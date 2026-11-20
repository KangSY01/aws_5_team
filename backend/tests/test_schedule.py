"""일정 생성(app/tools/schedule.py) 테스트. 네트워크를 쓰지 않는다.

모든 테스트를 USE_MOCK=1 로 돌린다(use_mock_data). build_plan 은 방문 순서를 정할 때 get_weather 도 부르는데,
USE_MOCK=0 이면 오늘 날짜에 따라 날씨 캐시(DynamoDB)·기상청을 부를 수 있어서다.
읽는 파일: places.json, travel_times.json, hours.json, weather/2026-11-28.json(샘플 예보, 비 없음).
"""

import datetime as dt
import logging
import re
import urllib.request

import pytest

from app import config
from app.guardian import context as guardian_context
from app.guardian.check import check_plan
from app.guardian.thresholds import TRANSFER_BUFFER_MIN
from app.models.plan import Profile
from app.ranking.orders import OrderScore
from app.storage.service import new_plan_id
from app.tools import lookup, schedule
from app.tools.lookup import get_travel_time
from app.tools.schedule import PlanBuildError, build_plan

KST = dt.timezone(dt.timedelta(hours=9))
PROFILE = Profile(language="en")
SAMPLE = ["gamcheon-village", "jagalchi-market", "busan-tower", "haeundae-beach"]
DAY = dt.date(2026, 11, 28)


@pytest.fixture(autouse=True)
def use_mock_data(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)


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
    # 10:45 + 이동 30분 + 여유 10분(TRANSFER_BUFFER_MIN) = 11:25 → 11:30
    assert second.start == dt.datetime(2026, 11, 28, 11, 30, tzinfo=KST)
    assert "30분" in caplog.text


OTHER_ROUTES = [
    ["haeundae-beach", "the-bay-101", "dongbaekseom", "busan-x-the-sky", "sea-life-busan"],
    ["busan-tower", "gukje-market", "jagalchi-market", "yongdusan-park", "busan-chinatown", "choryang-ibagu-gil"],
    ["beomeosa-temple", "taejongdae", "gwangalli-beach"],  # 먼 곳끼리
]


@pytest.mark.parametrize("place_ids", [SAMPLE, *OTHER_ROUTES])
@pytest.mark.parametrize("start", ["10:00", "10:05", "09:53", "13:30"])
def test_이동_여유는_항상_Guardian_기준_이상이다(place_ids, start):
    stops = build_plan(place_ids, DAY, start, PROFILE).stops
    assert len(stops) == len(place_ids)
    for prev, nxt in zip(stops, stops[1:]):
        travel = get_travel_time(prev.place_id, nxt.place_id)["minutes"]
        slack = (nxt.start - prev.end).total_seconds() / 60 - travel
        # 여유는 기준 이상이고, 10분 단위 올림 때문에 늘어나는 만큼(ROUND_MIN 미만)만 더 길다
        assert TRANSFER_BUFFER_MIN <= slack < TRANSFER_BUFFER_MIN + schedule.ROUND_MIN, (prev.place_id, nxt.place_id, slack)


