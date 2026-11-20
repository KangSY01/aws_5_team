"""예약 점검 Lambda(app/scheduled_handler.py). D 의 run_scheduled_check 를 저장소에 연결한 부분만 본다. AWS·네트워크 없음.

저장소는 conftest.py 의 api_storage(샘플 일정 plan-1 이 든 메모리 저장소)다. 조회 도구는 날씨가 없는 상태로 고정해
(실제 예보는 키가 없다) 점검 결과가 요일 규칙(토요일 감천문화마을)만 남도록 한다.
"""

import datetime as dt
import json
import logging

import pytest

from app import config, storage
from app.guardian import service as guardian_service
from app.guardian.scheduled import check_one
from app.models.plan import Plan
from app.scheduled_handler import handler

NOW = "2026-11-21T09:00:00+09:00"  # 샘플 일정(11/21)의 방문일


@pytest.fixture(autouse=True)
def no_weather(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)  # 샘플 예보를 쓰지 않는다. 환경 변수와 무관하게 고정
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "")  # 실제 예보 호출도 하지 않는다


@pytest.fixture(autouse=True)
def no_repairs(monkeypatch):
    """예약 점검은 해결안을 만들지 않는다. Guardian 의 해결안 조립(run_check)이 불리면 실패한다."""
    monkeypatch.setattr(guardian_service, "run_check", lambda *a, **k: pytest.fail("예약 점검이 해결안을 만들었다"))


def copy_of_sample(api_storage, plan_id: str) -> Plan:
    plan = api_storage.get_plan("plan-1").model_copy(update={"plan_id": plan_id})
    api_storage.create_plan(plan)
    return plan


def issue_ids(plan_id: str) -> list[str]:
    return [i.issue_id for i in storage.get_alerts(plan_id).issues]


def test_manual_run_with_plan_ids_checks_and_saves_those_plans(api_storage):
    result = handler({"plan_ids": ["plan-1"], "now": NOW})

    saved = storage.get_alerts("plan-1")
    expected = check_one(api_storage.get_plan("plan-1"), dt.datetime.fromisoformat(NOW))  # D 의 점검 결과를 기준으로 비교한다
    assert saved == expected  # D 가 찾은 문제가 개수·순서 그대로 저장된다
    assert result == {
        "requested": 1,
        "saved": 1,
        "results": [{"plan_id": "plan-1", "checked_at": NOW, "issues": len(saved.issues)}],
    }
    json.dumps(result)  # Lambda 반환값이라 JSON 으로 바꿀 수 있어야 한다


def test_only_the_given_plans_are_checked(api_storage):
    copy_of_sample(api_storage, "plan-2")

    handler({"plan_ids": ["plan-2"], "now": NOW})

    assert storage.get_alerts("plan-2").checked_at is not None
    assert storage.get_alerts("plan-1").checked_at is None  # 지정하지 않은 일정은 그대로


def test_without_plan_ids_every_stored_plan_is_checked(api_storage):
    copy_of_sample(api_storage, "plan-2")

    result = handler({"now": NOW})

    assert result["requested"] == 2 and sorted(r["plan_id"] for r in result["results"]) == ["plan-1", "plan-2"]
    assert storage.get_alerts("plan-1").checked_at is not None and storage.get_alerts("plan-2").checked_at is not None


@pytest.mark.parametrize("event", [None, {}, "text", []])
def test_empty_or_odd_events_check_every_stored_plan(api_storage, event):
    assert handler(event)["requested"] == 1  # 날짜 필터는 D 의 코드가 한다. 여기서는 목록을 그대로 넘긴다


def test_explicit_empty_plan_ids_checks_nothing(api_storage):
    assert handler({"plan_ids": []}) == {"requested": 0, "saved": 0, "results": []}


