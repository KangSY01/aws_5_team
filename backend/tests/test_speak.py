"""POST /speak (app/speech/polly.py) 테스트. AWS 에 접속하지 않는다 (boto3 클라이언트는 가짜 객체로 바꾼다)."""

import base64
import io
import json
import logging
import typing

import pytest
from botocore.exceptions import ClientError, MissingDependencyException, ReadTimeoutError

from app import config
from app.handler import handler
from app.models.api import ErrorResponse, SpeakLanguage, SpeakResponse
from app.speech import polly
from scripts.local_invoke import make_event

SECRET_TEXT = "자갈치시장까지 가는 버스를 타려면 어디로 가야 하나요?"
MP3 = b"\xff\xfb\x18\xc0fake-mp3"


class FakePolly:
    """synthesize_speech 만 가진 가짜 Polly 클라이언트. error 가 있으면 그 예외를 올린다."""

    def __init__(self, audio: bytes = MP3, error: Exception | None = None):
        self.audio, self.error, self.calls = audio, error, []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"AudioStream": io.BytesIO(self.audio), "ContentType": "audio/mpeg"}


@pytest.fixture
def real_mode(monkeypatch):
    """USE_MOCK=0 + 가짜 Polly. 캐시는 테스트마다 비운다."""
    fake = FakePolly()
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(polly, "_polly", lambda: fake)
    polly._synthesize.cache_clear()
    yield fake
    polly._synthesize.cache_clear()


def speak(body) -> tuple[int, dict]:
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    result = handler(make_event("POST", "/speak", raw))
    return result["statusCode"], json.loads(result["body"])


def error_code(status_body) -> tuple[int, str]:
    status, body = status_body
    return status, ErrorResponse.model_validate(body).error.code  # 계약의 오류 형식인지도 확인한다


# ---------- USE_MOCK=1 ----------

def test_mock_모드는_Polly_를_부르지_않고_샘플_mp3_를_돌려준다(monkeypatch):
    fake = FakePolly(error=AssertionError("USE_MOCK=1 에서는 호출하지 않는다"))
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(polly, "_polly", lambda: fake)
    for language in typing.get_args(SpeakLanguage):
        status, body = speak({"text": SECRET_TEXT, "language": language})
        assert status == 200 and set(body) == {"content_type", "audio_base64"}
        response = SpeakResponse.model_validate(body)
        assert response.content_type == "audio/mpeg"
        assert base64.b64decode(response.audio_base64, validate=True) == polly.SAMPLE_PATH.read_bytes()
    assert fake.calls == []


def test_샘플_mp3_는_짧은_MPEG_오디오_프레임이다():
    sample = polly.SAMPLE_PATH.read_bytes()
    assert 0 < len(sample) < 4096
    # 144바이트 프레임(MPEG-1 Layer III, 32kbps, 32kHz, 모노)마다 같은 헤더로 시작하고 나머지는 0(무음)이다
    frames = [sample[i:i + 144] for i in range(0, len(sample), 144)]
    assert all(frame == b"\xff\xfb\x18\xc0" + bytes(140) for frame in frames)


# ---------- 요청 검증 ----------

def test_text_는_1자에서_500자까지(real_mode):
    assert speak({"text": "가" * 500, "language": "ko"})[0] == 200
    assert error_code(speak({"text": "가" * 501, "language": "ko"})) == (422, "validation_error")
    assert error_code(speak({"text": "", "language": "ko"})) == (422, "validation_error")
    assert error_code(speak({"language": "ko"})) == (422, "validation_error")
    assert len(real_mode.calls) == 1  # 검증에 실패한 요청은 Polly 를 부르지 않는다


@pytest.mark.parametrize("language", ["fr", "ko-KR", "zh", "", None])
def test_잘못된_language_는_422(real_mode, language):
    assert error_code(speak({"text": "hello", "language": language})) == (422, "validation_error")
    assert real_mode.calls == []


def test_JSON_이_아니면_400_다른_메서드는_404(real_mode):
    assert error_code(speak("{not json")) == (400, "bad_request")
    result = handler(make_event("GET", "/speak"))
    assert (result["statusCode"], json.loads(result["body"])["error"]["code"]) == (404, "not_found")


