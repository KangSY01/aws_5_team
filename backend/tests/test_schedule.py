"""일정 생성(app/tools/schedule.py) 테스트. 네트워크를 쓰지 않는다(places.json·travel_times.json 만 읽는다)."""

import datetime as dt
import logging
import re

import pytest

from app.models.plan import Profile
from app.storage.service import new_plan_id
from app.tools import schedule
from app.tools.schedule import PlanBuildError, build_plan

KST = dt.timezone(dt.timedelta(hours=9))
PROFILE = Profile(language="en")
SAMPLE = ["gamcheon-village", "jagalchi-market", "busan-tower", "haeundae-beach"]
DAY = dt.date(2026, 11, 28)


def without_id(plan):
    return plan.model_dump(exclude={"plan_id"})


def test_same_input_gives_same_stops():
    first = build_plan(SAMPLE, DAY, dt.time(10, 0), PROFILE)
    assert without_id(first) == without_id(build_plan(SAMPLE, DAY, dt.time(10, 0), PROFILE))
    # 문자열로 주거나 start 를 생략(기본 10:00)해도 같다
    assert without_id(first) == without_id(build_plan(SAMPLE, "2026-11-28", "10:00", PROFILE))
    assert without_id(first) == without_id(build_plan(SAMPLE, DAY, None, PROFILE))
    # plan_id 를 넘기면 그대로 쓰고 stops 는 같다
    given = build_plan(SAMPLE, DAY, None, PROFILE, plan_id="plan-from-storage")
    assert given.plan_id == "plan-from-storage" and without_id(given) == without_id(first)


def test_plan_id_없으면_저장소와_같은_형식의_무작위_ID():
    first, second = (build_plan(SAMPLE, DAY, None, PROFILE) for _ in range(2))
    for plan in (first, second):
        assert re.fullmatch(r"plan-[0-9a-f]{32}", plan.plan_id)
    assert first.plan_id != second.plan_id  # 입력이 같아도 ID 는 다르다 (추측할 수 없게)
    assert re.fullmatch(r"plan-[0-9a-f]{32}", new_plan_id())  # 저장소 형식이 바뀌면 여기서 드러난다


def test_unknown_removed_duplicates_removed(caplog):
    with caplog.at_level(logging.WARNING, logger=schedule.__name__):
        plan = build_plan(["busan-tower", "no-such-place", "jagalchi-market", "busan-tower"], DAY, None, PROFILE)
    assert sorted(s.place_id for s in plan.stops) == ["busan-tower", "jagalchi-market"]
    assert [s.stop_id for s in plan.stops] == ["s1", "s2"]
    assert "no-such-place" in caplog.text


@pytest.mark.parametrize("place_ids", [[], ["no-such-place"]])
def test_no_valid_places_raises(place_ids):
    with pytest.raises(PlanBuildError) as e:
        build_plan(place_ids, DAY, None, PROFILE)
    assert e.value.code == "no_valid_places"


def test_bad_date_or_start_raises():
    with pytest.raises(PlanBuildError) as e:
        build_plan(SAMPLE, "11/28", None, PROFILE)
    assert e.value.code == "invalid_date"
    with pytest.raises(PlanBuildError) as e:
        build_plan(SAMPLE, DAY, "10시", PROFILE)
    assert e.value.code == "invalid_start"


def test_times_do_not_overlap_have_timezone_and_round_to_10_min():
    plan = build_plan(SAMPLE, DAY, "10:05", PROFILE)
    stops = plan.stops
    assert stops[0].start == dt.datetime(2026, 11, 28, 10, 5, tzinfo=KST)  # 첫 Stop 은 start 그대로
    for stop in stops:
        assert stop.start < stop.end
        assert stop.start.utcoffset() == stop.end.utcoffset() == dt.timedelta(hours=9)
        assert not stop.locked
    for prev, nxt in zip(stops, stops[1:]):
        assert prev.end <= nxt.start
        assert nxt.start.minute % 10 == 0 and nxt.start.second == 0
    assert "+09:00" in plan.model_dump_json()


def test_first_place_stays_first():
    for first in SAMPLE:
        place_ids = [first] + [p for p in SAMPLE if p != first]
        plan = build_plan(place_ids, DAY, None, PROFILE)
        assert plan.stops[0].place_id == first
        assert sorted(s.place_id for s in plan.stops) == sorted(SAMPLE)


def test_order_is_nearest_neighbor_then_2opt():
    # 일직선 위 장소: a(0) - b(1) - c(2) - d(10). 입력 순서와 무관하게 가까운 순으로 간다
    pos = {"a": 0, "b": 1, "c": 2, "d": 10}
    travel = lambda x, y: abs(pos[x] - pos[y])  # noqa: E731
    assert schedule._visit_order(["a", "d", "c", "b"], travel) == ["a", "b", "c", "d"]
    # 동률이면 place_id 사전순
    assert schedule._visit_order(["a", "c", "b"], lambda x, y: 5) == ["a", "b", "c"]
    # 최근접 이웃만으로는 s→c→d→b→a (10분). 2-opt 가 s→d→c→b→a (8분)로 줄인다
    pos = {"s": 0, "a": -6, "b": -5, "c": -1, "d": 1}
    assert schedule._visit_order(["s", "a", "b", "c", "d"], travel) == ["s", "d", "c", "b", "a"]


def test_travel_error_uses_30_min(monkeypatch, caplog):
    monkeypatch.setattr(schedule, "get_travel_time", lambda a, b: {"error": {"code": "no_route", "message": "x"}})
    with caplog.at_level(logging.WARNING, logger=schedule.__name__):
        plan = build_plan(["busan-tower", "jagalchi-market"], DAY, None, PROFILE)
    first, second = plan.stops
    assert first.end == dt.datetime(2026, 11, 28, 10, 45, tzinfo=KST)  # observatory 45분
    assert second.start == dt.datetime(2026, 11, 28, 11, 20, tzinfo=KST)  # 10:45 + 30분 = 11:15 → 11:20
    assert "30분" in caplog.text


def test_late_end_warns_but_keeps_all_stops(caplog):
    with caplog.at_level(logging.WARNING, logger=schedule.__name__):
        plan = build_plan(SAMPLE, DAY, "21:00", PROFILE)
    assert len(plan.stops) == len(SAMPLE)
    assert "22:00" in caplog.text


def test_sample_plan(capsys):
    """보고용 샘플. `uv run pytest -q -s -k sample_plan` 으로 출력한다."""
    plan = build_plan(SAMPLE, "2026-11-28", "10:00", PROFILE)
    with capsys.disabled():
        print()
        for s in plan.stops:
            print(f"  {s.stop_id} {s.place_id:18} {s.start.isoformat()} ~ {s.end.isoformat()}")
