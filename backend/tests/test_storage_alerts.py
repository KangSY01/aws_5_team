"""일정 목록 조회와 예약 점검 알림(sk=ALERTS) 저장·조회. AWS 자격 증명과 네트워크 없이 돈다.

메모리 백엔드와 DynamoDB 백엔드(가짜 테이블 주입)에서 같은 테스트를 돈다.
"""

import datetime as dt
import logging

import pytest
from botocore.exceptions import ClientError

from app import storage
from app.models.api import AlertsResponse
from app.models.plan import Issue
from app.storage.backends import MemoryBackend
from app.storage.dynamodb import DynamoBackend
from app.storage.errors import InvalidDataError, PlanNotFoundError, StorageError
from app.storage.service import Storage
from tests.test_storage import Clock, FakeTable, make_plan, make_profile

KST = dt.timezone(dt.timedelta(hours=9))
CHECKED = dt.datetime(2026, 11, 21, 9, 15, tzinfo=KST)
RAIN = Issue(issue_id="s4-rain", type="rain", stop_id="s4", severity="high", detail="15:30-17:00 강수확률 80%, 실외 장소")
CROWD = Issue(issue_id="s1-crowded", type="crowded", stop_id="s1", severity="medium", detail="토요일 혼잡 예상(요일 규칙)")


def alerts(plan_id="plan-a", checked_at=CHECKED, issues=(RAIN,)) -> AlertsResponse:
    return AlertsResponse(plan_id=plan_id, checked_at=checked_at, issues=list(issues))


@pytest.fixture(params=["memory", "dynamodb"])
def store(request) -> Storage:
    backend = MemoryBackend() if request.param == "memory" else DynamoBackend(FakeTable())
    return Storage(backend, clock=Clock())


def raw(store: Storage, pk: str, sk: str) -> dict | None:
    backend = store._backend
    items = backend._items if isinstance(backend, MemoryBackend) else backend._table.items
    return items.get((pk, sk))


# ---- 알림 저장·조회 ----


def test_alerts_save_then_get(store):
    store.create_plan(make_plan())
    store.save_alerts(alerts(issues=(RAIN, CROWD)))
    loaded = store.get_alerts("plan-a")
    assert loaded == alerts(issues=(RAIN, CROWD))
    assert loaded.checked_at.isoformat() == "2026-11-21T09:15:00+09:00"


def test_alerts_before_any_check_are_empty(store):
    store.create_plan(make_plan())
    assert store.get_alerts("plan-a") == AlertsResponse(plan_id="plan-a", checked_at=None, issues=[])


def test_alerts_of_a_missing_plan_are_plan_not_found_and_nothing_is_stored(store):
    with pytest.raises(PlanNotFoundError):
        store.get_alerts("plan-none")
    with pytest.raises(PlanNotFoundError):
        store.save_alerts(alerts("plan-none"))
    assert raw(store, "PLAN#plan-none", "ALERTS") is None


def test_a_new_check_overwrites_the_previous_result(store):
    store.create_plan(make_plan())
    store.save_alerts(alerts(issues=(RAIN, CROWD)))
    later = CHECKED + dt.timedelta(hours=3)
    store.save_alerts(alerts(checked_at=later, issues=()))  # 비가 그쳐 문제가 없어졌다

    assert store.get_alerts("plan-a") == alerts(checked_at=later, issues=())
    backend = store._backend
    items = backend._items if isinstance(backend, MemoryBackend) else backend._table.items
    assert [key for key in items if key[1] == "ALERTS"] == [("PLAN#plan-a", "ALERTS")]  # 같은 키 하나뿐


def test_saving_alerts_never_touches_the_plan_item(store):
    store.create_plan(make_plan())
    before_item, before_plan = dict(raw(store, "PLAN#plan-a", "META")), store.get_plan("plan-a")

    store.save_alerts(alerts())
    store.save_alerts(alerts(checked_at=CHECKED + dt.timedelta(hours=3)))

    assert raw(store, "PLAN#plan-a", "META") == before_item  # updated_at 까지 그대로
    assert store.get_plan("plan-a") == before_plan
    store.update_plan(make_plan())  # 일정 수정도 알림을 지우지 않는다
    assert store.get_alerts("plan-a").issues == [RAIN]


def test_alerts_of_different_plans_do_not_mix(store):
    store.create_plan(make_plan("plan-a"))
    store.create_plan(make_plan("plan-b"))
    store.save_alerts(alerts("plan-a", issues=(RAIN,)))
    assert store.get_alerts("plan-b").checked_at is None
    store.save_alerts(alerts("plan-b", issues=(CROWD,)))
    assert [i.issue_id for i in store.get_alerts("plan-a").issues] == ["s4-rain"]


