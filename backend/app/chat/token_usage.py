"""Bedrock 토큰 사용량 기록 (/chat 요청 하나 단위).

- 값은 Strands Agent 의 event_loop_metrics.accumulated_usage 에서 읽는다. Strands BedrockModel 이 ConverseStream 응답의
  metadata.usage(inputTokens, outputTokens, totalTokens)를 모델 호출마다 더해 둔 값이다. Agent 를 요청마다 새로 만들므로
  이 값이 곧 요청 하나에서 부른 모든 Bedrock 호출의 합계다.
- 로그에는 요청 유형, 토큰 수, 호출 횟수만 남긴다. 메시지·프롬프트·프로필 값은 남기지 않는다.
- 측정이나 로그가 실패해도 예외를 밖으로 내보내지 않는다 (대화 처리가 우선이다).

CloudWatch (Lambda LogFormat JSON): message 는 아래 JSON 문자열이고, 같은 키가 extra 로 로그 객체 최상위에도 들어간다.
  fields operation, input_tokens, output_tokens, total_tokens, bedrock_calls | filter event = "BEDROCK_TOKEN_USAGE"
"""

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

EVENT = "BEDROCK_TOKEN_USAGE"
# 대화 모드 → 로그의 요청 유형. create 는 새 일정(또는 일정 없는 상태의 질문), edit 는 기존 일정이 있는 상태의 대화
OPERATIONS = {"create": "plan_create", "edit": "plan_edit"}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    bedrock_calls: int
    # 프롬프트 캐시를 쓰면 Bedrock 이 따로 알려 주는 값. 지금은 캐시를 쓰지 않아 보통 0 이다
    cache_read_input_tokens: int = 0
    cache_write_input_tokens: int = 0


def _int(usage: Any, key: str) -> int:
    value = usage.get(key, 0) if isinstance(usage, dict) else 0
    return value if isinstance(value, int) and value >= 0 else 0


def usage_from_agent(agent: Any, bedrock_calls: int) -> TokenUsage | None:
    """Agent 한 번 실행의 누적 사용량. 읽을 수 없으면 None (예외를 내지 않는다)."""
    try:
        usage = agent.event_loop_metrics.accumulated_usage
        return TokenUsage(
            input_tokens=_int(usage, "inputTokens"),
            output_tokens=_int(usage, "outputTokens"),
            total_tokens=_int(usage, "totalTokens"),
            bedrock_calls=max(int(bedrock_calls), 0),
            cache_read_input_tokens=_int(usage, "cacheReadInputTokens"),
            cache_write_input_tokens=_int(usage, "cacheWriteInputTokens"),
        )
    except Exception:  # 측정 실패가 대화를 막지 않게 한다
        logger.warning("Bedrock 토큰 사용량을 읽지 못했습니다.")
        return None


def log_usage(mode: str, usage: TokenUsage | None, stop_reason: str) -> None:
    """BEDROCK_TOKEN_USAGE 구조화 로그 한 줄. usage 가 None 이면 남기지 않는다."""
    if usage is None:
        return
    try:
        payload = {"event": EVENT, "operation": OPERATIONS.get(mode, mode), **asdict(usage), "stop_reason": stop_reason}
        logger.info(json.dumps(payload, ensure_ascii=False), extra=payload)
    except Exception:
        logger.warning("Bedrock 토큰 사용량 로그를 남기지 못했습니다.")
