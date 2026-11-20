"""AgentCore Runtime 진입점 (1단계: Hello).

/chat 스트리밍 이벤트 순서(delta → done 또는 error)와 본문 형식은 docs/api-contract.md 「스트리밍」을 따른다.
AgentCore SDK는 yield 한 값을 `data: <json>` 줄로만 내보낸다(SSE 이벤트 이름 줄이 없다).
그래서 이벤트 이름은 값 안의 `event` 필드에 넣고, `event: delta` 형식으로 바꾸는 일은 브라우저 앞단 어댑터가 맡는다.

  {"event": "delta", "data": {"text": "..."}}
  {"event": "done",  "data": <ChatResponse>}
  {"event": "error", "data": <ErrorResponse>}

zip 안에서는 이 파일이 루트에 놓이고, backend/app 의 config·models 가 app/ 으로 함께 들어간다(build_zip.py).
"""

import logging

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

from app import config
from app.models.api import ChatDelta, ChatResponse, ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

# 모델 시스템 프롬프트는 영어로 쓴다 (tech.md)
SYSTEM_PROMPT = "You are a friendly travel guide for Busan, South Korea. Reply with one short, warm sentence."
FAKE_CHUNKS = ["Hello! ", "Welcome to Busan."]

# 모델 객체는 모듈 로드 때 1회 만들고, Agent는 요청마다 만든다
MODEL = (
    None
    if config.FAKE_LLM
    else BedrockModel(model_id=config.MODEL_ID, region_name=config.BEDROCK_REGION, max_tokens=256)
)

app = BedrockAgentCoreApp()


def _event(name: str, body) -> dict:
    return {"event": name, "data": body.model_dump(mode="json")}


def _error(code: str, message: str) -> dict:
    return _event("error", ErrorResponse(error=ErrorBody(code=code, message=message)))


async def _text_chunks(message: str):
    """답변 문장 조각을 도착 순서대로 내보낸다. FAKE_LLM=1 이면 Bedrock을 부르지 않는다."""
    if MODEL is None:
        for chunk in FAKE_CHUNKS:
            yield chunk
        return
    agent = Agent(model=MODEL, system_prompt=SYSTEM_PROMPT, callback_handler=None)
    async for event in agent.stream_async(message):
        text = event.get("data")  # Strands 텍스트 조각 이벤트의 키
        if isinstance(text, str) and text:
            yield text


@app.entrypoint
async def invoke(payload, context):
    # prompt 가 문자열이 아니면 도구 호출 블록이 그대로 에이전트에 들어갈 수 있어 반드시 검사한다
    message = payload.get("message", payload.get("prompt", "Hello"))
    if not isinstance(message, str) or not message.strip():
        yield _error("validation_error", "message 는 비어 있지 않은 문자열이어야 합니다.")
        return

    try:
        parts: list[str] = []
        async for text in _text_chunks(message):
            parts.append(text)
            yield _event("delta", ChatDelta(text=text))

        profile = payload.get("profile") or {}
        done = ChatResponse(
            session_id=payload.get("session_id") or getattr(context, "session_id", None) or "hello-session",
            plan_id=payload.get("plan_id") or "hello-plan",
            answer="".join(parts),
            language=profile.get("language", "en"),
            sources=[],
            plan_changes=[],
        )
        yield _event("done", done)
    except Exception:
        logger.exception("Hello 응답 처리 중 오류")
        yield _error("internal_error", "서버 오류가 발생했습니다.")


if __name__ == "__main__":
    app.run()
