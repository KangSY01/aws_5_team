"""해결안 탐색(repair.py, 스펙 작업 5.2~5.6) 테스트. sample_plan.json 4곳(자갈치 고정) 기준."""

import datetime as dt

from app.guardian.check import check_plan
from app.guardian.context import Event, OpeningHours
from app.guardian.repair import try_move_time
from app.models.plan import Plan, RepairOption
from guardian_fixtures import BASE_TRAVEL_MIN, at, hourly_weather, load_sample_plan, make_context

PLAN = load_sample_plan()  # s1 감천 10:00-11:30 · s2 자갈치(고정) 12:00-13:00 · s3 부산타워 13:30-14:30 · s4 해운대 15:30-17:00
LOCKED = PLAN.stops[1]


def with_stop(plan: Plan, stop_id: str, **update) -> Plan:
    return plan.model_copy(update={"stops": [
        s.model_copy(update=update) if s.stop_id == stop_id else s for s in plan.stops
    ]})


def issue_of(plan: Plan, ctx, issue_id: str):
    return next(i for i in check_plan(plan, ctx) if i.issue_id == issue_id)


def after_of(option: RepairOption, stop_id: str):
    return next(c.after for c in option.changes if c.stop_id == stop_id)


def assert_locked_untouched(option: RepairOption) -> None:
    assert option.metrics.locked_kept is True
    assert LOCKED.stop_id not in {c.stop_id for c in option.changes}


# ---------- 5.2 try_move_time ----------

def test_move_time_rain_shifts_later_and_changed_zero():
    # 15~17시 비 → 해운대 15:30-17:00 전부 비(high). +90분(17:00-18:30)이면 비가 없다.
    # -30·+30·+60 은 비가 남고, -60·-90 은 부산타워 체류가 45분 미만이 되어 안 된다.
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 17)))
    issue = issue_of(PLAN, ctx, "s4-rain")
    assert issue.severity == "high"

    options = try_move_time(PLAN, issue, ctx)

    assert len(options) == 1
    opt = options[0]
    assert opt.action == "move_time"
    assert [c.stop_id for c in opt.changes] == ["s4"]
    moved = after_of(opt, "s4")
    assert (moved.place_id, moved.start, moved.end) == ("haeundae-beach", at(17), at(18, 30))
    # 시각만 바뀌었으므로 변경 0곳 (PR #12)
    m = opt.metrics
    assert (m.changed, m.kept, m.extra_travel_min) == (0, 4, 0)
    assert_locked_untouched(opt)
    assert "s4-rain" not in {i.issue_id for i in check_plan(with_stop(PLAN, "s4", start=moved.start, end=moved.end), ctx)}


def test_move_time_shrinks_previous_neighbor():
    # 부산타워 13:30-15:00(90분), 이동 20분. 16~18시 비 → 해운대 high.
    # -30분(15:00-16:30)이면 비 30분만 남아 medium. 부산타워 끝을 14:30 으로 줄여 자리를 만든다.
    plan = with_stop(PLAN, "s3", end=at(15))
    travel = dict(BASE_TRAVEL_MIN) | {("busan-tower", "haeundae-beach"): 20}
    ctx = make_context(weather=hourly_weather(rain_hours=range(16, 18)), travel_min=travel)
    issue = issue_of(plan, ctx, "s4-rain")
    assert issue.severity == "high"

    opt = try_move_time(plan, issue, ctx)[0]

    assert [c.stop_id for c in opt.changes] == ["s3", "s4"]
    s3, s4 = after_of(opt, "s3"), after_of(opt, "s4")
    assert (s3.place_id, s3.start, s3.end) == ("busan-tower", at(13, 30), at(14, 30))
    assert (s4.start, s4.end) == (at(15), at(16, 30))
    assert opt.metrics.changed == 0
    assert_locked_untouched(opt)


