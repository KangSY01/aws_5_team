"""지연 재조정(delay.py, 스펙 작업 6) 테스트. sample_plan.json 4곳(자갈치 고정) 기준."""

import datetime as dt

from app.guardian import thresholds as th
from app.guardian.context import OpeningHours
from app.guardian.delay import propose_delay_repairs
from app.models.plan import RepairOption
from guardian_fixtures import BASE_TRAVEL_MIN, at, load_sample_plan, make_context

PLAN = load_sample_plan()  # s1 감천 10:00-11:30 · s2 자갈치(고정) 12:00-13:00 · s3 부산타워 13:30-14:30 · s4 해운대 15:30-17:00
LOCKED = PLAN.stops[1]
# 부산타워→해운대 20분이면 계약 예시(/plan/{plan_id}/delay)와 같은 결과가 나온다
SHORT_TRAVEL = dict(BASE_TRAVEL_MIN) | {("busan-tower", "haeundae-beach"): 20}


def times(option: RepairOption) -> dict[str, tuple[dt.datetime, dt.datetime] | None]:
    return {c.stop_id: (c.after.start, c.after.end) if c.after else None for c in option.changes}


def summary(options: list[RepairOption]) -> list[tuple[str, tuple[str, ...], int, int]]:
    """(action, 바뀐 stop_id, changed, extra_travel_min) 목록."""
    return [
        (o.action, tuple(c.stop_id for c in o.changes), o.metrics.changed, o.metrics.extra_travel_min)
        for o in options
    ]


def assert_locked_untouched(option: RepairOption, locked_id: str = LOCKED.stop_id) -> None:
    assert option.metrics.locked_kept is True
    assert locked_id not in {c.stop_id for c in option.changes}


# ---------- move_time: 미루기와 체류 단축 ----------

def test_delay_like_contract_example():
    # 13:40 에 30분 지연: 부산타워 14:00-15:00, 해운대는 간격 여유(30분)로 흡수해 그대로
    ctx = make_context(now=at(13, 40), travel_min=SHORT_TRAVEL)
    opt = propose_delay_repairs(PLAN, 30, ctx)[0]

    assert opt.action == "move_time"
    assert times(opt) == {"s3": (at(14), at(15))}
    m = opt.metrics
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (0, 4, 0, True)


def test_delay_pushes_next_stop_only_as_needed():
    # 부산타워→해운대 40분이면 해운대는 15:50 이후에 시작해야 한다 (20분만 미룸)
    ctx = make_context(now=at(13, 40))
    opt = propose_delay_repairs(PLAN, 30, ctx)[0]
    assert times(opt) == {"s3": (at(14), at(15)), "s4": (at(15, 50), at(17, 20))}
    assert opt.metrics.changed == 0


def test_delay_keeps_finished_stops():
    # 13:40 기준으로 이미 끝난 감천(s1)은 어떤 해결안에서도 바꾸지 않는다
    ctx = make_context(now=at(13, 40))
    for opt in propose_delay_repairs(PLAN, 30, ctx):
        assert "s1" not in times(opt)


def test_delay_shrinks_dwell_before_locked_stop():
    # 10:15 에 30분 지연: 감천 10:30 시작. 자갈치(고정) 12:00 에 가려면 11:35 까지 나와야 하므로 체류를 65분으로 줄인다
    ctx = make_context(now=at(10, 15))
    opt = propose_delay_repairs(PLAN, 30, ctx)[0]
    assert times(opt) == {"s1": (at(10, 30), at(11, 35))}
    assert_locked_untouched(opt)


def test_delay_shrinks_several_stops_closest_to_locked_first():
    # 해운대(s4)를 고정하고 자갈치는 풀었다. 12:40 에 45분 지연.
    # 미루기만 하면 해운대 앞에서 25분 모자란다 → 부산타워 60→45분, 자갈치 60→50분
    plan = PLAN.model_copy(update={"stops": [
        s.model_copy(update={"locked": s.stop_id == "s4"}) for s in PLAN.stops
    ]})
    ctx = make_context(now=at(12, 40))
    opt = propose_delay_repairs(plan, 45, ctx)[0]

    assert times(opt) == {"s2": (at(12, 45), at(13, 35)), "s3": (at(13, 55), at(14, 40))}
    assert_locked_untouched(opt, "s4")
    assert opt.metrics.changed == 0


# ---------- 노션 데모 대본 장면 6: 체류 단축 안 다음에 1곳 빼는 안 ----------

