"""해결안 탐색(repair.py, 스펙 작업 5.2~5.6) 테스트. sample_plan.json 4곳(자갈치 고정) 기준."""

import datetime as dt

from app.guardian.check import check_plan
from app.guardian.context import Event, OpeningHours
from app.guardian.repair import try_move_time, try_remove, try_reorder, try_replace
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


# ---------- 5.3 try_reorder ----------

# 자갈치→해운대 이동 시간. 기본 고정 데이터에는 없다 (순서를 바꾸면 처음 생기는 구간)
REORDER_TRAVEL = dict(BASE_TRAVEL_MIN) | {("jagalchi-market", "haeundae-beach"): 20}


def test_reorder_swaps_with_previous_neighbor():
    # 15~17시 비 → 해운대 high. 부산타워와 순서를 바꾸면 해운대 13:30-15:00, 부산타워(실내) 16:00-17:00.
    # 두 Stop 이 쓰던 13:30-17:00 구간 안에서만 바뀌고, 이동은 15+20+40=75분(+10분)
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 17)), travel_min=REORDER_TRAVEL)
    issue = issue_of(PLAN, ctx, "s4-rain")

    options = try_reorder(PLAN, issue, ctx)

    assert len(options) == 1
    opt = options[0]
    assert opt.action == "reorder"
    assert [c.stop_id for c in opt.changes] == ["s3", "s4"]
    s3, s4 = after_of(opt, "s3"), after_of(opt, "s4")
    assert (s4.place_id, s4.start, s4.end) == ("haeundae-beach", at(13, 30), at(15))
    assert (s3.place_id, s3.start, s3.end) == ("busan-tower", at(16), at(17))
    m = opt.metrics
    assert (m.changed, m.kept, m.extra_travel_min) == (0, 4, 10)
    assert_locked_untouched(opt)


def test_reorder_dropped_when_extra_travel_over_limit():
    # 자갈치→해운대 45분이면 이동 +35분 > 30분 → 뺀다
    travel = dict(BASE_TRAVEL_MIN) | {("jagalchi-market", "haeundae-beach"): 45}
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 17)), travel_min=travel)
    assert try_reorder(PLAN, issue_of(PLAN, ctx, "s4-rain"), ctx) == []


def test_reorder_dropped_when_travel_unknown():
    # 자갈치→해운대 이동 시간을 모르면 이동 시간 증가를 계산할 수 없어 만들지 않는다
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 17)))
    assert try_reorder(PLAN, issue_of(PLAN, ctx, "s4-rain"), ctx) == []


def test_reorder_never_swaps_with_locked_stop():
    # 감천(s1)의 이웃은 고정 일정(자갈치)뿐이라 순서 변경 해결안이 없다
    ctx = make_context(hours={"gamcheon-village": OpeningHours(closes=dt.time(11))}, travel_min=REORDER_TRAVEL)
    assert try_reorder(PLAN, issue_of(PLAN, ctx, "s1-closed"), ctx) == []


def test_reorder_skips_stop_already_started():
    # 기준 시각 14:00 이면 부산타워(13:30 시작)는 이미 시작했으므로 순서를 바꾸지 않는다
    ctx = make_context(now=at(14), weather=hourly_weather(rain_hours=range(15, 17)), travel_min=REORDER_TRAVEL)
    assert try_reorder(PLAN, issue_of(PLAN, ctx, "s4-rain"), ctx) == []


def test_reorder_crowded_only_with_event_window():
    # 해운대 15:00-17:00 행사. 순서를 바꾸면 해운대 13:30-15:00 이라 행사 시간대를 피한다
    event = Event(name="테스트 행사", start=at(15), end=at(17), place_ids=["haeundae-beach"])
    ctx = make_context(events=[event], travel_min=REORDER_TRAVEL)
    opt = try_reorder(PLAN, issue_of(PLAN, ctx, "s4-crowded"), ctx)[0]
    assert (after_of(opt, "s4").start, after_of(opt, "s4").end) == (at(13, 30), at(15))
    assert opt.metrics.changed == 0
    # 행사가 18시 이후면 시간대 근거가 없어 만들지 않는다
    late = Event(name="테스트 행사", start=at(18), end=at(22), place_ids=["haeundae-beach"])
    ctx = make_context(events=[late], travel_min=REORDER_TRAVEL)
    assert try_reorder(PLAN, issue_of(PLAN, ctx, "s4-crowded"), ctx) == []


# ---------- 5.4 try_replace ----------

