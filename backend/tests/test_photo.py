"""사진 인식 (app/photo) 테스트. AWS 를 부르지 않는다.

USE_MOCK·FAKE_LLM 은 테스트 안에서 monkeypatch 로 정한다. 기본 모드와 USE_MOCK=1 FAKE_LLM=1 모드 어느 쪽으로 돌려도 결과가 같다.
S3·Textract·Bedrock 은 호출 인자를 기록하는 가짜 클라이언트로 바꾼다.
"""

import pytest
from botocore.exceptions import ClientError

from app import config
from app.models.api import BoundingBox, PhotoTranslateRequest, PhotoTranslateResponse, PhotoUploadUrlRequest
from app.photo import ocr, service, translate, upload
from app.photo.errors import PhotoKeyInvalid, PhotoNotFound, PhotoServiceError, PhotoUnreadable
from app.photo.ocr import OcrLine

KEY = "photos/0123456789abcdef0123456789abcdef.jpg"
BOX = BoundingBox(left=0.1, top=0.2, width=0.3, height=0.05)


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(config, "FAKE_LLM", True)


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "UPLOADS_BUCKET", "busan-guide-uploads-test", raising=False)


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "test"}}, "Op")


def line_block(text: str, confidence: float = 99.0, box: dict | None = None) -> dict:
    return {
        "BlockType": "LINE",
        "Text": text,
        "Confidence": confidence,
        "Geometry": {"BoundingBox": box or {"Left": 0.1, "Top": 0.2, "Width": 0.3, "Height": 0.05}},
    }


# ---- 업로드 URL ----


class FakeS3:
    def __init__(self, error: Exception | None = None):
        self.calls, self.error = [], error

    def generate_presigned_url(self, method, Params, ExpiresIn, HttpMethod):
        self.calls.append((method, Params, ExpiresIn, HttpMethod))
        if self.error:
            raise self.error
        return f"https://bucket.s3.ap-northeast-2.amazonaws.com/{Params['Key']}?X-Amz-Signature=x"


@pytest.mark.parametrize("content_type, ext", [("image/jpeg", "jpg"), ("image/png", "png")])
def test_new_key_matches_pattern_and_is_unique(content_type, ext):
    keys = {upload.new_key(content_type) for _ in range(20)}
    assert len(keys) == 20
    for key in keys:
        assert key.endswith(f".{ext}")
        assert upload.validate_key(key) == key


def test_upload_url_signs_put_with_content_type(real_mode):
    s3 = FakeS3()
    result = upload.create_upload_url(PhotoUploadUrlRequest(content_type="image/png"), bucket="b1", client=s3)

    method, params, expires, http = s3.calls[0]
    assert (method, http, expires) == ("put_object", "PUT", 300)
    assert params == {"Bucket": "b1", "Key": result.key, "ContentType": "image/png"}
    assert result.expires_in == 300
    assert result.key in result.upload_url
    upload.validate_key(result.key)


def test_upload_url_without_bucket_is_service_error(real_mode):
    with pytest.raises(PhotoServiceError):
        upload.create_upload_url(PhotoUploadUrlRequest(content_type="image/jpeg"), bucket="", client=FakeS3())


def test_upload_url_aws_error_is_service_error(real_mode):
    with pytest.raises(PhotoServiceError):
        upload.create_upload_url(
            PhotoUploadUrlRequest(content_type="image/jpeg"), bucket="b1", client=FakeS3(client_error("AccessDenied"))
        )


def test_upload_url_mock_does_not_call_aws(mock_mode):
    s3 = FakeS3()
    result = upload.create_upload_url(PhotoUploadUrlRequest(content_type="image/jpeg"), bucket="", client=s3)
    assert s3.calls == []
    assert result.upload_url.startswith(upload.MOCK_UPLOAD_BASE)
    upload.validate_key(result.key)


@pytest.mark.parametrize("key", [
    "photos/abc.jpg",  # 32자가 아님
    "photos/0123456789ABCDEF0123456789ABCDEF.jpg",  # 대문자
    "photos/0123456789abcdef0123456789abcdef.gif",
    "data/0123456789abcdef0123456789abcdef.jpg",  # 다른 접두사
    "photos/../secret/0123456789abcdef0123456789abcdef.jpg",
    "photos/0123456789abcdef0123456789abcdef.jpg\n",
    "",
])
def test_validate_key_rejects_other_objects(key):
    with pytest.raises(PhotoKeyInvalid):
        upload.validate_key(key)


