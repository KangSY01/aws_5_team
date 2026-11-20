"""인식한 한국어 줄 번역과 매운맛 표시 (Bedrock Converse).

역할 분리 (team.md):
- LLM: 번역 문장, 음식이면 짧은 설명, 매운 음식인지 판단
- 코드: 줄·좌표(Textract 결과 그대로), 매운맛 단어 규칙(아래 SPICY_WORDS 가 있으면 LLM 판단과 상관없이 true)

모델 출력은 도구 호출(toolChoice 로 submit_translations 한 개를 강제)로 받아 JSON 형식을 보장한다.
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html
(toolChoice.tool 은 Anthropic Claude·Amazon Nova 모델만 지원한다. 기본 모델 BEDROCK_MODEL_ID 는 Claude 다)
에이전트(도구 반복)가 아니라 1회 호출이라 Strands Agent 를 쓰지 않고 boto3 Converse 를 직접 부른다.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from app import config
from app.models.api import PhotoItem
from app.models.plan import Language
from app.photo.errors import PhotoServiceError
from app.photo.ocr import OcrLine

logger = logging.getLogger(__name__)

FAKE_TRANSLATIONS = Path(__file__).parent / "samples" / "fake_translations.json"  # FAKE_LLM=1 고정 번역

MAX_TOKENS = 2048  # 30줄 번역에 충분한 상한
TIMEOUT_SEC = 10  # 메뉴판 한 장(최대 30줄) 생성 시간. 연결 시간은 5초
RETRIES = 1
TOOL_NAME = "submit_translations"

LANGUAGE_NAMES: dict[Language, str] = {
    "en": "English",
    "ja": "Japanese",
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
}

# 이 단어가 원문에 있으면 매운 음식으로 표시한다 (모델이 놓쳐도). 빨간 양념이 기본인 메뉴 이름 위주.
# "안 매운", "순한" 같은 부정 표현이 있으면 규칙을 적용하지 않고 모델 판단을 따른다.
SPICY_WORDS = ("매운", "매콤", "얼큰", "불닭", "땡초", "청양", "고추", "낙곱새", "떡볶이", "짬뽕", "닭갈비", "제육", "김치찌개", "육개장", "쭈꾸미", "주꾸미", "낙지볶음", "아구찜", "아귀찜", "마라")
MILD_WORDS = re.compile(r"안\s*매운|순한|맵지\s*않|백짬뽕|궁중떡볶이|간장")

SYSTEM_PROMPT = """\
You translate Korean text read from a photo of a Busan restaurant menu or shop sign for a foreign traveler.
For each numbered line, return:
- translated: the line in {language}. For a dish, give the name in {language} (a reading in {language} script is fine) \
followed by a short description of what it is in parentheses, e.g. "Dwaeji-gukbap (pork soup with rice)". \
Keep prices, numbers and units exactly as written. For text that is not a dish, translate it plainly.
- spicy: true if the dish is normally spicy in Korea, false if it is normally not spicy, null if the line is not a dish \
or you cannot tell. Never guess ingredients that are not implied by the name.
Return every line exactly once by its index, using the {tool} tool. Do not add lines.
"""

_TOOL_SPEC = {
    "toolSpec": {
        "name": TOOL_NAME,
        "description": "Submit the translation of every numbered line.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer", "description": "Line number from the input"},
                                "translated": {"type": "string"},
                                "spicy": {"type": ["boolean", "null"]},
                            },
                            "required": ["index", "translated", "spicy"],
                        },
                    }
                },
                "required": ["items"],
            }
        },
    }
}


def rule_spicy(text_ko: str) -> bool:
    """원문에 매운 메뉴 단어가 있고 순한 맛 표현이 없으면 True."""
    return any(word in text_ko for word in SPICY_WORDS) and not MILD_WORDS.search(text_ko)


@lru_cache(maxsize=1)
def _bedrock_client() -> Any:
    return boto3.client(
        "bedrock-runtime",
        region_name=config.BEDROCK_REGION,
        config=BotocoreConfig(
            connect_timeout=5,
            read_timeout=TIMEOUT_SEC,
            retries={"max_attempts": RETRIES, "mode": "standard"},
        ),
    )


def _user_text(lines: list[OcrLine]) -> str:
    return "\n".join(f"{i}. {line.text}" for i, line in enumerate(lines))


def _call_model(lines: list[OcrLine], language: Language, client: Any) -> list[dict]:
    """Converse 1회. submit_translations 도구 입력의 items 를 돌려준다."""
    try:
        response = client.converse(
            modelId=config.MODEL_ID,
            system=[{"text": SYSTEM_PROMPT.format(language=LANGUAGE_NAMES[language], tool=TOOL_NAME)}],
            messages=[{"role": "user", "content": [{"text": _user_text(lines)}]}],
            toolConfig={"tools": [_TOOL_SPEC], "toolChoice": {"tool": {"name": TOOL_NAME}}},
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
        )
    except (ClientError, BotoCoreError) as error:
        logger.error("사진 번역 Bedrock 호출 실패: %s", error)
        raise PhotoServiceError("번역에 실패했습니다.") from error

    if response.get("stopReason") == "max_tokens":
        logger.warning("사진 번역이 max_tokens 에서 끊겼습니다. 받은 줄만 씁니다.")
    for block in response.get("output", {}).get("message", {}).get("content", []):
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == TOOL_NAME:
            items = (tool_use.get("input") or {}).get("items")
            if isinstance(items, list):
                return items
    logger.error("사진 번역 응답에 %s 도구 호출이 없습니다 (stopReason=%s).", TOOL_NAME, response.get("stopReason"))
    raise PhotoServiceError("번역 결과를 읽지 못했습니다.")


def _fake_items(lines: list[OcrLine], language: Language) -> list[dict]:
    """FAKE_LLM=1: 샘플 번역표에 있는 줄은 그 번역, 없는 줄은 원문을 그대로 돌려준다."""
    table = json.loads(FAKE_TRANSLATIONS.read_text(encoding="utf-8"))
    items = []
    for i, line in enumerate(lines):
        entry = table.get(line.text, {})
        items.append({"index": i, "translated": entry.get(language, line.text), "spicy": entry.get("spicy")})
    return items


def _merge(lines: list[OcrLine], raw_items: list[dict]) -> list[PhotoItem]:
    """모델 결과를 줄 번호로 맞춘다. 좌표와 원문은 Textract 값만 쓰고, 모델이 빠뜨린 줄은 번역 없이 원문을 둔다."""
    by_index: dict[int, dict] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        index = raw.get("index")
        if isinstance(index, int) and 0 <= index < len(lines) and index not in by_index:
            by_index[index] = raw

    missing = len(lines) - len(by_index)
    if missing:
        logger.warning("사진 번역에서 %d줄이 빠져 원문을 그대로 둡니다.", missing)

    items = []
    for i, line in enumerate(lines):
        raw = by_index.get(i, {})
        translated = raw.get("translated")
        spicy = raw.get("spicy") if isinstance(raw.get("spicy"), bool) else None
        if rule_spicy(line.text):
            spicy = True
        items.append(PhotoItem(
            text_ko=line.text,
            translated=translated.strip() if isinstance(translated, str) and translated.strip() else line.text,
            bbox=line.bbox,
            spicy=spicy,
        ))
    return items


def translate_lines(lines: list[OcrLine], language: Language, client: Any = None) -> list[PhotoItem]:
    """줄마다 번역과 매운맛을 붙인다. 줄이 없으면 모델을 부르지 않는다."""
    if not lines:
        return []
    raw = _fake_items(lines, language) if config.FAKE_LLM else _call_model(lines, language, client or _bedrock_client())
    return _merge(lines, raw)