def test_the_date_filter_belongs_to_the_guardian_code(api_storage):
    result = handler({"now": "2026-12-31T09:00:00+09:00"})  # 11/21 일정은 지난 일정이다

    assert result["requested"] == 1 and result["saved"] == 0  # D 의 is_due 가 건너뛴다
    assert storage.get_alerts("plan-1").checked_at is None  # 저장하지 않는다


def test_rechecking_overwrites_the_previous_result_and_keeps_the_plan(api_storage):
    before = api_storage.get_plan("plan-1")
    handler({"plan_ids": ["plan-1"], "now": NOW})
    handler({"plan_ids": ["plan-1"], "now": "2026-11-21T14:15:00+09:00"})

    alerts = storage.get_alerts("plan-1")
    assert alerts.checked_at.isoformat() == "2026-11-21T14:15:00+09:00"  # 두 번째 결과만 남는다
    assert [key for key in api_storage._backend._items if key[1] == "ALERTS"] == [("PLAN#plan-1", "ALERTS")]
    assert api_storage.get_plan("plan-1") == before  # 일정은 그대로


def test_one_failing_plan_does_not_stop_the_others(api_storage, caplog):
    copy_of_sample(api_storage, "plan-ok")
    copy_of_sample(api_storage, "plan-bad")
    api_storage._backend._items[("PLAN#plan-bad", "META")]["plan"]["date"] = "not-a-date"  # 저장된 데이터가 깨졌다

    with caplog.at_level(logging.ERROR):
        result = handler({"plan_ids": ["plan-bad", "plan-1", "plan-ok", "plan-missing"], "now": NOW})

    assert result["requested"] == 4 and sorted(r["plan_id"] for r in result["results"]) == ["plan-1", "plan-ok"]
    assert "plan-bad" in caplog.text and "plan-missing" in caplog.text  # 실패한 일정 ID 가 로그에 남는다
    assert storage.get_alerts("plan-ok").checked_at is not None


def test_a_save_failure_for_one_plan_does_not_stop_the_others(api_storage, monkeypatch):
    copy_of_sample(api_storage, "plan-2")
    original = storage.save_alerts

    def flaky(alerts):
        if alerts.plan_id == "plan-1":
            raise storage.StorageError("down")
        return original(alerts)

    monkeypatch.setattr(storage, "save_alerts", flaky)

    result = handler({"plan_ids": ["plan-1", "plan-2"], "now": NOW})

    assert [r["plan_id"] for r in result["results"]] == ["plan-2"]


@pytest.mark.parametrize(
    "event",
    [{"plan_ids": "plan-1"}, {"plan_ids": [1]}, {"plan_ids": [""]}, {"plan_ids": [None]}, {"now": "tomorrow"}, {"now": 5}],
)
def test_malformed_events_fail_loudly_and_change_nothing(api_storage, event):
    with pytest.raises(ValueError):
        handler(event)
    assert storage.get_alerts("plan-1").checked_at is None


def test_duplicate_plan_ids_are_checked_once(api_storage):
    assert handler({"plan_ids": ["plan-1", "plan-1"], "now": NOW})["requested"] == 1


def test_naive_now_is_read_as_korean_time(api_storage):
    handler({"plan_ids": ["plan-1"], "now": "2026-11-21T09:00:00"})
    assert storage.get_alerts("plan-1").checked_at.isoformat() == "2026-11-21T09:00:00+09:00"


def test_a_storage_failure_while_listing_plans_is_not_swallowed(api_storage, monkeypatch):
    def down():
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "list_plan_ids", down)
    with pytest.raises(storage.StorageError):
        handler({})


def test_demo_now_environment_setting_is_used_when_the_event_has_no_now(api_storage, monkeypatch):
    monkeypatch.setattr(config, "DEMO_NOW", "2026-11-21T13:00:00+09:00")
    handler({"plan_ids": ["plan-1"]})
    assert storage.get_alerts("plan-1").checked_at.isoformat() == "2026-11-21T13:00:00+09:00"