# ---- 글자 인식 ----


def test_parse_lines_keeps_korean_lines_only():
    response = {"Blocks": [
        {"BlockType": "PAGE"},
        line_block("돼지국밥   9,000원"),
        {"BlockType": "WORD", "Text": "돼지국밥", "Confidence": 99.0, "Geometry": {"BoundingBox": {}}},
        line_block("OPEN 10:00"),  # 한글 없음
        line_block("곱빼기", confidence=40.0),  # 신뢰도 낮음
        line_block("   "),
        {"BlockType": "LINE", "Text": "밀면", "Confidence": 99.0},  # 좌표 없음
    ]}
    lines = ocr.parse_lines(response)
    assert [line.text for line in lines] == ["돼지국밥 9,000원"]
    assert lines[0].bbox == BOX


def test_parse_lines_clamps_bbox_to_0_1():
    box = {"Left": -0.01, "Top": 0.95, "Width": 1.02, "Height": "x"}
    (line,) = ocr.parse_lines({"Blocks": [line_block("어묵", box=box)]})
    assert line.bbox == BoundingBox(left=0.0, top=0.95, width=1.0, height=0.0)


def test_parse_lines_caps_line_count():
    lines = ocr.parse_lines({"Blocks": [line_block(f"메뉴 {i}") for i in range(ocr.MAX_LINES + 5)]})
    assert len(lines) == ocr.MAX_LINES
    assert lines[0].text == "메뉴 0"


class FakeTextract:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.calls, self.response, self.error = [], response or {"Blocks": []}, error

    def detect_document_text(self, Document):
        self.calls.append(Document)
        if self.error:
            raise self.error
        return self.response


def test_detect_lines_reads_s3_object(real_mode):
    textract = FakeTextract({"Blocks": [line_block("밀면")]})
    lines = ocr.detect_lines("b1", KEY, client=textract)
    assert textract.calls == [{"S3Object": {"Bucket": "b1", "Name": KEY}}]
    assert [line.text for line in lines] == ["밀면"]


@pytest.mark.parametrize("code, expected", [
    ("InvalidS3ObjectException", PhotoNotFound),
    ("UnsupportedDocumentException", PhotoUnreadable),
    ("BadDocumentException", PhotoUnreadable),
    ("DocumentTooLargeException", PhotoUnreadable),
    ("ThrottlingException", PhotoServiceError),
    ("AccessDeniedException", PhotoServiceError),
])
def test_detect_lines_maps_textract_errors(real_mode, code, expected):
    with pytest.raises(expected):
        ocr.detect_lines("b1", KEY, client=FakeTextract(error=client_error(code)))


def test_detect_lines_without_bucket_is_service_error(real_mode):
    with pytest.raises(PhotoServiceError):
        ocr.detect_lines("", KEY, client=FakeTextract())


def test_detect_lines_mock_uses_sample_menu(mock_mode):
    textract = FakeTextract()
    lines = ocr.detect_lines("", KEY, client=textract)
    assert textract.calls == []
    assert [line.text for line in lines] == [
        "차림표", "돼지국밥 9,000원", "순대국밥 9,500원", "낙곱새 (2인) 28,000원",
        "밀면 8,000원", "비빔밀면 8,500원", "어묵 4,000원", "공기밥 추가 1,000원",
    ]


# ---- 번역·매운맛 ----


@pytest.mark.parametrize("text, spicy", [
    ("낙곱새 (2인) 28,000원", True),
    ("얼큰 수제비", True),
    ("김치찌개", True),
    ("안 매운 떡볶이", False),
    ("궁중떡볶이", False),
    ("간장 닭갈비", False),
    ("돼지국밥", False),
    ("밀면", False),
])
def test_rule_spicy(text, spicy):
    assert translate.rule_spicy(text) is spicy


def lines_of(*texts: str) -> list[OcrLine]:
    return [OcrLine(text=t, bbox=BOX) for t in texts]


