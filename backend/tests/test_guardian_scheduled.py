"""예약 점검(scheduled.py, 스펙 작업 11) 테스트. 저장소·조회 도구는 가짜로 넘긴다."""

import datetime as dt
from types import SimpleNamespace

from app.guardian.scheduled import check_one, is_due, run_scheduled_check
from app.models.api import AlertsResponse
from guardian_fixtures import at, load_sample_plan

PLAN = load_sample_plan()  # 2026-11-21 (토)
RAIN_15_18 = {"date": "2026-11-21", "hourly": [
    {"time": at(h).isoformat(), "pop": 80 if 15 <= h < 18 else 20, "pty": 1 if 15 <= h < 18 else 0}
    for h in range(8, 21)
]}


def lookups(weather=None):
    """예보만 주는 가짜 조회 도구. 나머지 도구는 없다 (그 규칙만 건너뜀)."""
    return SimpleNamespace(get_weather=lambda date: weather or {"date": date, "hourly": []})


def store(*plans):
    saved: dict[str, AlertsResponse] = {}
    by_id = {p.plan_id: p for p in plans}

    def load_plan(plan_id):
        return by_id[plan_id]  # 없으면 KeyError

    def save_result(result):
        saved[result.plan_id] = result

    return load_plan, save_result, saved


def test_is_due_only_within_forecast_range():
    assert is_due(PLAN, at(9))  # 당일
    assert is_due(PLAN, at(9) - dt.timedelta(days=3))  # 3일 전
    assert not is_due(PLAN, at(9) - dt.timedelta(days=4))  # 예보 범위 밖
    assert not is_due(PLAN, at(9) + dt.timedelta(days=1))  # 지난 일정


def test_check_one_has_alerts_shape_without_repairs():
    result = check_one(PLAN, at(9), lookups(RAIN_15_18))
    assert isinstance(result, AlertsResponse)
    assert result.checked_at == at(9)
    assert [(i.issue_id, i.severity) for i in result.issues] == [("s4-rain", "high"), ("s1-crowded", "medium")]
    AlertsResponse.model_validate_json(result.model_dump_json())  # 계약 형식


def test_run_saves_due_plans_and_skips_others():
    far = PLAN.model_copy(update={"plan_id": "plan-far", "date": dt.date(2026, 12, 25)})
    load_plan, save, saved = store(PLAN, far)

    results = run_scheduled_check(["plan-1", "plan-far"], load_plan, save, now=at(9), lookups=lookups(RAIN_15_18))

    assert [r.plan_id for r in results] == ["plan-1"]
    assert set(saved) == {"plan-1"}
    assert saved["plan-1"].issues[0].issue_id == "s4-rain"


def test_run_continues_after_one_plan_fails():
    load_plan, save, saved = store(PLAN)
    results = run_scheduled_check(["no-such-plan", "plan-1"], load_plan, save, now=at(9), lookups=lookups())
    assert [r.plan_id for r in results] == ["plan-1"]
    assert set(saved) == {"plan-1"}


def test_run_continues_after_save_fails():
    load_plan, _, _ = store(PLAN)

    def broken_save(result):
        raise RuntimeError("DynamoDB 오류")

    assert run_scheduled_check(["plan-1"], load_plan, broken_save, now=at(9), lookups=lookups()) == []


def test_run_never_calls_llm_or_changes_plan():
    # 점검만 한다: 일정은 그대로이고, 결과에 해결안 필드가 없다 (요구사항 5.1·8.2)
    load_plan, save, saved = store(PLAN)
    before = PLAN.model_copy(deep=True)
    run_scheduled_check(["plan-1"], load_plan, save, now=at(9), lookups=lookups(RAIN_15_18))
    assert PLAN == before
    assert "repairs" not in saved["plan-1"].model_dump()