def test_move_time_shrinks_next_neighbor_but_never_locked():
    # 부산타워 14:00 개장 → 13:30-14:30 은 closed high.
    # -30분은 앞이 고정 일정(자갈치)이라 줄일 수 없다. +30분(14:00-15:00)에 해운대 시작을 15:50 으로 늦춘다.
    ctx = make_context(hours={"busan-tower": OpeningHours(opens=dt.time(14))})
    issue = issue_of(PLAN, ctx, "s3-closed")
    assert issue.severity == "high"

    opt = try_move_time(PLAN, issue, ctx)[0]

    s3, s4 = after_of(opt, "s3"), after_of(opt, "s4")
    assert (s3.start, s3.end) == (at(14), at(15))
    assert (s4.place_id, s4.start, s4.end) == ("haeundae-beach", at(15, 50), at(17))
    assert opt.metrics.changed == 0
    assert_locked_untouched(opt)


def test_move_time_none_when_neighbor_would_drop_below_min_dwell():
    # 이동 시간이 길어 어느 폭으로 옮겨도 이웃 체류가 45분 미만이 되거나 비가 남는 경우
    ctx = make_context(weather=hourly_weather(rain_hours=range(14, 20)))
    issue = issue_of(PLAN, ctx, "s4-rain")
    assert try_move_time(PLAN, issue, ctx) == []


def test_move_time_skips_locked_target():
    # 고정 일정(자갈치)의 Issue 는 해결안을 만들지 않는다
    ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
    issue = issue_of(PLAN, ctx, "s2-closed")
    assert issue.severity == "low"
    assert try_move_time(PLAN, issue, ctx) == []


def test_move_time_crowded_without_event_time_evidence():
    # 토요일 감천(요일 규칙)은 하루 단위 근거라 시간 이동을 만들지 않는다 (요구사항 4.3)
    ctx = make_context()
    issue = issue_of(PLAN, ctx, "s1-crowded")
    assert try_move_time(PLAN, issue, ctx) == []


def test_move_time_crowded_with_event_window():
    # 해운대 15:00-17:00 행사 → 체류가 행사 시간대와 겹친다. +90분(17:00-18:30)이면 겹치지 않는다
    event = Event(name="테스트 행사", start=at(15), end=at(17), place_ids=["haeundae-beach"])
    ctx = make_context(events=[event])
    issue = issue_of(PLAN, ctx, "s4-crowded")

    opt = try_move_time(PLAN, issue, ctx)[0]

    s4 = after_of(opt, "s4")
    assert (s4.start, s4.end) == (at(17), at(18, 30))
    assert opt.metrics.changed == 0
    assert_locked_untouched(opt)


def test_move_time_crowded_event_outside_stay():
    # 행사가 18:00 이후면 15:30-17:00 체류와 겹치지 않으므로 시간 이동 근거가 없다
    event = Event(name="테스트 행사", start=at(18), end=at(22), place_ids=["haeundae-beach"])
    ctx = make_context(events=[event])
    issue = issue_of(PLAN, ctx, "s4-crowded")
    assert try_move_time(PLAN, issue, ctx) == []


def test_move_time_prefers_smallest_step_and_respects_now():
    # 감천 11:00 마감 → 10:00-11:30 은 closed high. 뒤로는 고정 일정(자갈치)이 막고 있다.
    hours = {"gamcheon-village": OpeningHours(closes=dt.time(11))}
    # 기준 시각 09:00: -30분(09:30-11:00)이 가장 작은 폭이다
    ctx = make_context(hours=hours)
    opt = try_move_time(PLAN, issue_of(PLAN, ctx, "s1-closed"), ctx)[0]
    s1 = after_of(opt, "s1")
    assert (s1.start, s1.end) == (at(9, 30), at(11))
    # 기준 시각 10:00: 지금보다 이르게 옮길 수 없어 해결안이 없다
    ctx = make_context(now=at(10), hours=hours)
    assert try_move_time(PLAN, issue_of(PLAN, ctx, "s1-closed"), ctx) == []
