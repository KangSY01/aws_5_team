"""Guardian 기반 코드(스펙 작업 1) 확인: 기준값, CheckContext, 테스트용 고정 데이터."""

import datetime as dt
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.guardian import thresholds as th
from app.guardian.context import CheckContext, HourlyWeather, OpeningHours
from guardian_fixtures import BASE_CROWD, BASE_TRAVEL_MIN, DATE, at, load_places, load_sample_plan, make_context


def test_thresholds_are_consistent():
    assert th.CROWD_MEDIUM_RATE < th.CROWD_HIGH_RATE
    assert 0 < th.RAIN_POP_MEDIUM <= 100
    assert 0 < th.RAIN_PTY_HIGH_RATIO <= 1
    assert list(th.SHIFT_STEPS_MIN) == sorted(th.SHIFT_STEPS_MIN)
    assert set(th.WEEKDAY_RULE_SEVERITY) <= set(range(7))
    assert th.MAX_REPAIRS == 3


def test_threshold_place_ids_exist():
    # 장소 ID는 places.json 에 있는 값만 쓴다
    assert th.WEEKDAY_RULE_PLACES <= set(load_places())


def test_weekday_rule_places_are_places_without_concentration():
    # data-rules.md 「혼잡도」: congestion.json 에 없는 장소는 모두 요일 규칙 대상이다
    path = Path(__file__).resolve().parents[1] / "app" / "data" / "congestion.json"
    with_rate = set(json.loads(path.read_text(encoding="utf-8"))["places"])
    assert th.WEEKDAY_RULE_PLACES == set(load_places()) - with_rate


def test_fixture_matches_sample_plan():
    plan = load_sample_plan()
    ctx = make_context()
    assert plan.date == DATE
    # 일정의 장소가 모두 context.places 에 있다
    assert {s.place_id for s in plan.stops} <= set(ctx.places)
    # 고정 데이터의 장소 ID도 places.json 값이다
    ids = {i for pair in BASE_TRAVEL_MIN for i in pair} | set(BASE_CROWD)
    assert ids <= set(ctx.places)
    # 요일 규칙 대상은 집중률에 넣지 않는다. 부산타워만 예외로 가상의 집중률을 두어 기본 상태에서 s3 에 문제가 없게 한다
    assert th.WEEKDAY_RULE_PLACES & set(ctx.crowd) == {"busan-tower"}


def test_fixture_has_enough_transfer_buffer():
    # 기본 context 에서는 tight_transfer 가 생기지 않아야 한다
    plan = load_sample_plan()
    ctx = make_context()
    for prev, stop in zip(plan.stops, plan.stops[1:]):
        travel = ctx.travel(prev.place_id, stop.place_id)
        assert travel is not None
        slack = (stop.start - prev.end).total_seconds() / 60 - travel
        assert slack >= th.TRANSFER_BUFFER_MIN


def test_travel_lookup_is_symmetric():
    ctx = make_context()
    assert ctx.travel("jagalchi-market", "busan-tower") == 10
    assert ctx.travel("busan-tower", "jagalchi-market") == 10
    assert ctx.travel("busan-tower", "busan-tower") == 0
    assert ctx.travel("busan-tower", "beomeosa-temple") is None


def test_overrides_and_missing_data():
    ctx = make_context(weather=None, hours={"busan-tower": OpeningHours(closed_weekdays=[5])})
    assert ctx.weather is None  # 예보 없음 → rain 규칙 건너뜀
    assert ctx.hours["busan-tower"].opens is None  # 모르는 값은 None


def test_weather_validation():
    assert HourlyWeather(time=at(15), pop=80, pty=1).has_precipitation
    assert not HourlyWeather(time=at(15), pop=80).has_precipitation
    with pytest.raises(ValidationError):
        HourlyWeather(time=at(15), pop=120)
    with pytest.raises(ValidationError):
        # 시간대 없는 시각은 받지 않는다
        HourlyWeather(time=dt.datetime(2026, 11, 21, 15), pop=10)


def test_now_requires_timezone():
    with pytest.raises(ValidationError):
        CheckContext(now=dt.datetime(2026, 11, 21, 9), places=load_places())
