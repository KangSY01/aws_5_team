"""사진 업로드용 S3 presigned PUT URL (POST /photo/upload-url).

브라우저가 사진을 S3 에 직접 올린다. 서버는 URL 만 서명하고 사진 바이트를 받지 않는다.
버킷은 공용 스택(infra/base)의 업로드 버킷이다. 퍼블릭 접근 차단, 1일 뒤 자동 삭제, CORS(PUT) 설정이 되어 있다.
"""

import logging
import re
import uuid
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from app import config
from app.models.api import ImageType, PhotoUploadUrlRequest, PhotoUploadUrlResponse
from app.photo.errors import PhotoKeyInvalid, PhotoServiceError

logger = logging.getLogger(__name__)

KEY_PREFIX = "photos/"
EXPIRES_IN = 300  # presigned URL 유효 시간(초). api-contract 예시와 같다
EXTENSIONS: dict[ImageType, str] = {"image/jpeg": "jpg", "image/png": "png"}
KEY_PATTERN = re.compile(r"photos/[0-9a-f]{32}\.(jpg|png)")  # fullmatch 로 쓴다 ($ 는 끝의 줄바꿈을 허용한다)
MOCK_UPLOAD_BASE = "https://mock-uploads.invalid"  # USE_MOCK=1 에서 돌려주는 가짜 주소 (.invalid 는 실제로 연결되지 않는 도메인)

TIMEOUT_SEC = 5  # team.md: 외부 호출 타임아웃 5초, 재시도 1회
RETRIES = 1


def new_key(content_type: ImageType) -> str:
    """추측할 수 없는 새 키. 사진마다 다르다."""
    return f"{KEY_PREFIX}{uuid.uuid4().hex}.{EXTENSIONS[content_type]}"


def validate_key(key: str) -> str:
    """이 서버가 발급한 형식의 키만 받는다. 아니면 PhotoKeyInvalid."""
    if not KEY_PATTERN.fullmatch(key):
        raise PhotoKeyInvalid(f"key 형식이 올바르지 않습니다: {key[:80]}")
    return key


@lru_cache(maxsize=1)
def _s3_client() -> Any:
    """컨테이너당 1회 만든다. 리전 엔드포인트로 서명해야 브라우저 PUT 이 리디렉션되지 않는다."""
    return boto3.client(
        "s3",
        region_name=config.BEDROCK_REGION,  # AWS_REGION 값. 리소스는 모두 같은 리전에 둔다
        config=BotocoreConfig(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
            connect_timeout=TIMEOUT_SEC,
            read_timeout=TIMEOUT_SEC,
            retries={"max_attempts": RETRIES, "mode": "standard"},
        ),
    )


def create_upload_url(request: PhotoUploadUrlRequest, *, bucket: str, client: Any = None) -> PhotoUploadUrlResponse:
    """presigned PUT URL 을 만든다. 브라우저는 같은 Content-Type 헤더로 PUT 해야 서명이 맞는다.

    USE_MOCK=1 이면 AWS 를 부르지 않고 가짜 주소를 돌려준다. 이 주소로는 올릴 수 없고,
    /photo/translate 는 USE_MOCK=1 에서 사진 대신 샘플 메뉴판을 읽는다.
    """
    key = new_key(request.content_type)
    if config.USE_MOCK:
        return PhotoUploadUrlResponse(upload_url=f"{MOCK_UPLOAD_BASE}/{key}", key=key, expires_in=EXPIRES_IN)

    if not bucket:
        logger.error("UPLOADS_BUCKET 환경 변수가 비어 있어 사진 업로드 URL 을 만들 수 없습니다.")
        raise PhotoServiceError("UPLOADS_BUCKET 이 설정되지 않았습니다.")
    try:
        url = (client or _s3_client()).generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": request.content_type},
            ExpiresIn=EXPIRES_IN,
            HttpMethod="PUT",
        )
    except (ClientError, BotoCoreError) as error:
        logger.error("사진 업로드 URL 서명 실패: %s", error)
        raise PhotoServiceError("업로드 URL 을 만들지 못했습니다.") from error
    return PhotoUploadUrlResponse(upload_url=url, key=key, expires_in=EXPIRES_IN)
