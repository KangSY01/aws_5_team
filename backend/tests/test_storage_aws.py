"""실제 DynamoDB 테이블에 대한 저장소 통합 테스트. 기본 실행에서는 건너뛴다.

같은 시나리오(run_scenario)를 두 곳에서 돌린다.
- 메모리 백엔드: 항상 실행. AWS 없이 시나리오 자체가 맞는지 확인한다.
- 실제 DynamoDB: RUN_AWS_STORAGE_TEST=1 일 때만 실행. 자격 증명이 필요하다.

실제 테이블 실행 (PowerShell, backend/ 에서). 기존 데이터와 겹치지 않도록 매번 새 ID(plan-itest-*)를 쓰고, 끝나면 만든 항목을 지운다.
  $env:RUN_AWS_STORAGE_TEST="1"; $env:DYNAMODB_TABLE="busan-guide-sessions"; $env:AWS_REGION="ap-northeast-2"
  uv run --with "botocore[crt]" pytest -q tests/test_storage_aws.py
(aws login 으로 받은 자격 증명을 쓰면 botocore[crt] 가 필요하다. 키를 쓰는 프로필이면 --with 는 없어도 된다.)
"""

import os
import uuid
from collections.abc import Callable

import boto3
import pytest

from app import config
from app.models.plan import Plan, Profile
from app.storage.backends import MemoryBackend
from app.storage.dynamodb import DynamoBackend
from app.storage.errors import PlanAccessDeniedError, PlanAlreadyExistsError, PlanNotFoundError, SessionNotFoundError
from app.storage.service import Storage
from tests.test_storage import make_plan, make_profile

RawGet = Callable[[str], dict | None]


def run_scenario(store: Storage, raw_get: RawGet, created_pks: list[str], tag: str) -> None:
    """일정 저장·조회·수정, 세션 생성·조회, 연결, 격리. 만든 항목의 pk 를 created_pks 에 모은다."""
    plan_a, plan_b = f"plan-itest-{tag}-a", f"plan-itest-{tag}-b"

    # 일정 저장 후 조회
    created_pks.append(f"PLAN#{plan_a}")
    store.create_plan(make_plan(plan_a))
    assert store.get_plan(plan_a) == make_plan(plan_a)
    item = raw_get(f"PLAN#{plan_a}")  # 단일 테이블 항목 모양
    assert item["sk"] == "META" and isinstance(item["plan"], dict) and item["plan"]["plan_id"] == plan_a

    # 같은 ID 로 다시 만들면 조건부 쓰기가 막는다
    with pytest.raises(PlanAlreadyExistsError):
        store.create_plan(make_plan(plan_a))

    # 일정 수정 후 재조회 (고정 Stop 은 그대로)
    changed = make_plan(plan_a)
    changed.stops[3] = changed.stops[3].model_copy(update={"place_id": "shinsegae-centum-city"})
    store.update_plan(changed)
    reloaded = store.get_plan(plan_a)
    assert reloaded == changed and reloaded.stops[1].locked is True

    # 없는 일정: 조회·수정 모두 오류이고 수정이 항목을 만들지 않는다
    missing = f"plan-itest-{tag}-missing"
    with pytest.raises(PlanNotFoundError):
        store.get_plan(missing)
    with pytest.raises(PlanNotFoundError):
        store.update_plan(make_plan(missing))
    assert raw_get(f"PLAN#{missing}") is None

    # 세션 생성·조회
    session_a = store.create_session(make_profile("ja"))
    created_pks.append(f"SESSION#{session_a.session_id}")
    assert store.get_session(session_a.session_id) == session_a
    with pytest.raises(SessionNotFoundError):
        store.get_session(f"sess-itest-{tag}-missing")

    # 세션과 일정 연결
    linked = store.link_plan(session_a.session_id, plan_a)
    assert linked.plan_id == plan_a and linked.profile == session_a.profile
    assert linked.created_at == session_a.created_at and linked.updated_at >= session_a.updated_at
    assert store.get_plan_for_session(session_a.session_id, plan_a) == changed

    # 세션 간 격리
    created_pks.append(f"PLAN#{plan_b}")
    store.create_plan(make_plan(plan_b))
    session_b = store.create_session(make_profile("en"), plan_id=plan_b)
    created_pks.append(f"SESSION#{session_b.session_id}")
    with pytest.raises(PlanAccessDeniedError):
        store.get_plan_for_session(session_a.session_id, plan_b)
    with pytest.raises(PlanAccessDeniedError):
        store.get_plan_for_session(session_b.session_id, plan_a)
    assert store.get_session(session_a.session_id).profile.language == "ja"
    assert store.get_session(session_b.session_id).profile.language == "en"


def test_scenario_on_memory_backend():
    backend = MemoryBackend()
    run_scenario(Storage(backend), backend.get, [], uuid.uuid4().hex[:8])


@pytest.mark.skipif(os.environ.get("RUN_AWS_STORAGE_TEST") != "1", reason="실제 DynamoDB 테스트: RUN_AWS_STORAGE_TEST=1 일 때만 실행")
def test_scenario_on_real_dynamodb(monkeypatch):
    table_name = os.environ.get("DYNAMODB_TABLE", "")
    assert table_name, "DYNAMODB_TABLE 을 설정하세요."
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "DYNAMODB_TABLE", table_name)
    assert config.BEDROCK_REGION == "ap-northeast-2", "AWS_REGION 은 ap-northeast-2 여야 합니다."

    backend = DynamoBackend.from_config()  # 운영과 같은 경로(타임아웃·재시도 설정 포함)
    table = backend._table
    created_pks: list[str] = []
    try:
        run_scenario(Storage(backend), backend.get, created_pks, uuid.uuid4().hex[:8])
    finally:
        for pk in created_pks:  # 이 테스트가 만든 항목만 지운다
            table.delete_item(Key={"pk": pk, "sk": "META"})
