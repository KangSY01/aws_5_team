"""일정·세션 저장 규칙. 저장 매체(메모리/DynamoDB)는 backends 가 맡는다.

키 구조 (단일 테이블, pk + sk):
  일정  pk=PLAN#<plan_id>        sk=META  plan(Plan 의 JSON 맵), updated_at
  세션  pk=SESSION#<session_id>  sk=META  SessionState 필드 (session_id, plan_id, profile, created_at, updated_at)

규칙:
- 쓰기 전에 Pydantic 모델로 다시 검증한다. 읽을 때도 검증하고, 맞지 않으면 StorageError.
- place_id 가 places.json 에 있는지는 보지 않는다 (에이전트·API 계층의 일).
- 동시 수정은 마지막 쓰기가 이긴다 (버전 필드 없음).
- 일정은 plan_id 를 아는 쪽이 읽을 수 있다. 세션 간 격리는 get_plan_for_session 이 맡는다.
- created_at, updated_at 은 기록용 시각이라 실제 시각을 쓴다 (DEMO_NOW 를 따르지 않는다). 테스트는 clock 을 주입한다.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app import config
from app.models.plan import Plan, Profile
from app.storage.backends import Backend, ItemExists, ItemMissing, MemoryBackend
from app.storage.errors import (
    InvalidDataError,
    PlanAccessDeniedError,
    PlanAlreadyExistsError,
    PlanNotFoundError,
    SessionNotFoundError,
    StorageError,
)
from app.storage.models import SessionState

logger = logging.getLogger(__name__)

_SAMPLE_PLAN_PATH = Path(__file__).parent.parent / "data" / "sample_plan.json"


def new_plan_id() -> str:
    return f"plan-{uuid.uuid4().hex}"


def new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex}"


def _plan_pk(plan_id: str) -> str:
    return f"PLAN#{plan_id}"


def _session_pk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDataError(f"{name} 는 비어 있지 않은 문자열이어야 합니다.")
    return value


def _field_paths(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())


def _validated[T: BaseModel](model: type[T], value: Any) -> T:
    """모델 인스턴스를 직렬화했다가 다시 검증한 복사본. model_construct 나 필드 대입으로 깨진 값도 걸러낸다."""
    if not isinstance(value, model):
        raise InvalidDataError(f"{model.__name__} 모델이 필요합니다.")
    try:
        return model.model_validate(value.model_dump(mode="json", warnings=False))
    except ValidationError as error:
        raise InvalidDataError(f"{model.__name__} 검증 실패: {_field_paths(error)}") from error
    except ValueError as error:  # 직렬화할 수 없는 값
        raise InvalidDataError(f"{model.__name__} 을 직렬화할 수 없습니다.") from error


def _load[T: BaseModel](model: type[T], data: Any, what: str) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        logger.error("저장된 %s 데이터가 모델과 맞지 않습니다: %s", what, _field_paths(error))
        raise StorageError("저장된 데이터가 올바르지 않습니다.") from error


class Storage:
    def __init__(self, backend: Backend, clock: Callable[[], datetime] | None = None):
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ---- 일정 ----

    def create_plan(self, plan: Plan) -> Plan:
        """새 일정을 저장한다. 같은 plan_id 가 이미 있으면 PlanAlreadyExistsError."""
        plan = _validated(Plan, plan)
        _require_id(plan.plan_id, "plan_id")
        try:
            self._backend.create(_plan_pk(plan.plan_id), self._plan_attrs(plan))
        except ItemExists:
            raise PlanAlreadyExistsError(plan.plan_id) from None
        return plan

    def get_plan(self, plan_id: str) -> Plan:
        """없으면 PlanNotFoundError."""
        _require_id(plan_id, "plan_id")
        item = self._backend.get(_plan_pk(plan_id))
        if item is None:
            raise PlanNotFoundError(plan_id)
        return _load(Plan, item.get("plan"), "일정")

    def update_plan(self, plan: Plan) -> Plan:
        """있는 일정을 통째로 바꾼다 (PUT /plan). 없으면 PlanNotFoundError."""
        plan = _validated(Plan, plan)
        _require_id(plan.plan_id, "plan_id")
        try:
            self._backend.replace(_plan_pk(plan.plan_id), self._plan_attrs(plan))
        except ItemMissing:
            raise PlanNotFoundError(plan.plan_id) from None
        return plan

    def _plan_attrs(self, plan: Plan) -> dict[str, Any]:
        return {"plan": plan.model_dump(mode="json"), "updated_at": self._clock().isoformat()}

    def _require_plan_exists(self, plan_id: str) -> None:
        if self._backend.get(_plan_pk(plan_id)) is None:
            raise PlanNotFoundError(plan_id)

    # ---- 세션 ----

    def create_session(self, profile: Profile, plan_id: str | None = None) -> SessionState:
        """새 세션을 만들고 session_id 를 발급한다. plan_id 를 주면 그 일정이 있어야 한다."""
        profile = _validated(Profile, profile)
        if plan_id is not None:
            self._require_plan_exists(_require_id(plan_id, "plan_id"))
        now = self._clock()
        state = SessionState(
            session_id=new_session_id(), plan_id=plan_id, profile=profile, created_at=now, updated_at=now
        )
        try:
            self._backend.create(_session_pk(state.session_id), state.model_dump(mode="json"))
        except ItemExists:
            logger.error("세션 ID 가 충돌했습니다.")
            raise StorageError("세션을 만들지 못했습니다.") from None
        return state

    def get_session(self, session_id: str) -> SessionState:
        """없으면 SessionNotFoundError."""
        _require_id(session_id, "session_id")
        item = self._backend.get(_session_pk(session_id))
        if item is None:
            raise SessionNotFoundError(session_id)
        return _load(SessionState, {name: item.get(name) for name in SessionState.model_fields}, "세션")

    def link_plan(self, session_id: str, plan_id: str) -> SessionState:
        """세션에 일정을 연결한다. 이미 연결돼 있으면 바꾼다. 일정이 없으면 PlanNotFoundError."""
        _require_id(session_id, "session_id")
        _require_id(plan_id, "plan_id")
        self._require_plan_exists(plan_id)
        try:
            self._backend.update(
                _session_pk(session_id), {"plan_id": plan_id, "updated_at": self._clock().isoformat()}
            )
        except ItemMissing:
            raise SessionNotFoundError(session_id) from None
        return self.get_session(session_id)

    def get_plan_for_session(self, session_id: str, plan_id: str) -> Plan:
        """세션에 연결된 일정만 돌려준다. 다른 일정이면 PlanAccessDeniedError (404 와 같게 변환)."""
        _require_id(plan_id, "plan_id")
        session = self.get_session(session_id)
        if session.plan_id != plan_id:
            logger.warning("세션에 연결되지 않은 일정 요청을 거부했습니다.")
            raise PlanAccessDeniedError(plan_id)
        return self.get_plan(plan_id)


# ---- 프로세스 단위 저장소 (agent.py, handler.py 가 쓴다) ----

_storage: Storage | None = None
_storage_is_mock: bool | None = None
_lock = threading.Lock()


def _mock_storage(seed: bool) -> Storage:
    storage = Storage(MemoryBackend())
    if seed:  # USE_MOCK=1 에서 plan-1 을 읽을 수 있게 한다 (요구사항 9.1)
        storage.create_plan(Plan.model_validate_json(_SAMPLE_PLAN_PATH.read_text(encoding="utf-8")))
    return storage


def _build_storage() -> Storage:
    if config.USE_MOCK:
        return _mock_storage(seed=True)
    from app.storage.dynamodb import DynamoBackend  # 목 모드에서는 boto3 를 불러오지 않는다

    return Storage(DynamoBackend.from_config())


def get_storage() -> Storage:
    """컨테이너(프로세스)당 하나. USE_MOCK 값이 바뀌면 새로 만든다."""
    global _storage, _storage_is_mock
    with _lock:
        if _storage is None or _storage_is_mock != config.USE_MOCK:
            _storage = _build_storage()
            _storage_is_mock = config.USE_MOCK
        return _storage


def reset_mock_store(seed: bool = True) -> None:
    """목 저장소를 처음 상태로 되돌린다 (테스트용). seed=True 면 sample_plan.json 의 일정이 들어 있다."""
    global _storage, _storage_is_mock
    if not config.USE_MOCK:
        raise RuntimeError("reset_mock_store 는 USE_MOCK=1 에서만 쓸 수 있습니다.")
    with _lock:
        _storage = _mock_storage(seed)
        _storage_is_mock = True
