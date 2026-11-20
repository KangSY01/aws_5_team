"""Strands Agent 구성과 /chat 처리 (에이전트 담당).

- build_model(): Bedrock 모델 객체. get_model() 이 컨테이너당 첫 요청에서 한 번 만들어 재사용한다.
- run_chat(): 요청 하나를 처리한다. FAKE_LLM=1 이면 고정 응답, 아니면 요청마다 새 Agent 로 실제 모델을 부른다.

역할 분리 (team.md): 모델은 장소를 고르고 문장을 쓴다. 방문 순서·시각(build_plan), 장소 ID 검증, 일정 검증, 저장,
sources, plan_changes 는 코드가 만든다. 모델의 답변은 장소를 [place:ID] 표식으로만 쓰고, 코드가 검증해 이름으로 바꾼다.

저장 시점: 이 함수가 일정을 저장한다(만든 일정, 채팅으로 바꾼 일정). 응답의 plan_changes 가 비어 있지 않으면
프론트엔드는 GET /plan 으로 다시 읽으므로(api-contract), PUT /plan 흐름과 겹치지 않는다. Guardian 해결안은 여기서
저장하지 않는다. 답변 검증이 모두 끝난 뒤에만 저장한다.

Strands·Bedrock API는 추측하지 말고 공식 문서(.kiro/settings/mcp.json 의 strands, aws-docs) 기준으로 쓴다.
"""

import datetime as dt
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from botocore.config import Config as BotocoreConfig
from strands import Agent
from strands.models import BedrockModel
from strands.tools.executors import SequentialToolExecutor

from app import config, storage
from app.chat import answer as chat_answer
from app.chat.messages import message
from app.chat.plan_rules import load_places, place_name, validate_plan
from app.chat.prompt import Mode, build_system_prompt
from app.chat.tools import LOOKUP_TOOLS, MAX_TOOL_CALLS, PlanCreator, ToolRecorder, place_ids_in
from app.guardian.context import resolve_now
from app.models.api import ChatRequest, ChatResponse
from app.models.plan import Language, Plan, StopChange
from app.storage import SessionNotFoundError, SessionState
from app.tools.plan_edit import PlanEditor

logger = logging.getLogger(__name__)

# Bedrock 호출 설정 (team.md: 타임아웃 5초, 재시도 1회, max_tokens 설정)
ALLOWED_REGION = "ap-northeast-2"
MAX_TOKENS = 1024  # 모델 호출 1회당 생성 상한
BEDROCK_TIMEOUT_SEC = 5
BEDROCK_RETRIES = 1  # botocore max_attempts 는 최초 호출을 뺀 재시도 횟수

# 대화 한 건의 한도 (요구사항 6.2, 6.3)
CHAT_TIMEOUT_SEC = 14  # 정상 응답 15초 안에 저장과 응답 조립 시간을 남긴다
MAX_TURNS = MAX_TOOL_CALLS + 3  # 도구 5회 + 한도 안내를 받고도 도구를 부르려는 시도 + 최종 답변

_DATA_DIR = Path(__file__).parent / "data"
_FAKE_RESPONSE_PATH = _DATA_DIR / "chat_response.json"