def travel_with(**extra: int) -> dict:
    """기본 이동 시간 + 부산타워에서 후보 장소까지 이동 시간. 인자 이름의 _ 는 - 로 바꾼다."""
    return dict(BASE_TRAVEL_MIN) | {("busan-tower", name.replace("_", "-")): m for name, m in extra.items()}


def test_replace_rain_with_indoor_place_like_contract_example():
    # 계약 예시와 같은 장면: 15~18시 비, 해운대 → 신세계 센텀시티(실내), 이동 +5분
    # 광안리(같은 beach)는 실외라 비가 남아 빠지고, 자갈치·부산타워는 이미 일정에 있어 후보가 아니다
    ctx = make_context(
        weather=hourly_weather(rain_hours=range(15, 18)),
        travel_min=travel_with(shinsegae_centum_city=45, gwangalli_beach=30),
    )
    issue = issue_of(PLAN, ctx, "s4-rain")

    options = try_replace(PLAN, issue, ctx)

    assert [after_of(o, "s4").place_id for o in options] == ["shinsegae-centum-city"]
    opt = options[0]
    assert opt.action == "replace"
    s4 = after_of(opt, "s4")
    assert (s4.start, s4.end) == (PLAN.stops[3].start, PLAN.stops[3].end)  # 시각은 그대로
    m = opt.metrics
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (1, 3, 5, True)
    assert_locked_untouched(opt)


def test_replace_crowded_with_same_category_only():
    # 토요일 해운대 집중률 96 → crowded high. 같은 beach 인 광안리로만 바꾼다 (실내 장소는 비 문제일 때만)
    ctx = make_context(
        crowd={"jagalchi-market": 60.0, "busan-tower": 50.0, "haeundae-beach": 96.0},
        travel_min=travel_with(gwangalli_beach=30, shinsegae_centum_city=45),
    )
    issue = issue_of(PLAN, ctx, "s4-crowded")
    assert issue.severity == "high"

    options = try_replace(PLAN, issue, ctx)

    assert [after_of(o, "s4").place_id for o in options] == ["gwangalli-beach"]
    assert options[0].metrics.extra_travel_min == -10


def test_replace_excludes_over_limit_and_unknown_travel():
    # 광안리 +35분(30분 초과), 신세계 이동 시간 모름 → 후보 없음
    ctx = make_context(
        weather=hourly_weather(rain_hours=range(15, 18)),
        crowd={"jagalchi-market": 60.0, "busan-tower": 50.0, "haeundae-beach": 96.0},
        travel_min=travel_with(gwangalli_beach=75),
    )
    assert try_replace(PLAN, issue_of(PLAN, ctx, "s4-crowded"), ctx) == []
    assert try_replace(PLAN, issue_of(PLAN, ctx, "s4-rain"), ctx) == []


def test_replace_skips_locked_target_and_no_candidate():
    # 고정 일정(자갈치)은 바꾸지 않는다
    ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
    assert try_replace(PLAN, issue_of(PLAN, ctx, "s2-closed"), ctx) == []
    # 감천은 places.json 에서 유일한 village 라 같은 분류 후보가 없다
    ctx = make_context()
    assert try_replace(PLAN, issue_of(PLAN, ctx, "s1-crowded"), ctx) == []


# ---------- 5.5 try_remove ----------

def test_remove_first_stop_like_contract_example():
    # 계약 예시 s1-crowded: 감천을 빼면 이동 65 → 50분 (-15), 변경 1곳 · 3곳 유지
    ctx = make_context()
    options = try_remove(PLAN, issue_of(PLAN, ctx, "s1-crowded"), ctx)

    assert len(options) == 1
    opt = options[0]
    assert opt.action == "remove"
    assert [(c.stop_id, c.before, c.after) for c in opt.changes] == [("s1", PLAN.stops[0], None)]
    m = opt.metrics
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (1, 3, -15, True)
    assert_locked_untouched(opt)


def test_remove_middle_stop_keeps_other_times():
    # 부산타워(s3)를 빼면 자갈치→해운대 20분: 15+20=35분 (-30). 다른 Stop 시각은 그대로
    ctx = make_context(hours={"busan-tower": OpeningHours(opens=dt.time(14))}, travel_min=REORDER_TRAVEL)
    opt = try_remove(PLAN, issue_of(PLAN, ctx, "s3-closed"), ctx)[0]
    assert [c.stop_id for c in opt.changes] == ["s3"]
    assert opt.metrics.extra_travel_min == -30


def test_remove_skips_locked_target():
    ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
    assert try_remove(PLAN, issue_of(PLAN, ctx, "s2-closed"), ctx) == []