# ---------- Polly 호출 ----------

def test_언어별_음성으로_mp3_를_요청하고_base64_로_돌려준다(real_mode):
    for language, (voice, engine) in polly.VOICES.items():
        status, body = speak({"text": "hello", "language": language})
        assert status == 200
        assert base64.b64decode(SpeakResponse.model_validate(body).audio_base64) == MP3
        assert real_mode.calls[-1] == {"Text": "hello", "OutputFormat": "mp3", "VoiceId": voice, "Engine": engine}
    assert set(polly.VOICES) == set(typing.get_args(SpeakLanguage))  # 계약의 언어를 모두 지원한다
    assert polly.VOICES["ko"][0] == "Seoyeon" and polly.VOICES["zh-Hans"] == polly.VOICES["zh-Hant"]


def test_같은_문장과_언어는_캐시를_쓴다(real_mode):
    assert polly.synthesize("hello", "en") == polly.synthesize("hello", "en") == MP3
    assert len(real_mode.calls) == 1
    polly.synthesize("hello", "ja")  # 언어가 다르면 다시 부른다
    polly.synthesize("hello!", "en")  # 문장이 다르면 다시 부른다
    assert len(real_mode.calls) == 3
    assert polly._synthesize.cache_info().maxsize == polly.CACHE_SIZE == 128


@pytest.mark.parametrize("error", [
    ClientError({"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "SynthesizeSpeech"),
    ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "SynthesizeSpeech"),
    ReadTimeoutError(endpoint_url="https://polly.ap-northeast-2.amazonaws.com"),
])
def test_Polly_실패는_계약의_오류_형식으로_답하고_문장을_로그에_남기지_않는다(real_mode, caplog, error):
    real_mode.error = error
    with caplog.at_level(logging.DEBUG):
        status, body = speak({"text": SECRET_TEXT, "language": "ko"})
    assert status == 500 and set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "internal_error"
    assert SECRET_TEXT not in caplog.text and SECRET_TEXT not in json.dumps(body, ensure_ascii=False)
    assert "language=ko" in caplog.text and f"글자 수={len(SECRET_TEXT)}" in caplog.text  # 언어와 길이만 남긴다
    # 실패는 캐시하지 않는다: Polly 가 돌아오면 같은 요청이 성공한다
    real_mode.error = None
    assert speak({"text": SECRET_TEXT, "language": "ko"})[0] == 200


def test_빈_음성도_실패로_본다(real_mode):
    real_mode.audio = b""
    assert error_code(speak({"text": "hello", "language": "en"})) == (500, "internal_error")


def test_성공_로그에도_문장을_남기지_않는다(real_mode, caplog):
    with caplog.at_level(logging.DEBUG):
        assert speak({"text": SECRET_TEXT, "language": "ko"})[0] == 200
    assert SECRET_TEXT not in caplog.text and "language=ko" in caplog.text


def test_클라이언트는_서울_리전으로_처음_쓸_때_한_번만_만든다(monkeypatch):
    created = []

    def fake_client(service, **kwargs):
        created.append((service, kwargs["region_name"]))
        return FakePolly()

    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(polly.boto3, "client", fake_client)
    polly._polly.cache_clear()
    polly._synthesize.cache_clear()
    try:
        assert created == []  # 모듈을 불러오는 것만으로는 만들지 않는다
        assert polly.synthesize("a", "ko") == polly.synthesize("b", "en") == MP3
        assert created == [("polly", config.BEDROCK_REGION)]
    finally:
        polly._polly.cache_clear()
        polly._synthesize.cache_clear()


def test_자격_증명을_찾지_못해도_오류_형식으로_답한다(monkeypatch):
    def broken_client(*args, **kwargs):
        raise MissingDependencyException(msg="botocore[crt] 가 필요합니다")

    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(polly.boto3, "client", broken_client)
    polly._polly.cache_clear()
    polly._synthesize.cache_clear()
    try:
        assert error_code(speak({"text": "hello", "language": "en"})) == (500, "internal_error")
    finally:
        polly._polly.cache_clear()
