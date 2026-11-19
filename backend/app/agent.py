"""Strands Agent 구성 (에이전트 담당). 뼈대 단계: 시그니처만 있고 로직은 없다.

Strands·Bedrock API는 추측하지 말고 공식 문서(.kiro/settings/mcp.json 의 strands, aws-docs) 기준으로 쓴다.
"""

from app.models.api import ChatRequest, ChatResponse


def build_model():
    """Bedrock 모델 객체를 만든다. 핸들러 밖(모듈 로드 시)에서 1회만 호출한다.

    TODO(에이전트 담당):
    - config.MODEL_ID, config.BEDROCK_REGION 사용, max_tokens 설정, 스트리밍 끔
    - config.FAKE_LLM 이면 Bedrock을 호출하지 않는 고정 응답 경로
    """
    raise NotImplementedError("TODO(에이전트 담당)")


def run_chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지 한 건을 처리해 /chat 응답을 만든다. Agent는 요청마다 새로 만든다.

    입력: ChatRequest (session_id, plan_id, message, profile)
    출력: ChatResponse (answer, language, sources, plan_changes)

    TODO(에이전트 담당):
    - app/tools/ 의 도구 등록, 도구 반복 상한 5회
    - 장소명·수치·시간·영업 정보는 도구 결과 값만 사용, sources 에 근거 기록
    - 일정 수정은 plan_edit 도구로만 하고 그 결과를 plan_changes 로 반환
    """
    raise NotImplementedError("TODO(에이전트 담당)")