def test_샘플_일정의_시각():
    stops = build_plan(SAMPLE, "2026-11-28", "10:00", PROFILE).stops
    assert [(s.place_id, s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in stops] == [
        ("gamcheon-village", "10:00", "11:30"),
        ("jagalchi-market", "12:00", "13:00"),  # 11:30 + 이동 16분 + 여유 10분 = 11:56 → 12:00
        ("busan-tower", "13:20", "14:05"),  # 13:00 + 10분 + 10분 = 13:20
        ("haeundae-beach", "15:10", "16:10"),  # 14:05 + 52분 + 10분 = 15:07 → 15:10
    ]


@pytest.mark.parametrize("place_ids", [SAMPLE, *OTHER_ROUTES])
def test_만든_일정에_Guardian_tight_transfer가_없다(place_ids, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)  # 날씨는 샘플 파일. 이동 시간은 실제 표를 읽는다
    plan = build_plan(place_ids, DAY, "10:00", PROFILE)
    context = guardian_context.build_context(plan)
    assert all(context.travel(a.place_id, b.place_id) is not None for a, b in zip(plan.stops, plan.stops[1:]))
    issues = check_plan(plan, context)
    assert [i for i in issues if i.type == "tight_transfer"] == []


# ---------- 방문 순서 (rank_orders) ----------

def fake_rank_orders(result: list[OrderScore], calls: list):
    """rank_orders 대신 넣는다. 받은 인자를 calls 에 남기고 result 를 돌려준다."""

    def fake(place_ids, ctx, **kwargs):
        calls.append({"place_ids": place_ids, "ctx": ctx, **kwargs})
        return result

    return fake


def scored(order: list[str]) -> OrderScore:
    # stops 는 비워 둔다. build_plan 이 rank_orders 의 stops 를 쓰면 Stop 이 0개가 되어 드러난다
    return OrderScore(order=order, score=0.0, travel_min=0, rain_points=0, locked_slack_min=None, stops=[])


def error(code: str) -> dict:
    return {"error": {"code": code, "message": "x"}}


def test_rank_orders_1위_순서를_쓰고_시각은_기존_방식으로_계산한다(monkeypatch):
    calls = []
    chosen = ["gamcheon-village", "haeundae-beach", "busan-tower", "jagalchi-market"]  # 최근접 이웃 + 2-opt 와 다른 순서
    monkeypatch.setattr(schedule, "rank_orders", fake_rank_orders([scored(chosen)], calls))

    stops = build_plan([*SAMPLE, "no-such-place", "busan-tower"], DAY, "10:00", PROFILE).stops

    assert [(s.stop_id, s.place_id, s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in stops] == [
        ("s1", "gamcheon-village", "10:00", "11:30"),
        ("s2", "haeundae-beach", "12:40", "13:40"),  # 11:30 + 이동 58분 + 여유 10분 = 12:38 → 12:40
        ("s3", "busan-tower", "14:50", "15:35"),  # 13:40 + 52분 + 10분 = 14:42 → 14:50
        ("s4", "jagalchi-market", "16:00", "17:00"),  # 15:35 + 10분 + 10분 = 15:55 → 16:00
    ]
    # 넘긴 값: 유효 장소(모르는 ID·중복 제외), 방문일, 시작 시각, category 기본 체류 시간. locked 는 넘기지 않는다
    (call,) = calls
    assert call["place_ids"] == SAMPLE
    assert call["day"] == DAY and call["start_time"] == dt.time(10, 0)
    assert call["dwell_min"] == {"gamcheon-village": 90, "jagalchi-market": 60, "busan-tower": 45, "haeundae-beach": 60}
    assert "locked" not in call


def test_rank_orders_에_넘기는_CheckContext(monkeypatch):
    real_travel, real_hours = schedule.get_travel_time, schedule.get_hours
    monkeypatch.setattr(
        schedule, "get_travel_time",
        lambda a, b: error("no_route") if {a, b} == {"busan-tower", "haeundae-beach"} else real_travel(a, b),
    )
    monkeypatch.setattr(
        schedule, "get_hours",
        lambda p: error("data_unavailable") if p == "gamcheon-village" else real_hours(p),
    )
    monkeypatch.setattr(config, "DEMO_NOW", "2026-11-28T09:30:00+09:00")
    calls = []
    monkeypatch.setattr(schedule, "rank_orders", fake_rank_orders([], calls))

    build_plan(SAMPLE, DAY, "10:00", PROFILE)

    ctx = calls[0]["ctx"]
    assert ctx.now == dt.datetime(2026, 11, 28, 9, 30, tzinfo=KST)  # DEMO_NOW
    assert ctx.places == guardian_context.PLACES
    # 유효 장소 4곳의 6쌍 중 조회에 실패한 1쌍은 넣지 않는다
    assert len(ctx.travel_min) == 5 and ctx.travel("busan-tower", "haeundae-beach") is None
    expected = real_travel("gamcheon-village", "haeundae-beach")["minutes"]
    assert ctx.travel("gamcheon-village", "haeundae-beach") == ctx.travel("haeundae-beach", "gamcheon-village") == expected
    # 운영시간도 조회에 실패한 장소는 넣지 않는다
    assert set(ctx.hours) == {"jagalchi-market", "busan-tower", "haeundae-beach"}
    assert ctx.hours["busan-tower"] == guardian_context.OpeningHours.model_validate(real_hours("busan-tower"))
    # USE_MOCK=1 이라 샘플 예보 (app/data/weather/2026-11-28.json)
    hourly = lookup.get_weather("2026-11-28")["hourly"]
    assert hourly and ctx.weather == [guardian_context.HourlyWeather.model_validate(h) for h in hourly]

    monkeypatch.setattr(config, "DEMO_NOW", None)  # DEMO_NOW 가 없으면 현재 시각(KST)
    build_plan(SAMPLE, DAY, "10:00", PROFILE)
    now = calls[1]["ctx"].now
    assert now.utcoffset() == dt.timedelta(hours=9) and abs(now - dt.datetime.now(KST)) < dt.timedelta(minutes=1)


@pytest.mark.parametrize(
    "weather", [error("upstream_error"), {"date": "2026-11-28", "hourly": []}], ids=["error", "no_forecast"]
)
def test_예보가_오류이거나_없으면_weather_는_None(weather, monkeypatch):
    calls = []
    monkeypatch.setattr(schedule, "get_weather", lambda date: weather)
    monkeypatch.setattr(schedule, "rank_orders", fake_rank_orders([], calls))
    assert len(build_plan(SAMPLE, DAY, "10:00", PROFILE).stops) == len(SAMPLE)
    assert calls[0]["ctx"].weather is None


def test_rank_orders_가_빈_목록이면_최근접_이웃_2opt_로_정하고_로그를_한_줄_남긴다(monkeypatch, caplog):
    monkeypatch.setattr(schedule, "rank_orders", fake_rank_orders([], []))
    shuffled = ["gamcheon-village", "haeundae-beach", "busan-tower", "jagalchi-market"]
    with caplog.at_level(logging.INFO, logger=schedule.__name__):
        plan = build_plan(shuffled, DAY, "10:00", PROFILE)
    # 입력 순서가 아니라 기존 방식의 순서: 감천 → 자갈치(16분) → 부산타워(10분) → 해운대(52분)
    assert [s.place_id for s in plan.stops] == SAMPLE
    fallback = [r for r in caplog.records if "기존 방식" in r.getMessage()]
    assert len(fallback) == 1 and fallback[0].levelno == logging.INFO


@pytest.mark.parametrize("place_ids", [SAMPLE, *OTHER_ROUTES])
def test_실제_rank_orders_1위의_순서와_시각이_그대로_나온다(place_ids, monkeypatch):
    results = []
    real = schedule.rank_orders

    def spy(*args, **kwargs):
        results.append(real(*args, **kwargs))
        return results[-1]

    monkeypatch.setattr(schedule, "rank_orders", spy)
    plan = build_plan(place_ids, DAY, "10:00", PROFILE)
    assert results[0], "10:00 시작이면 모두 운영시간 안이라 가능한 순서가 있다"
    # 시각은 build_plan 이 따로 계산하지만 rank_orders 가 채점한 시각과 같다 (운영시간·비 판단이 실제 일정과 맞는다)
    assert plan.stops == results[0][0].stops
    # 같은 입력이면 같은 결과
    assert without_id(plan) == without_id(build_plan(place_ids, DAY, "10:00", PROFILE))


def test_USE_MOCK_1_이면_네트워크를_부르지_않는다(monkeypatch):
    # 오늘을 방문 전날로 둔다. USE_MOCK=0 이면 날씨 캐시(DynamoDB)와 기상청을 부르는 날짜다
    monkeypatch.setattr(lookup, "_now", lambda: dt.datetime(2026, 11, 27, 9, 0, tzinfo=KST))
    calls = []
    monkeypatch.setattr(lookup, "_cache_table", lambda: calls.append("dynamodb"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: calls.append("http"))

    assert len(build_plan(SAMPLE, DAY, "10:00", PROFILE).stops) == len(SAMPLE)  # USE_MOCK=1 (use_mock_data)
    assert calls == []

    # 감시가 제대로 걸렸는지 확인: 같은 호출을 USE_MOCK=0 으로 하면 날씨 캐시부터 찾는다
    monkeypatch.setattr(config, "USE_MOCK", False)
    build_plan(SAMPLE, DAY, "10:00", PROFILE)
    assert calls[:1] == ["dynamodb"]


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
