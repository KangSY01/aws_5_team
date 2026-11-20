"""사진 인식 경로 진입점. handler.py 는 이 두 함수만 부른다.

POST /photo/upload-url → create_upload_url
POST /photo/translate  → translate_photo (S3 사진 → Textract → Bedrock 번역·매운맛)

오류는 app.photo.errors 의 예외로 올라온다. handler.py 가 api-contract 오류 형식으로 바꾼다.
"""

import logging

from app import config
from app.models.api import PhotoTranslateRequest, PhotoTranslateResponse, PhotoUploadUrlRequest, PhotoUploadUrlResponse
from app.photo import ocr, translate, upload

logger = logging.getLogger(__name__)


def _bucket() -> str:
    """업로드 버킷 이름 (환경 변수 UPLOADS_BUCKET, 공용 스택 출력 UploadsBucketName).

    config.py 는 A 담당이라 아직 이 상수가 없을 수 있다. 추가되기 전에는 빈 값으로 보고, USE_MOCK=0 이면 PhotoServiceError 가 난다.
    """
    return getattr(config, "UPLOADS_BUCKET", "") or ""


def create_upload_url(request: PhotoUploadUrlRequest) -> PhotoUploadUrlResponse:
    return upload.create_upload_url(request, bucket=_bucket())


def translate_photo(request: PhotoTranslateRequest) -> PhotoTranslateResponse:
    key = upload.validate_key(request.key)
    lines = ocr.detect_lines(_bucket(), key)
    items = translate.translate_lines(lines, request.language)
    logger.info("사진 번역 완료: %s, %d줄, 매운 음식 %d개", key, len(items), sum(1 for i in items if i.spicy))
    return PhotoTranslateResponse(key=key, language=request.language, items=items)