class ChatError(Exception):
    """대화를 처리하지 못했다. code: timeout, model_error, invalid_model_output.

    handler.py 가 연결되면 api-contract 오류 형식(internal_error, 500)으로 바꾼다. 내부 사유는 응답에 담지 않는다.
    일정을 만들 수 없는 것처럼 사용자가 알아야 하는 실패는 예외가 아니라 사용자 언어의 정상 응답으로 돌려준다.
    """

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def build_model() -> BedrockModel | None:
    """Bedrock 모델 객체를 만든다.

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


_model: BedrockModel | None = None
_model_lock = threading.Lock()


def get_model() -> BedrockModel | None:
    """컨테이너당 첫 요청에서 한 번 만들어 재사용한다. import 때 만들지 않는 것은 리전 오류가 import 를 막지 않게 하려는 것이다."""
    global _model
    with _model_lock:
        if _model is None:
            _model = build_model()
        return _model


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


# ---- 요청 준비: 세션과 일정 ----


@lru_cache(maxsize=1)
def _demo_plan_id() -> str:
    return Plan.model_validate_json((_DATA_DIR / "sample_plan.json").read_text(encoding="utf-8")).plan_id


def _resolve_session(request: ChatRequest) -> SessionState:
    """session_id 가 없거나 모르는 값이면 새 세션을 발급한다 (api-contract). 클라이언트가 준 ID 를 새 세션의 ID 로 쓰지 않는다."""
    if request.session_id:
        try:
            return storage.get_session(request.session_id)
        except SessionNotFoundError:
            logger.warning("알 수 없는 세션 ID 라서 새 세션을 만듭니다.")
    return storage.create_session(request.profile)


def _resolve_plan(request: ChatRequest, session: SessionState) -> Plan | None:
    """이 세션에 연결된 일정만 읽는다. 없는 일정은 PlanNotFoundError, 다른 세션의 일정은 PlanAccessDeniedError(404)."""
    plan_id = request.plan_id or session.plan_id
    if plan_id is None:
        return None
    if config.USE_MOCK and plan_id == _demo_plan_id() and session.plan_id != plan_id:
        # 목 모드의 샘플 일정은 모두가 쓰는 데모 일정이라 어느 세션이든 연결할 수 있다. 실제 저장소에서는 적용하지 않는다
        session = storage.link_plan(session.session_id, plan_id)
    return storage.get_plan_for_session(session.session_id, plan_id)


@dataclass
class _Chat:
    """요청 하나의 상태. 요청 사이에 공유하지 않는다."""

    request: ChatRequest
    session: SessionState
    plan: Plan | None  # 불러온 일정. Stop 이 하나도 없으면 아직 일정이 없는 것으로 본다
    today: dt.date
    mode: Mode
    recorder: ToolRecorder
    creator: PlanCreator | None  # create 모드에서만
    editor: PlanEditor | None  # edit 모드에서만

    @property
    def language(self) -> Language:
        return self.request.profile.language

    @property
    def plan_id(self) -> str:
        return self.creator.plan_id if self.creator else self.editor.current_plan.plan_id


def _prepare(request: ChatRequest) -> _Chat:
    session = _resolve_session(request)
    plan = _resolve_plan(request, session)
    today = resolve_now(request.demo.now if request.demo else None).date()
    recorder = ToolRecorder()
    if plan is not None and plan.stops:
        chat = _Chat(request, session, plan, today, "edit", recorder, creator=None, editor=PlanEditor(plan))
    else:
        creator = PlanCreator(request.profile, today, plan.plan_id if plan else storage.new_plan_id())
        chat = _Chat(request, session, plan, today, "create", recorder, creator=creator, editor=None)
    recorder.on_output(lambda name, data: _on_output(chat, name, data))
    return chat


def _on_output(chat: _Chat, name: str, data: object) -> None:
    """search_places 가 돌려준 장소만 일정 생성·교체·추가 후보가 된다."""
    if name == "search_places":
        (chat.creator or chat.editor).allow_search_results(data)


# ---- 모델 호출 ----


def _converse(chat: _Chat, model: BedrockModel | None) -> tuple[str, str]:
    """요청마다 새 Agent 로 모델을 부른다. (답변 문장, 종료 사유)를 돌려준다. 도구는 순서대로 실행한다."""
    agent = Agent(
        model=model,
        system_prompt=build_system_prompt(
            mode=chat.mode,
            profile=chat.request.profile,
            today=chat.today,
            plan=chat.plan,
            max_tool_calls=MAX_TOOL_CALLS,
        ),
        tools=[*LOOKUP_TOOLS, *(chat.creator or chat.editor).tools],
        hooks=[chat.recorder],
        tool_executor=SequentialToolExecutor(),  # 검색 결과가 나온 뒤에 교체·생성이 실행되게 한다
        callback_handler=None,
    )
    cancel = threading.Event()
    timer = threading.Timer(CHAT_TIMEOUT_SEC, cancel.set)
    timer.daemon = True
    timer.start()
    try:
        result = agent(chat.request.message, limits={"turns": MAX_TURNS}, cancel_signal=cancel)
    except Exception as error:  # 오류 종류만 남긴다. 메시지에 요청 내용이 들어갈 수 있다
        logger.error("모델 호출 실패: %s", type(error).__name__)
        raise ChatError("model_error", f"모델 호출 실패: {type(error).__name__}") from error
    finally:
        timer.cancel()
    if result.stop_reason == "cancelled":
        logger.error("대화 처리 시간이 %d초를 넘어 중단했습니다.", CHAT_TIMEOUT_SEC)
        raise ChatError("timeout", "대화 처리 시간 초과")
    return str(result).strip(), result.stop_reason


# ---- 결과 조립과 저장 ----


def _outcome(chat: _Chat) -> tuple[Plan | None, str | None, list[StopChange]]:
    """(저장할 일정, 사용자에게 줄 안내 키, plan_changes). 일정이 검증을 통과하지 못하면 저장하지 않고 안내만 한다."""
    if chat.mode == "create":
        staged = chat.creator.plan
        if staged is None:
            return None, chat.creator.notice, []
        if validate_plan(staged):
            return None, "plan_invalid", []
        return staged, None, [StopChange(stop_id=s.stop_id, before=None, after=s) for s in staged.stops]
    changes = chat.editor.net_changes()
    if not changes:
        return None, None, []
    final = chat.editor.current_plan
    if validate_plan(final, original=chat.plan):  # 시간 겹침, 잘못된 시간 범위, 없는 장소, 고정 일정 변경
        return None, "plan_invalid", []
    return final, None, changes


def _fallback_text(plan: Plan | None, changes: list[StopChange], language: Language) -> str:
    """모델이 답변 문장을 만들지 못했을 때(도구 호출 한도 등) 이미 확보한 결과만으로 만드는 문장 (요구사항 6.5)."""
    if plan is None:
        return message("incomplete", language)
    if changes and changes[0].before is None and len(changes) == len(plan.stops):
        names = ", ".join(place_name(load_places()[s.place_id], language) for s in plan.stops)
        return message("plan_created", language, count=len(plan.stops), date=plan.date.isoformat(), places=names)
    return message("plan_changed", language, count=len(changes))


def _persist(chat: _Chat, plan: Plan | None) -> None:
    """검증이 끝난 결과를 저장한다. 일정이 만들어지지 않았어도 응답에 줄 plan_id 가 실제로 있도록 빈 일정을 만든다."""
    if chat.mode == "edit":
        if plan is not None:
            storage.update_plan(plan)
        return
    if plan is None:
        if chat.plan is not None:  # 이미 있는 빈 일정이 그대로 plan_id 가 된다
            return
        plan = Plan(plan_id=chat.creator.plan_id, date=chat.today, profile=chat.request.profile, stops=[])
    if chat.plan is None:
        storage.create_plan(plan)
    else:
        storage.update_plan(plan)
    if chat.session.plan_id != plan.plan_id:
        storage.link_plan(chat.session.session_id, plan.plan_id)


def _finish(chat: _Chat, model_text: str) -> ChatResponse:
    language = chat.language
    plan, notice, changes = _outcome(chat)
    searched = {pid for out in chat.recorder.outputs if out.name == "search_places" for pid in place_ids_in(out.data)}
    grounded = searched | {s.place_id for s in (chat.plan.stops if chat.plan else [])}
    grounded |= {s.place_id for s in plan.stops} if plan else set()

    if notice:  # 일정을 만들지 못한 사유를 사용자 언어로 안내한다. 모델의 문장은 쓰지 않는다
        text, referenced = message(notice, language), set()
    elif model_text:
        try:
            text = chat_answer.render_answer(model_text, language, grounded)
        except chat_answer.InvalidAnswer as error:
            logger.error("모델 답변 검증 실패: %s", error)
            raise ChatError("invalid_model_output", "모델 답변이 검증을 통과하지 못했습니다.") from error
        referenced = set(chat_answer.referenced_ids(model_text))
    else:
        text, referenced = _fallback_text(plan, changes, language), set()
    if plan is not None:
        referenced |= {s.place_id for s in plan.stops}
    referenced |= {c.after.place_id for c in changes if c.after is not None}

    try:
        response = ChatResponse.model_validate(
            {
                "session_id": chat.session.session_id,
                "plan_id": chat.plan_id,
                "answer": text,
                "language": language,
                "sources": [s.model_dump() for s in chat_answer.build_sources(chat.recorder.outputs, referenced, language)],
                "plan_changes": [c.model_dump() for c in changes],
            }
        )
    except ValueError as error:
        logger.error("응답이 ChatResponse 검증을 통과하지 못했습니다.")
        raise ChatError("invalid_model_output", "응답 검증 실패") from error
    _persist(chat, plan)  # 응답이 완성된 뒤에만 저장한다
    return response


def _log_summary(chat: _Chat, stop_reason: str) -> None:
    """Agent 실행이 끝날 때 도구 이름별 호출 횟수를 한 번 남긴다 (요구사항 10.3). 메시지·프로필 값은 남기지 않는다."""
    rec = chat.recorder
    logger.info(
        "대화 처리 종료: 모드=%s 도구 호출=%s 실패=%s 한도로 막힌 호출=%d 종료 사유=%s",
        chat.mode, dict(rec.counts), dict(rec.errors), rec.rejected, stop_reason,
    )


def run_chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지 한 건을 처리해 /chat 응답을 만든다. Agent 는 요청마다 새로 만든다.

    입력: ChatRequest (session_id, plan_id, message, profile, demo)
    출력: ChatResponse (answer, language, sources, plan_changes)

    FAKE_LLM=1 이면 Bedrock 을 호출하지 않고 backend/app/data/chat_response.json 의 고정 응답을 돌려준다.
    고정 응답의 answer·language 는 샘플(ja) 그대로다.

    흐름: 세션 확인·발급 → (plan_id 가 있으면) 이 세션의 일정 읽기 → 모드 결정
      - create: 일정이 없거나 Stop 이 0개. search_places 로 고른 place_id 로 create_plan(build_plan) 을 부른다.
      - edit: Stop 이 있는 일정. PlanEditor 도구로 필요한 Stop 만 바꾼다.
    → 답변 검증 → 응답 조립 → 저장. 일정이 만들어지지 않은 대화에도 빈 일정을 하나 만들어 plan_id 를 돌려준다.

    Raises:
        PlanNotFoundError, PlanAccessDeniedError: 없는 일정이거나 이 세션의 일정이 아님 (404)
        ChatError: 모델 오류, 시간 초과, 근거 없는 장소가 든 답변
        StorageError: 저장소 오류
    """
    if config.FAKE_LLM:
        return _fake_response(request)
    chat = _prepare(request)
    stop_reason = "error"
    try:
        text, stop_reason = _converse(chat, get_model())
        return _finish(chat, text)
    finally:
        _log_summary(chat, stop_reason)
