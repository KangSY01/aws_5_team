"""음성 입력 (app/voice, POST /voice/url). AWS 를 부르지 않는다.

서명은 botocore 가 하고, 이 테스트는 AWS 문서의 Transcribe WebSocket 서명 절차를 직접 계산해 같은 서명인지 확인한다.
https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html
"""

import datetime as dt
import hashlib
import hmac
import json
import logging
import typing
from urllib.parse import parse_qsl, quote, urlsplit

import pytest
from botocore.credentials import ReadOnlyCredentials

from app import config
from app import handler as handler_module
from app.handler import handler
from app.models.api import ErrorResponse, VoiceUrlResponse
from app.models.plan import Language
from app.voice import languages, presign, service
from app.voice.errors import VoiceServiceError
from scripts.local_invoke import make_event

# 테스트용 가짜 키 (AWS 문서 예시 형식). 실제 키가 아니다
CREDS = ReadOnlyCredentials("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "FAKE/SESSION+TOKEN==")
NOW = dt.datetime(2026, 11, 28, 9, 30, 15, tzinfo=dt.timezone.utc)
REGION = "ap-northeast-2"


@pytest.fixture
def frozen_time(monkeypatch):
    import botocore.auth

    monkeypatch.setattr(botocore.auth, "get_current_datetime", lambda: NOW)


def call(body) -> tuple[int, dict]:
    result = handler(make_event("POST", "/voice/url", body if isinstance(body, str) else json.dumps(body)))
    return result["statusCode"], json.loads(result["body"])


def expected_signature(url: str, secret: str) -> str:
    """AWS 문서의 절차 그대로: canonical request → string to sign → 서명 키 → HMAC-SHA256."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "X-Amz-Signature"]
    canonical_query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query))
    canonical_request = "\n".join([
        "GET", parts.path, canonical_query, f"host:{parts.netloc}\n", "host", hashlib.sha256(b"").hexdigest(),
    ])
    values = dict(query)
    amz_date = values["X-Amz-Date"]
    scope = values["X-Amz-Credential"].split("/", 1)[1]
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode()).hexdigest()])
    key = ("AWS4" + secret).encode()
    for part in scope.split("/"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()


# ---- 언어 ----


def test_every_app_language_has_a_streaming_language_code():
    assert set(languages.VOICE_LANGUAGES) == set(typing.get_args(Language))
    codes = {lang: v.transcribe_code for lang, v in languages.VOICE_LANGUAGES.items()}
    assert codes == {"en": "en-US", "ja": "ja-JP", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW"}


def test_recognition_code_and_transcript_language_are_separate():
    # 인식 언어 코드(Transcribe)와 인식된 문장의 언어(채팅·번역)는 따로 정한다. 중국어는 간체·번체가 코드로 갈린다
    assert languages.transcript_language("zh-CN") == "zh-Hans"
    assert languages.transcript_language("zh-TW") == "zh-Hant"
    assert all(languages.transcript_language(v.transcribe_code) == v.transcript_language
               for v in languages.VOICE_LANGUAGES.values())
    with pytest.raises(KeyError):
        languages.transcript_language("ko-KR")


# ---- 서명 ----


@pytest.mark.parametrize("token", [CREDS.token, None])
def test_presigned_url_follows_the_transcribe_websocket_spec(frozen_time, token):
    creds = ReadOnlyCredentials(CREDS.access_key, CREDS.secret_key, token)

    url = presign.websocket_url(credentials=creds, region=REGION, language_code="ja-JP", sample_rate=16000)

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    assert (parts.scheme, parts.netloc, parts.path) == ("wss", "transcribestreaming.ap-northeast-2.amazonaws.com:8443",
                                                         "/stream-transcription-websocket")
    assert {k: query[k] for k in ("language-code", "media-encoding", "sample-rate")} == {
        "language-code": "ja-JP", "media-encoding": "pcm", "sample-rate": "16000"}
    assert query["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert query["X-Amz-Credential"] == f"{CREDS.access_key}/20261128/ap-northeast-2/transcribe/aws4_request"
    assert query["X-Amz-Date"] == "20261128T093015Z" and query["X-Amz-Expires"] == "300"
    assert query["X-Amz-SignedHeaders"] == "host"
    assert query.get("X-Amz-Security-Token") == token  # 임시 자격 증명이면 세션 토큰이 들어간다
    assert CREDS.secret_key not in url and quote(CREDS.secret_key, safe="") not in url  # 비밀 키는 URL 에 없다
    assert query["X-Amz-Signature"] == expected_signature(url, CREDS.secret_key)


@pytest.mark.parametrize("expires", [0, 301])
def test_expiry_is_limited_to_what_transcribe_accepts(expires):
    with pytest.raises(ValueError):
        presign.websocket_url(credentials=CREDS, region=REGION, language_code="en-US", sample_rate=16000, expires=expires)


# ---- 서비스 ----


@pytest.mark.parametrize("language, code", [("en", "en-US"), ("ja", "ja-JP"), ("zh-Hans", "zh-CN"), ("zh-Hant", "zh-TW")])
def test_real_mode_signs_with_the_role_credentials_in_the_config_region(monkeypatch, frozen_time, language, code):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "BEDROCK_REGION", REGION)
    monkeypatch.setattr(service, "_credentials", lambda: CREDS)

    status, body = call({"language": language})

    assert status == 200
    response = VoiceUrlResponse.model_validate(body)
    query = dict(parse_qsl(urlsplit(response.url).query))
    assert query["language-code"] == code and "/ap-northeast-2/transcribe/" in query["X-Amz-Credential"]
    assert (response.expires_in, response.sample_rate, response.media_encoding) == (300, 16000, "pcm")
    assert query["sample-rate"] == str(response.sample_rate)  # 브라우저가 맞출 값과 서명한 값이 같다


def test_mock_mode_needs_no_aws(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(service, "_credentials", lambda: pytest.fail("USE_MOCK=1 에서 자격 증명을 읽으면 안 된다"))

    status, body = call({"language": "zh-Hant"})

    response = VoiceUrlResponse.model_validate(body)
    assert status == 200 and response.url.startswith("wss://mock-transcribe.invalid/stream-transcription-websocket?")
    assert "language-code=zh-TW" in response.url and "X-Amz-Signature" not in response.url


def test_missing_credentials_become_a_service_error(monkeypatch):
    class NoCredentials:
        def get_credentials(self):
            return None

    monkeypatch.setattr(service.boto3, "Session", NoCredentials)
    with pytest.raises(VoiceServiceError):
        service._credentials()


# ---- API 오류와 로그 ----


@pytest.mark.parametrize("body, status, code", [
    ({"language": "ko"}, 422, "validation_error"),  # 지원하지 않는 언어
    ({}, 422, "validation_error"),
    ("{bad", 400, "bad_request"),
])
def test_bad_requests_keep_the_contract(body, status, code):
    got_status, got = call(body)
    assert got_status == status and ErrorResponse.model_validate(got).error.code == code


def test_service_errors_are_500_without_details(monkeypatch, caplog):
    monkeypatch.setattr(config, "USE_MOCK", False)

    def boom():
        raise RuntimeError("secret detail")

    monkeypatch.setattr(service, "_credentials", boom)  # 서명 단계의 예상하지 못한 오류
    with caplog.at_level(logging.INFO):
        status, body = call({"language": "en"})

    assert status == 500 and body == {"error": {"code": "internal_error", "message": "서버 오류가 발생했습니다."}}
    assert "secret detail" not in json.dumps(body) and "secret detail" not in caplog.text  # 예외 내용은 남기지 않는다
    assert "RuntimeError" in caplog.text  # 종류만 남긴다


def test_issued_url_and_token_are_not_logged(monkeypatch, frozen_time, caplog):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(service, "_credentials", lambda: CREDS)
    with caplog.at_level(logging.INFO):
        status, _ = call({"language": "ja"})
    assert status == 200
    assert CREDS.token not in caplog.text and "X-Amz-Signature" not in caplog.text and CREDS.secret_key not in caplog.text


def test_voice_route_is_added_next_to_the_existing_routes(monkeypatch):
    source = open(handler_module.__file__, encoding="utf-8").read()
    for route in ('["chat"]', '["plan", "check"]', '["alerts"]', '["speak"]', '["photo", "upload-url"]',
                  '["photo", "translate"]', '["voice", "url"]'):
        assert route in source, route
    monkeypatch.setattr(config, "USE_MOCK", True)
    assert call({"language": "en"})[0] == 200
