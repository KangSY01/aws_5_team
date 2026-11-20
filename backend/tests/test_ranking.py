"""랭킹 엔진 (app/ranking/) 테스트. 수치는 guardian_fixtures 의 테스트용 값이다."""

import datetime as dt

from app.guardian.check import check_plan
from app.guardian.context import HourlyWeather, OpeningHours
from app.models.plan import Plan, Profile
from app.ranking import LockedSlot, rank_orders, rank_places, score_place
from app.ranking import weights as w
from tests.guardian_fixtures import DATE, at, hourly_weather, make_context

PROFILE = Profile(language="ja", interests=["sea"])
SAT = DATE  # 2026-11-21 토요일


# ---------- score_place ----------

def test_unknown_place_is_excluded():
    s = score_place("no-such-place", PROFILE, make_context(), day=SAT)
    assert s.excluded == "unknown_place" and s.total == 0


def test_closed_weekday_and_outside_hours_are_excluded():
    hours = {
        "busan-tower": OpeningHours(closed_weekdays=[SAT.weekday()]),
        "jagalchi-market": OpeningHours(opens=dt.time(9), closes=dt.time(18)),
    }
    ctx = make_context(hours=hours)
    assert score_place("busan-tower", PROFILE, ctx, day=SAT).excluded == "closed_day"
    late = score_place("jagalchi-market", PROFILE, ctx, day=SAT, start=at(17, 30), end=at(18, 30))
    assert late.excluded == "outside_hours"
    ok = score_place("jagalchi-market", PROFILE, ctx, day=SAT, start=at(12), end=at(13))
    assert ok.excluded is None


def test_rank_places_drops_excluded_and_duplicates():
    ctx = make_context(hours={"busan-tower": OpeningHours(closed_weekdays=[SAT.weekday()])})
    ranked = rank_places(
        ["busan-tower", "haeundae-beach", "haeundae-beach", "jagalchi-market"], PROFILE, ctx, day=SAT, limit=None
    )
    assert [s.place_id for s in ranked].count("haeundae-beach") == 1
    assert "busan-tower" not in {s.place_id for s in ranked}


def test_rank_places_drops_previous_place():
    ranked = rank_places(
        ["gamcheon-village", "jagalchi-market"], PROFILE, make_context(), day=SAT,
        prev_place_id="gamcheon-village", limit=None,
    )
    assert [s.place_id for s in ranked] == ["jagalchi-market"]


def test_interest_uses_curation_tags():
    ctx = make_context()
    sea = score_place("haeundae-beach", PROFILE, ctx, day=SAT)
    culture = score_place("gamcheon-village", PROFILE, ctx, day=SAT)
    assert sea.breakdown["interest"] == 1.0 and "interest:sea" in sea.notes
    assert culture.breakdown["interest"] == 0.0


def test_no_interests_is_neutral():
    s = score_place("haeundae-beach", Profile(language="en"), make_context(), day=SAT)
    assert s.breakdown["interest"] == w.NEUTRAL


def test_crowd_follows_guardian_severity():
    # 토요일 집중률 99 → Guardian high
    ctx = make_context(crowd={"haeundae-beach": 99.0})
    busy = score_place("haeundae-beach", PROFILE, ctx, day=SAT)
    assert busy.breakdown["crowd"] == w.SEVERITY_SCORE["high"] and "crowd:high" in busy.notes
    calm = score_place("haeundae-beach", PROFILE, make_context(), day=SAT)  # 70 → 문제 없음
    assert calm.breakdown["crowd"] == 1.0


def test_weather_prefers_indoor_when_raining():
    ctx = make_context(weather=hourly_weather(rain_hours=range(13, 15)))
    outdoor = score_place("haeundae-beach", PROFILE, ctx, day=SAT, start=at(13), end=at(14))
    indoor = score_place("sea-life-busan", PROFILE, ctx, day=SAT, start=at(13), end=at(14))
    assert outdoor.breakdown["weather"] == w.SEVERITY_SCORE["high"] and "rain:high" in outdoor.notes
    assert indoor.breakdown["weather"] == 1.0


def test_weather_without_window_or_forecast_is_neutral():
    assert score_place("haeundae-beach", PROFILE, make_context(), day=SAT).breakdown["weather"] == w.NEUTRAL
    s = score_place("haeundae-beach", PROFILE, make_context(weather=None), day=SAT, start=at(13), end=at(14))
    assert s.breakdown["weather"] == w.NEUTRAL


def test_travel_from_previous_place():
    ctx = make_context()  # 감천 → 자갈치 15분
    s = score_place("jagalchi-market", PROFILE, ctx, day=SAT, prev_place_id="gamcheon-village")
    assert s.breakdown["travel"] == 1 - 15 / w.TRAVEL_SCORE_MAX_MIN and "travel_min:15" in s.notes
    unknown = score_place("songjeong-beach", PROFILE, ctx, day=SAT, prev_place_id="gamcheon-village")
    assert unknown.breakdown["travel"] == w.NEUTRAL and "no_data:travel" in unknown.notes


