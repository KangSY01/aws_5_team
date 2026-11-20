"""Strands Agent 구성 (에이전트 담당).

작업 1 범위: 모델 생성(build_model)과 FAKE_LLM 고정 응답 경로.
도구 등록, sources·plan_changes 수집, 일정 저장은 작업 3~5에서 채운다.

Strands·Bedrock API는 추측하지 말고 공식 문서(.kiro/settings/mcp.json 의 strands, aws-docs) 기준으로 쓴다.
"""

import logging
from functools import lru_cache
from pathlib import Path

from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

from app import config
from app.models.api import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

# Bedrock 호출 설정 (team.md: 타임아웃 5초, 재시도 1회, max_tokens 설정)
ALLOWED_REGION = "ap-northeast-2"
MAX_TOKENS = 1024  # 모델 호출 1회당 생성 상한
BEDROCK_TIMEOUT_SEC = 5
BEDROCK_RETRIES = 1  # botocore max_attempts 는 최초 호출을 뺀 재시도 횟수

_FAKE_RESPONSE_PATH = Path(__file__).parent / "data" / "chat_response.json"


def build_model() -> BedrockModel | None:
    """Bedrock 모델 객체를 만든다. Agent 를 요청마다 만드는 것과 달리 모델은 컨테이너당 1회만 만든다.

    FAKE_LLM=1 이면 Bedrock 을 쓰지 않으므로 None 을 돌려준다.
    리전이 ap-northeast-2 가 아니면 한국어 오류 로그를 남기고 RuntimeError 를 발생시킨다.
    모델 ID 는 config.MODEL_ID(BEDROCK_MODEL_ID), 리전은 config.BEDROCK_REGION(AWS_REGION)에서 읽는다.
    """
    if config.FAKE_LLM:
        logger.info("FAKE_LLM=1 이므로 Bedrock 모델을 만들지 않습니다.")
        return None

    if config.BEDROCK_REGION != ALLOWED_REGION:
        logger.error(
            "Bedrock 리전은 %s 만 허용합니다. 현재 AWS_REGION: %s", ALLOWED_REGION, config.BEDROCK_REGION
        )
        raise RuntimeError(f"AWS_REGION 은 {ALLOWED_REGION} 이어야 합니다 (현재: {config.BEDROCK_REGION}).")

    client_config = BotocoreConfig(
        connect_timeout=BEDROCK_TIMEOUT_SEC,
        read_timeout=BEDROCK_TIMEOUT_SEC,
        retries={"max_attempts": BEDROCK_RETRIES, "mode": "standard"},
    )
    return BedrockModel(
        model_id=config.MODEL_ID,
        region_name=config.BEDROCK_REGION,
        max_tokens=MAX_TOKENS,
        streaming=True,  # /chat 의 delta 이벤트를 위해 모델 스트리밍을 켠다
        boto_client_config=client_config,
    )


@lru_cache(maxsize=1)
def _load_fake_response() -> ChatResponse:
    return ChatResponse.model_validate_json(_FAKE_RESPONSE_PATH.read_text(encoding="utf-8"))


def _fake_response(request: ChatRequest) -> ChatResponse:
    """고정 응답. 대화가 이어지도록 session_id, plan_id 만 요청 값을 따른다 (없으면 샘플 값)."""
    base = _load_fake_response()
    return base.model_copy(
        update={
            "session_id": request.session_id or base.session_id,
            "plan_id": request.plan_id or base.plan_id,
        },
        deep=True,  # 호출자가 결과를 고쳐도 다음 응답에 영향이 없게 한다
    )


def run_chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지 한 건을 처리해 /chat 응답을 만든다. Agent는 요청마다 새로 만든다.

    입력: ChatRequest (session_id, plan_id, message, profile)
    출력: ChatResponse (answer, language, sources, plan_changes)

    FAKE_LLM=1 이면 Bedrock 을 호출하지 않고 backend/app/data/chat_response.json 의 고정 응답을 돌려준다.
    고정 응답의 answer·language 는 샘플(ja) 그대로다.

    TODO(에이전트 담당, 작업 3~5):
    - app/tools/ 의 도구 등록, 도구 반복 상한 5회
    - 장소명·수치·시간·영업 정보는 도구 결과 값만 사용, sources 에 근거 기록
    - 일정 수정은 plan_edit 도구로만 하고 그 결과를 plan_changes 로 반환
    """
    if config.FAKE_LLM:
        return _fake_response(request)
    raise NotImplementedError("실제 모델 경로는 작업 4에서 구현합니다. 지금은 FAKE_LLM=1 로 실행하세요.")
