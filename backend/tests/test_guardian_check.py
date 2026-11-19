"""check_plan(스펙 작업 3) 테스트: 결정적 issue_id, 고정 일정 low 제한, 정렬, 데이터 없는 규칙 건너뛰기."""

import datetime as dt

from app.guardian import rules
from app.guardian.check import check_plan
from app.guardian.context import OpeningHours
from guardian_fixtures import at, hourly_weather, load_sample_plan, make_context

PLAN = load_sample_plan()  # 11/21(토) 감천 · 자갈치(고정) · 부산타워 · 해운대


def ids(issues):
    return [(i.issue_id, i.severity) for i in issues]


def with_stop(plan, stop_id, **update):
    stops = [s.model_copy(update=update) if s.stop_id == stop_id else s for s in plan.stops]
    return plan.model_copy(update={"stops": stops})


def test_baseline_only_weekday_rule():
    assert ids(check_plan(PLAN, make_context())) == [("s1-crowded", "medium")]


def test_no_issues_returns_empty():
    # 월요일(11/23)로 옮기면 요일 규칙도 해당 없음
    shift = dt.timedelta(days=2)
    stops = [s.model_copy(update={"start": s.start + shift, "end": s.end + shift}) for s in PLAN.stops]
    plan = PLAN.model_copy(update={"stops": stops, "date": dt.date(2026, 11, 23)})
    assert check_plan(plan, make_context(now=at(9) + shift)) == []


def test_rain_high_on_haeundae():
    issues = check_plan(PLAN, make_context(weather=hourly_weather(rain_hours=range(15, 18))))
    assert ids(issues) == [("s4-rain", "high"), ("s1-crowded", "medium")]


def test_indoor_busan_tower_not_flagged_in_rain():
    issues = check_plan(PLAN, make_context(weather=hourly_weather(rain_hours=range(13, 15))))
    assert all(i.stop_id != "s3" for i in issues)


def test_locked_stop_capped_to_low():
    ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
    issue = next(i for i in check_plan(PLAN, ctx) if i.stop_id == "s2")
    assert issue.issue_id == "s2-closed" and issue.severity == "low"
    assert "고정 일정" in issue.detail and "high" in issue.detail


def test_tight_transfer_high():
    # 부산타워 14:30 끝 → 해운대 15:00 시작(간격 30분), 이동 40분
    plan = with_stop(PLAN, "s4", start=at(15), end=at(16, 30))
    assert ("s4-tight_transfer", "high") in ids(check_plan(plan, make_context()))


def test_sort_by_severity_then_start_then_type():
    ctx = make_context(
        weather=hourly_weather(rain_hours=range(15, 18)),  # s4 rain high
        hours={"busan-tower": OpeningHours(closed_weekdays=[5])},  # s3 closed high
        crowd={"haeundae-beach": 90, "jagalchi-market": 60, "busan-tower": 50},  # s4 crowded medium
    )
    assert ids(check_plan(PLAN, ctx)) == [
        ("s3-closed", "high"),  # high 중 시작이 이른 쪽
        ("s4-rain", "high"),
        ("s1-crowded", "medium"),  # medium 중 시작이 이른 쪽
        ("s4-crowded", "medium"),
    ]


def test_same_input_same_issue_ids():
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 18)))
    assert ids(check_plan(PLAN, ctx)) == ids(check_plan(PLAN, ctx))


def test_unsorted_stops_use_time_order():
    # stops 순서가 섞여 있어도 시각 순서로 이웃을 정한다
    plan = PLAN.model_copy(update={"stops": list(reversed(PLAN.stops))})
    assert ids(check_plan(plan, make_context())) == ids(check_plan(PLAN, make_context()))


def test_missing_data_skips_rules():
    ctx = make_context(weather=None, crowd={}, hours={}, travel_min={})
    # 집중률·예보·영업 정보·이동 시간이 모두 없으면 요일 규칙만 남는다
    assert ids(check_plan(PLAN, ctx)) == [("s1-crowded", "medium")]


def test_failing_rule_is_skipped(monkeypatch):
    def broken(stop, ctx):
        raise RuntimeError("테스트용 실패")

    monkeypatch.setattr(rules, "check_crowded", broken)
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 18)))
    assert ids(check_plan(PLAN, ctx)) == [("s4-rain", "high")]


def test_dict_context_accepted():
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 18)))
    assert ids(check_plan(PLAN, ctx.model_dump())) == ids(check_plan(PLAN, ctx))