def test_delay_offers_remove_after_move_time():
    # 13:40 에 30분 지연. 첫 안은 시간만(변경 0곳), 다음 안은 해운대를 빼는 안(변경 1곳, 이동 -40분)
    # 부산타워를 빼는 안은 자갈치→해운대 이동 시간을 몰라 만들지 않는다
    ctx = make_context(now=at(13, 40))
    options = propose_delay_repairs(PLAN, 30, ctx)
    assert summary(options) == [
        ("move_time", ("s3", "s4"), 0, 0),
        ("remove", ("s3", "s4"), 1, -40),
    ]
    assert times(options[1]) == {"s3": (at(14), at(15)), "s4": None}


def test_delay_remove_when_shrink_is_not_enough():
    # 10:15 에 60분 지연: 감천을 45분까지 줄여도 자갈치(고정)에 늦는다 → 감천을 빼는 안만 남는다
    ctx = make_context(now=at(10, 15))
    options = propose_delay_repairs(PLAN, 60, ctx)
    assert summary(options) == [("remove", ("s1",), 1, -15)]
    assert_locked_untouched(options[0])


# ---------- reorder·replace: move_time 이 안 될 때만 ----------

HAEUNDAE_CLOSES = {"haeundae-beach": OpeningHours(closes=dt.time(17, 30))}
FALLBACK_TRAVEL = dict(BASE_TRAVEL_MIN) | {
    ("jagalchi-market", "haeundae-beach"): 20,
    ("busan-tower", "gwangalli-beach"): 40,
}


def test_delay_reorder_and_replace_only_when_move_time_fails(monkeypatch):
    # 해운대 17:30 마감. 13:40 에 60분 지연이면 미루기만 해서는 해운대가 16:20-17:50 이라 운영시간 밖이다.
    #  - reorder: 해운대 14:30-16:00 → 부산타워 16:50-17:50 (이동 +10분)
    #  - replace: 해운대 → 광안리(같은 beach), 시각 16:20-17:50 (이동 +0분)
    #  - remove: 해운대 빼기(-40분), 부산타워 빼기(-30분)
    monkeypatch.setattr(th, "MAX_REPAIRS", 5)
    ctx = make_context(now=at(13, 40), hours=HAEUNDAE_CLOSES, travel_min=FALLBACK_TRAVEL)
    options = propose_delay_repairs(PLAN, 60, ctx)

    assert summary(options) == [
        ("reorder", ("s3", "s4"), 0, 10),
        ("remove", ("s3", "s4"), 1, -40),
        ("remove", ("s3",), 1, -30),
        ("replace", ("s3", "s4"), 1, 0),
    ]
    assert times(options[0]) == {"s3": (at(16, 50), at(17, 50)), "s4": (at(14, 30), at(16))}
    replaced = next(c.after for c in options[3].changes if c.stop_id == "s4")
    assert (replaced.place_id, replaced.start, replaced.end) == ("gwangalli-beach", at(16, 20), at(17, 50))
    for opt in options:
        assert_locked_untouched(opt)


def test_delay_returns_at_most_max_repairs_and_no_fallback_when_move_works():
    ctx = make_context(now=at(13, 40), hours=HAEUNDAE_CLOSES, travel_min=FALLBACK_TRAVEL)
    assert len(propose_delay_repairs(PLAN, 60, ctx)) == th.MAX_REPAIRS
    # 30분 지연은 미루기로 되므로 reorder·replace 를 찾지 않는다
    actions = {o.action for o in propose_delay_repairs(PLAN, 30, ctx)}
    assert actions <= {"move_time", "remove"}
    assert "move_time" in actions


# ---------- 공통 ----------

def test_delay_skips_options_that_create_closed_issue():
    # 부산타워 15:00 마감. 30분 지연(14:00-15:00)은 되지만 60분 지연은 어떤 안도 운영시간·이동 시간 조건을 못 맞춘다
    hours = {"busan-tower": OpeningHours(closes=dt.time(15))}
    ctx = make_context(now=at(13, 40), travel_min=SHORT_TRAVEL, hours=hours)
    assert times(propose_delay_repairs(PLAN, 30, ctx)[0]) == {"s3": (at(14), at(15))}
    assert propose_delay_repairs(PLAN, 60, ctx) == []


def test_delay_nothing_left_to_adjust():
    # 18:00 이면 남은 비고정 Stop 이 없다
    assert propose_delay_repairs(PLAN, 30, make_context(now=at(18))) == []


def test_delay_never_touches_locked_and_accepts_dict_context():
    ctx = make_context(now=at(9), travel_min=FALLBACK_TRAVEL)
    for delay in (10, 20, 30, 45, 60, 90, 120):
        for opt in propose_delay_repairs(PLAN, delay, ctx):
            assert_locked_untouched(opt)
    first = propose_delay_repairs(PLAN, 20, ctx)
    assert propose_delay_repairs(PLAN, 20, ctx.model_dump()) == first