def test_merge_aligns_by_index_and_keeps_textract_values():
    lines = lines_of("돼지국밥", "낙곱새", "공기밥")
    raw = [
        {"index": 1, "translated": "Nakgopsae", "spicy": False},  # 규칙이 true 로 덮는다
        {"index": 0, "translated": "  Pork soup  ", "spicy": "no"},  # bool 아님 → null
        {"index": 0, "translated": "duplicate", "spicy": True},  # 같은 번호 두 번째는 버린다
        {"index": 7, "translated": "out of range", "spicy": True},
        "not a dict",
    ]
    items = translate._merge(lines, raw)
    assert [(i.text_ko, i.translated, i.spicy) for i in items] == [
        ("돼지국밥", "Pork soup", None),
        ("낙곱새", "Nakgopsae", True),
        ("공기밥", "공기밥", None),  # 모델이 빠뜨린 줄은 원문
    ]
    assert all(item.bbox == BOX for item in items)


class FakeBedrock:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.calls, self.response, self.error = [], response, error

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def tool_response(items: list[dict], name: str = translate.TOOL_NAME) -> dict:
    return {
        "stopReason": "tool_use",
        "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": name, "input": {"items": items}}}]}},
    }


def test_call_model_forces_tool_and_reads_items(real_mode):
    bedrock = FakeBedrock(tool_response([{"index": 0, "translated": "ミルミョン", "spicy": False}]))
    items = translate.translate_lines(lines_of("밀면"), "ja", client=bedrock)

    call = bedrock.calls[0]
    assert call["modelId"] == config.MODEL_ID
    assert call["toolConfig"]["toolChoice"] == {"tool": {"name": translate.TOOL_NAME}}
    assert "Japanese" in call["system"][0]["text"]
    assert call["messages"][0]["content"][0]["text"] == "0. 밀면"
    assert call["inferenceConfig"]["maxTokens"] == translate.MAX_TOKENS
    assert [(i.translated, i.spicy) for i in items] == [("ミルミョン", False)]


@pytest.mark.parametrize("response", [
    {"stopReason": "end_turn", "output": {"message": {"content": [{"text": "sorry"}]}}},
    tool_response([], name="other_tool"),
])
def test_call_model_without_tool_use_is_service_error(real_mode, response):
    with pytest.raises(PhotoServiceError):
        translate.translate_lines(lines_of("밀면"), "en", client=FakeBedrock(response))


def test_call_model_aws_error_is_service_error(real_mode):
    with pytest.raises(PhotoServiceError):
        translate.translate_lines(lines_of("밀면"), "en", client=FakeBedrock(error=client_error("ThrottlingException")))


def test_translate_without_lines_does_not_call_model(real_mode):
    bedrock = FakeBedrock()
    assert translate.translate_lines([], "en", client=bedrock) == []
    assert bedrock.calls == []


# ---- 경로 전체 (USE_MOCK=1 FAKE_LLM=1) ----


@pytest.mark.parametrize("language", ["en", "ja", "zh-Hans", "zh-Hant"])
def test_translate_photo_mock_end_to_end(mock_mode, language):
    result = service.translate_photo(PhotoTranslateRequest(key=KEY, language=language))

    PhotoTranslateResponse.model_validate(result.model_dump())  # 계약 모델과 같은 형식
    assert result.key == KEY and result.language == language
    assert len(result.items) == 8
    spicy = {item.text_ko: item.spicy for item in result.items}
    assert spicy["낙곱새 (2인) 28,000원"] is True
    assert spicy["비빔밀면 8,500원"] is True
    assert spicy["돼지국밥 9,000원"] is False
    assert spicy["차림표"] is None
    assert all(item.translated != item.text_ko for item in result.items)  # 샘플 번역표에 모든 줄이 있다


def test_translate_photo_rejects_foreign_key(mock_mode):
    with pytest.raises(PhotoKeyInvalid):
        service.translate_photo(PhotoTranslateRequest(key="data/places.json", language="en"))


def test_service_reads_bucket_from_config(real_mode, monkeypatch):
    seen = {}
    monkeypatch.setattr(upload, "create_upload_url", lambda request, bucket: seen.setdefault("bucket", bucket))
    service.create_upload_url(PhotoUploadUrlRequest(content_type="image/jpeg"))
    assert seen["bucket"] == "busan-guide-uploads-test"
