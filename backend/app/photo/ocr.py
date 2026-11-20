"""사진의 한국어 글자 인식 (Textract DetectDocumentText).

DetectDocumentText 는 한국어를 지원한다 (Textract 언어 지원 Category 3).
https://docs.aws.amazon.com/textract/latest/dg/supported-languages.html
LINE 블록만 쓴다. 좌표(BoundingBox)는 사진 너비·높이 대비 비율(0~1)이라 api-contract 의 bbox 와 기준이 같다.
"""

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from app import config
from app.models.api import BoundingBox
from app.photo.errors import PhotoNotFound, PhotoServiceError, PhotoUnreadable

logger = logging.getLogger(__name__)

SAMPLE_RESPONSE = Path(__file__).parent / "samples" / "textract_menu.json"  # USE_MOCK=1 에서 쓰는 Textract 응답

HANGUL = re.compile(r"[\uac00-\ud7a3]")  # 한글 음절이 하나도 없는 줄(영어 간판, 숫자만 있는 줄)은 번역하지 않는다
MIN_CONFIDENCE = 70.0  # Textract 신뢰도(0~100)가 이보다 낮은 줄은 버린다
MAX_LINES = 30  # 번역 호출 1회에 넣는 상한. 메뉴판 한 장에는 충분하다

TIMEOUT_SEC = 5  # team.md: 외부 호출 타임아웃 5초, 재시도 1회
RETRIES = 1

# Textract 오류 코드 → 사용자 쪽 문제(이미지)인지
_NOT_FOUND = {"InvalidS3ObjectException"}
_UNREADABLE = {"UnsupportedDocumentException", "BadDocumentException", "DocumentTooLargeException", "InvalidParameterException"}


@dataclass(frozen=True)
class OcrLine:
    text: str  # 공백을 하나로 줄인 한 줄
    bbox: BoundingBox


def _ratio(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _bbox(box: dict) -> BoundingBox:
    """Textract BoundingBox(Width, Height, Left, Top). 사진 가장자리에서 1을 조금 넘는 값이 와도 0~1로 자른다."""
    return BoundingBox(left=_ratio(box.get("Left")), top=_ratio(box.get("Top")),
                       width=_ratio(box.get("Width")), height=_ratio(box.get("Height")))


def parse_lines(response: dict) -> list[OcrLine]:
    """DetectDocumentText 응답에서 번역할 줄을 읽는 순서대로 뽑는다 (최대 MAX_LINES)."""
    lines: list[OcrLine] = []
    for block in response.get("Blocks") or []:
        if block.get("BlockType") != "LINE":
            continue
        text = " ".join(str(block.get("Text") or "").split())
        box = (block.get("Geometry") or {}).get("BoundingBox")
        if not text or not HANGUL.search(text) or not box:
            continue
        if float(block.get("Confidence") or 0) < MIN_CONFIDENCE:
            continue
        lines.append(OcrLine(text=text, bbox=_bbox(box)))
    if len(lines) > MAX_LINES:
        logger.info("인식한 줄이 %d개라 앞의 %d개만 번역합니다.", len(lines), MAX_LINES)
    return lines[:MAX_LINES]


@lru_cache(maxsize=1)
def _textract_client() -> Any:
    return boto3.client(
        "textract",
        region_name=config.BEDROCK_REGION,  # AWS_REGION 값. 업로드 버킷과 같은 리전이어야 한다
        config=BotocoreConfig(
            connect_timeout=TIMEOUT_SEC,
            read_timeout=TIMEOUT_SEC,
            retries={"max_attempts": RETRIES, "mode": "standard"},
        ),
    )


def _call_textract(bucket: str, key: str, client: Any) -> dict:
    try:
        return client.detect_document_text(Document={"S3Object": {"Bucket": bucket, "Name": key}})
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code in _NOT_FOUND:
            raise PhotoNotFound(f"사진을 찾을 수 없습니다: {key}") from error
        if code in _UNREADABLE:
            raise PhotoUnreadable("사진을 읽을 수 없습니다. JPEG·PNG, 10MB 이하로 다시 찍어 주세요.") from error
        logger.error("Textract 호출 실패 (%s): %s", code, error)
        raise PhotoServiceError("글자 인식에 실패했습니다.") from error
    except BotoCoreError as error:
        logger.error("Textract 호출 실패: %s", error)
        raise PhotoServiceError("글자 인식에 실패했습니다.") from error


def detect_lines(bucket: str, key: str, client: Any = None) -> list[OcrLine]:
    """S3 의 사진에서 한국어 줄과 좌표를 읽는다. USE_MOCK=1 이면 샘플 메뉴판 응답을 쓴다 (key 는 보지 않는다)."""
    if config.USE_MOCK:
        response = json.loads(SAMPLE_RESPONSE.read_text(encoding="utf-8"))
    else:
        if not bucket:
            logger.error("UPLOADS_BUCKET 환경 변수가 비어 있어 사진을 읽을 수 없습니다.")
            raise PhotoServiceError("UPLOADS_BUCKET 이 설정되지 않았습니다.")
        response = _call_textract(bucket, key, client or _textract_client())
    return parse_lines(response)
