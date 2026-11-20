"""일정·세션 저장소 (에이전트 담당).

agent.py, handler.py 는 아래 함수를 쓴다. USE_MOCK=1 이면 메모리, 아니면 DynamoDB(DYNAMODB_TABLE)에 저장한다.
오류는 errors.py 의 예외로 올라오며, api-contract 오류 형식으로 바꾸는 일은 부르는 쪽이 한다.
"""

from app.models.api import AlertsResponse
from app.models.plan import Plan, Profile
from app.storage.errors import (
    InvalidDataError,
    PlanAccessDeniedError,
    PlanAlreadyExistsError,
    PlanNotFoundError,
    SessionNotFoundError,
    StorageError,
)
from app.storage.models import SessionState
from app.storage.service import Storage, get_storage, new_plan_id, new_session_id, reset_mock_store

__all__ = [
    "InvalidDataError",
    "PlanAccessDeniedError",
    "PlanAlreadyExistsError",
    "PlanNotFoundError",
    "SessionNotFoundError",
    "SessionState",
    "Storage",
    "StorageError",
    "create_plan",
    "create_session",
    "get_alerts",
    "get_plan",
    "get_plan_for_session",
    "get_session",
    "get_storage",
    "link_plan",
    "list_plan_ids",
    "new_plan_id",
    "new_session_id",
    "reset_mock_store",
    "save_alerts",
    "update_plan",
]


def create_plan(plan: Plan) -> Plan:
    return get_storage().create_plan(plan)


def get_plan(plan_id: str) -> Plan:
    return get_storage().get_plan(plan_id)


def update_plan(plan: Plan) -> Plan:
    return get_storage().update_plan(plan)


def create_session(profile: Profile, plan_id: str | None = None) -> SessionState:
    return get_storage().create_session(profile, plan_id)


def get_session(session_id: str) -> SessionState:
    return get_storage().get_session(session_id)


def link_plan(session_id: str, plan_id: str) -> SessionState:
    return get_storage().link_plan(session_id, plan_id)


def get_plan_for_session(session_id: str, plan_id: str) -> Plan:
    return get_storage().get_plan_for_session(session_id, plan_id)


def list_plan_ids() -> list[str]:
    return get_storage().list_plan_ids()


def save_alerts(alerts: AlertsResponse) -> AlertsResponse:
    return get_storage().save_alerts(alerts)


def get_alerts(plan_id: str) -> AlertsResponse:
    return get_storage().get_alerts(plan_id)