def test_dispersal_bonus_for_west():
    ctx = make_context()
    assert score_place("gamcheon-village", PROFILE, ctx, day=SAT).breakdown["dispersal"] == 1.0
    assert score_place("haeundae-beach", PROFILE, ctx, day=SAT).breakdown["dispersal"] == 0.0


def test_total_is_0_to_100_and_deterministic():
    ctx = make_context(weather=hourly_weather(rain_hours=range(13, 15)))
    ids = list(ctx.places)
    first = rank_places(ids, PROFILE, ctx, day=SAT, start=at(13), end=at(14), limit=None)
    second = rank_places(ids, PROFILE, ctx, day=SAT, start=at(13), end=at(14), limit=None)
    assert first == second
    assert all(0 <= s.total <= 100 for s in first)
    assert [s.total for s in first] == sorted((s.total for s in first), reverse=True)
    assert len(rank_places(ids, PROFILE, ctx, day=SAT)) == 5


# ---------- rank_orders ----------

A, B, C = "gamcheon-village", "jagalchi-market", "busan-tower"
DWELL = {A: 60, B: 60, C: 60, "haeundae-beach": 60}


def _ctx(**kw):
    # 감천→자갈치 15, 자갈치→부산타워 10, 감천→부산타워 40
    travel = {(A, B): 15, (B, C): 10, (A, C): 40}
    return make_context(travel_min=travel, **kw)


def test_rank_orders_prefers_less_travel():
    best = rank_orders([A, C, B], _ctx(), day=SAT, start_time=dt.time(10), dwell_min=DWELL)
    assert best[0].order == [A, B, C] and best[0].travel_min == 25
    assert best[1].order == [A, C, B] and best[1].travel_min == 50


def test_rank_orders_times_leave_transfer_buffer():
    best = rank_orders([A, B, C], _ctx(), day=SAT, start_time=dt.time(10), dwell_min=DWELL)[0]
    s1, s2, s3 = best.stops
    assert (s1.start, s1.end) == (at(10), at(11))
    assert s2.start == at(11, 30)  # 11:00 + 15 + 10 = 11:25 → 11:30
    plan = Plan(plan_id="p", date=SAT, profile=PROFILE, stops=best.stops)
    assert not [i for i in check_plan(plan, _ctx()) if i.type == "tight_transfer"]


def test_rank_orders_drops_orders_late_for_locked():
    # 부산타워 12:30 고정. A→C(40분)로 바로 가면 11:00+40+10=11:50 → 여유 40분.
    # A→B→C 면 B 11:30-12:30 → C 준비 12:50 → 늦음
    locked = {C: LockedSlot(start=at(12, 30), end=at(13, 30))}
    results = rank_orders([A, B, C], _ctx(), day=SAT, start_time=dt.time(10), dwell_min=DWELL, locked=locked, limit=None)
    assert [r.order for r in results] == [[A, C, B]]
    assert results[0].locked_slack_min == 40
    assert results[0].stops[1].locked and results[0].stops[1].start == at(12, 30)


def test_rank_orders_avoids_rain_for_outdoor():
    # 12~14시 비. 감천(실외) 10:00-12:00 → 두 번째 12:30-13:30(비) → 세 번째 14:00-15:00(맑음).
    # 해운대(실외)와 자갈치(실내) 중 비 오는 두 번째 칸에 실내가 오는 순서가 좋다
    travel = {(A, B): 15, (A, "haeundae-beach"): 15, (B, "haeundae-beach"): 15}
    ctx = make_context(travel_min=travel, weather=hourly_weather(rain_hours=range(12, 14)))
    dwell = {A: 120, B: 60, "haeundae-beach": 60}
    best = rank_orders([A, "haeundae-beach", B], ctx, day=SAT, start_time=dt.time(10), dwell_min=dwell)[0]
    assert best.order == [A, B, "haeundae-beach"] and best.rain_points == 0


def test_rank_orders_out_of_range_returns_empty():
    ctx = _ctx()
    assert rank_orders([A], ctx, day=SAT, start_time=dt.time(10), dwell_min=DWELL) == []
    too_many = list(ctx.places)[: w.MAX_ORDER_PLACES + 1]
    assert rank_orders(too_many, ctx, day=SAT, start_time=dt.time(10), dwell_min={p: 60 for p in too_many}) == []
    locked_first = {A: LockedSlot(start=at(10), end=at(11))}
    assert rank_orders([A, B], ctx, day=SAT, start_time=dt.time(10), dwell_min=DWELL, locked=locked_first) == []


def test_rank_orders_is_deterministic():
    ctx = _ctx(weather=[HourlyWeather(time=at(h), pop=10) for h in range(8, 21)])
    args = dict(day=SAT, start_time=dt.time(10), dwell_min=DWELL, limit=None)
    assert rank_orders([A, B, C], ctx, **args) == rank_orders([A, B, C], ctx, **args)
