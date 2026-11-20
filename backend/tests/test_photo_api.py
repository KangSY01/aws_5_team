"""사진 인식 경로(POST /photo/upload-url, /photo/translate)의 handler 연결 테스트. AWS 를 부르지 않는다.

USE_MOCK=1 FAKE_LLM=1 로 고정해 샘플 메뉴판·고정 번역을 쓴다. 오류 변환은 service 를 바꿔 끼워 확인한다.
"""

import json

import pytest

from app import config, handler as handler_module
from app.handler import handler
from app.models.api import ErrorResponse, PhotoTranslateResponse, PhotoUploadUrlResponse
from app.photo import errors, upload

KEY = "photos/0123456789abcdef0123456789abcdef.jpg"


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(config, "FAKE_LLM", True)


def post(path: str, body) -> tuple[int, dict]:
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    event = {"version": "2.0", "rawPath": path, "requestContext": {"http": {"method": "POST", "path": path}},
             "body": raw, "isBase64Encoded": False}
    res = handler(event)
    return res["statusCode"], json.loads(res["body"])


@pytest.mark.parametrize("content_type, ext", [("image/jpeg", "jpg"), ("image/png", "png")])
def test_upload_url(content_type, ext):
    status, body = post("/photo/upload-url", {"content_type": content_type})
    assert status == 200
    result = PhotoUploadUrlResponse.model_validate(body)
    assert result.key.endswith(f".{ext}") and upload.validate_key(result.key)
    assert result.expires_in == upload.EXPIRES_IN


@pytest.mark.parametrize("body", [{"content_type": "image/gif"}, {}])
def test_upload_url_rejects_other_types(body):
    status, err = post("/photo/upload-url", body)
    assert status == 422 and ErrorResponse.model_validate(err).error.code == "validation_error"


def test_translate_sample_menu():
    status, body = post("/photo/translate", {"key": KEY, "language": "ja"})
    assert status == 200
    result = PhotoTranslateResponse.model_validate(body)
    assert result.key == KEY and result.language == "ja"
    assert len(result.items) == 8
    assert {i.text_ko: i.spicy for i in result.items}["낙곱새 (2인) 28,000원"] is True


@pytest.mark.parametrize("body, code", [
    ({"key": "data/places.json", "language": "en"}, "validation_error"),  # 발급한 형식이 아닌 키
    ({"key": KEY, "language": "ko"}, "validation_error"),  # 번역 언어가 아님
    ("{not json", "bad_request"),
])
def test_translate_rejects_bad_requests(body, code):
    status, err = post("/photo/translate", body)
    assert status == (400 if code == "bad_request" else 422)
    assert ErrorResponse.model_validate(err).error.code == code


@pytest.mark.parametrize("error, status, code", [
    (errors.PhotoNotFound("사진을 찾을 수 없습니다"), 404, "not_found"),
    (errors.PhotoUnreadable("사진을 읽을 수 없습니다"), 422, "validation_error"),
    (errors.PhotoServiceError("UPLOADS_BUCKET 이 설정되지 않았습니다."), 500, "internal_error"),
])
def test_translate_maps_photo_errors(monkeypatch, error, status, code):
    def fail(request):
        raise error

    monkeypatch.setattr(handler_module.photo, "translate_photo", fail)
    got_status, err = post("/photo/translate", {"key": KEY, "language": "en"})
    body = ErrorResponse.model_validate(err).error
    assert (got_status, body.code) == (status, code)
    if code == "internal_error":
        assert "UPLOADS_BUCKET" not in body.message  # 내부 사유는 응답에 담지 않는다


def test_upload_url_service_error_is_500(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "UPLOADS_BUCKET", "")
    status, err = post("/photo/upload-url", {"content_type": "image/jpeg"})
    assert status == 500 and ErrorResponse.model_validate(err).error.code == "internal_error"