def test_invalid_alerts_are_rejected(store):
    store.create_plan(make_plan())
    with pytest.raises(InvalidDataError):
        store.save_alerts(alerts().model_dump(mode="json"))  # 모델이 아니라 dict
    broken = AlertsResponse.model_construct(plan_id="plan-a", checked_at="not-a-time", issues=[])
    with pytest.raises(InvalidDataError):
        store.save_alerts(broken)
    with pytest.raises(InvalidDataError):
        store.get_alerts("")
    assert store.get_alerts("plan-a").checked_at is None  # 아무것도 저장하지 않았다


def test_stored_alerts_that_no_longer_match_the_model_are_a_storage_error(store, caplog):
    store.create_plan(make_plan())
    store.save_alerts(alerts())
    raw(store, "PLAN#plan-a", "ALERTS")["checked_at"] = "not-a-time"
    with caplog.at_level(logging.ERROR, logger="app.storage.service"):
        with pytest.raises(StorageError):
            store.get_alerts("plan-a")
    assert "알림" in caplog.text and "not-a-time" not in caplog.text


def test_dynamodb_alert_item_shape(store):
    if isinstance(store._backend, MemoryBackend):
        pytest.skip("DynamoDB 항목 모양 확인")
    store.create_plan(make_plan())
    store.save_alerts(alerts(issues=(RAIN,)))
    item = raw(store, "PLAN#plan-a", "ALERTS")
    assert set(item) == {"pk", "sk", "plan_id", "checked_at", "issues", "updated_at"}
    assert item["checked_at"] == "2026-11-21T09:15:00+09:00" and item["issues"][0]["issue_id"] == "s4-rain"


# ---- 일정 목록 ----


def test_list_plan_ids_returns_only_plans_sorted(store):
    for plan_id in ("plan-c", "plan-a", "plan-b"):
        store.create_plan(make_plan(plan_id))
    store.create_session(make_profile(), plan_id="plan-a")  # 세션 항목은 목록에 없다
    store.save_alerts(alerts("plan-a"))  # 알림 항목(sk=ALERTS)도 없다
    store.save_alerts(alerts("plan-b"))

    assert store.list_plan_ids() == ["plan-a", "plan-b", "plan-c"]


def test_list_plan_ids_of_an_empty_store(store):
    assert store.list_plan_ids() == []


def test_list_plan_ids_reads_every_page_of_the_scan():
    table = FakeTable()
    table.page_size = 2
    store = Storage(DynamoBackend(table), clock=Clock())
    for n in range(5):
        store.create_plan(make_plan(f"plan-{n}"))
    store.create_session(make_profile(), plan_id="plan-0")
    store.save_alerts(alerts("plan-3"))

    assert store.list_plan_ids() == [f"plan-{n}" for n in range(5)]
    scans = [kwargs for name, kwargs in table.calls if name == "scan"]
    assert len(scans) > 1 and scans[0]["ExclusiveStartKey"] is None and scans[1]["ExclusiveStartKey"] is not None
    assert all(kwargs["ConsistentRead"] is True for kwargs in scans)


@pytest.mark.parametrize("action", ["list", "save", "get"])
def test_dynamodb_failures_in_alert_operations_become_storage_errors(action, caplog):
    table = FakeTable()
    store = Storage(DynamoBackend(table), clock=Clock())
    store.create_plan(make_plan())
    table.fail_with = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "secret-detail"}}, "Op")
    calls = {"list": store.list_plan_ids, "save": lambda: store.save_alerts(alerts()), "get": lambda: store.get_alerts("plan-a")}

    with caplog.at_level(logging.ERROR, logger="app.storage.dynamodb"):
        with pytest.raises(StorageError) as error:
            calls[action]()

    assert not isinstance(error.value, PlanNotFoundError) and "secret-detail" not in str(error.value)
    assert "DynamoDB" in caplog.text and "secret-detail" not in caplog.text and "plan-a" not in caplog.text


# ---- 모듈 함수 (agent.py, handler.py, 예약 점검 Lambda 가 쓴다) ----


def test_module_level_functions_use_the_current_store(api_storage):
    api_storage.create_plan(make_plan("plan-m"))
    assert "plan-m" in storage.list_plan_ids()
    storage.save_alerts(alerts("plan-m"))
    assert storage.get_alerts("plan-m") == alerts("plan-m")
    assert storage.get_alerts("plan-1").checked_at is None  # 샘플 일정: 아직 점검 전
