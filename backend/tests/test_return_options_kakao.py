"""get_return_options의 카카오 실시간 경로와 rank_routes 연결 테스트. 네트워크를 쓰지 않는다."""

import collections
import json
import threading
import time

import pytest

from app import config
from app.tools import lookup
from app.tools import return_options as ro

DAY = "2026-11-28"
FESTIVAL = "해운대 빛축제"
STATIONS = {
    station["station"]: station
    for station in json.loads((lookup.DATA_DIR / "stations.json").read_text(encoding="utf-8"))["stations"]
}
STATION_BY_COORD = {(station["lat"], station["lng"]): name for name, station in STATIONS.items()}
NAME_KO = {"Haeundae": "해운대", "Dongbaek": "동백", "Jung-dong": "중동", "Seomyeon": "서면"}
LIVE_MINUTES = {"Haeundae": 40, "Dongbaek": 35, "Jung-dong": 42}


@pytest.fixture(autouse=True)
def live_config(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "TEST-KAKAO-KEY")


def kakao_routes(station: str, minutes: int) -> list[dict]:
    """실제 응답을 복사하지 않고 fetch_routes 반환 형식에 맞춰 직접 만든 경로다."""
    return [{
        "route_type": "SUBWAY",
        "total_minutes": minutes,
        "transfers": 0,
        "distance_m": minutes * 400,
        "fare": 1600,
        "walk_meters": 0,
        "legs": [{
            "mode": "SUBWAY",
            "minutes": minutes,
            "distance_m": minutes * 400,
            "lines": ["2호선"],
            "from_name": NAME_KO[station],
            "to_name": NAME_KO["Seomyeon"],
        }],
    }]


def station_for(origin_lat: float, origin_lng: float) -> str:
    return STATION_BY_COORD[(origin_lat, origin_lng)]


def scene7() -> dict:
    return ro.return_options(DAY, event_name=FESTIVAL)


def test_카카오_성공은_출발역별_한번씩_병렬_조회하고_ranked를_붙인다(monkeypatch):
    calls = []
    destinations = []
    lock = threading.Lock()
    barrier = threading.Barrier(3, timeout=1)

    def fake_fetch(origin_lat, origin_lng, dest_lat, dest_lng):
        station = station_for(origin_lat, origin_lng)
        with lock:
            calls.append(station)
            destinations.append((dest_lat, dest_lng))
        barrier.wait()  # 세 출발역 호출이 동시에 실행되지 않으면 테스트가 실패한다
        return kakao_routes(station, LIVE_MINUTES[station])

    monkeypatch.setattr(ro, "fetch_routes", fake_fetch)
    monkeypatch.setattr(ro, "last_train_warnings", lambda *args: ["last_train_missed"])
    started = time.perf_counter()
    result = scene7()
    elapsed = time.perf_counter() - started

    assert elapsed < 2
    assert collections.Counter(calls) == {"Haeundae": 1, "Dongbaek": 1, "Jung-dong": 1}
    assert set(destinations) == {(STATIONS["Seomyeon"]["lat"], STATIONS["Seomyeon"]["lng"])}
    assert result["baseline"]["minutes"] == 40 and result["baseline"]["time_source"] == "kakao"
    assert result["baseline"]["legs"][0] == {
        "mode": "SUBWAY", "minutes": 40, "distance_m": 16000, "lines": ["2호선"],
        "from_name": "해운대", "to_name": "서면",
        "from_names": {"ko": "해운대", "en": "Haeundae"}, "to_names": {"ko": "서면", "en": "Seomyeon"},
    }

    by_station = {option["station"]: option for option in result["options"] if option["type"] == "walk_to_station"}
    assert (by_station["Dongbaek"]["extra_min"], by_station["Jung-dong"]["extra_min"]) == (13, 19)
    assert all(option["time_source"] == "kakao" and option["legs"] for option in result["options"])

    ranked = result["ranked"]
    assert [row["option"]["station"] for row in ranked] == ["Dongbaek", "Jung-dong", "Haeundae"]
    assert [row["labels"] for row in ranked] == [["best"], [], ["earliest_arrival", "least_walking"]]
    assert not any(row["option"]["type"] == "shift_later" for row in ranked)
    assert all(row["excluded"] is None for row in ranked)


def test_일부_출발역_실패는_그_역만_좌표_추정으로_섞는다(monkeypatch):
    calls = []

    def fake_fetch(origin_lat, origin_lng, dest_lat, dest_lng):
        station = station_for(origin_lat, origin_lng)
        calls.append(station)
        if station == "Dongbaek":
            return None
        return kakao_routes(station, LIVE_MINUTES[station])

    monkeypatch.setattr(ro, "fetch_routes", fake_fetch)
    result = scene7()

    assert collections.Counter(calls) == {"Haeundae": 1, "Dongbaek": 1, "Jung-dong": 1}
    assert result["baseline"]["time_source"] == "kakao" and result["baseline"]["minutes"] == 40
    walk_options = {option["station"]: option for option in result["options"] if option["type"] == "walk_to_station"}
    assert walk_options["Dongbaek"]["time_source"] == "estimate"
    assert walk_options["Dongbaek"]["extra_min"] == 14
    assert "legs" not in walk_options["Dongbaek"]
    assert walk_options["Jung-dong"]["time_source"] == "kakao"
    assert walk_options["Jung-dong"]["extra_min"] == 19
    assert walk_options["Jung-dong"]["legs"][0]["from_name"] == "중동"


def test_카카오가_전부_실패하면_기존_좌표_추정과_rank_routes를_쓴다(monkeypatch):
    calls = []

    def no_routes(origin_lat, origin_lng, dest_lat, dest_lng):
        calls.append(station_for(origin_lat, origin_lng))
        return None

    monkeypatch.setattr(ro, "fetch_routes", no_routes)
    result = scene7()

    assert collections.Counter(calls) == {"Haeundae": 1, "Dongbaek": 1, "Jung-dong": 1}
    assert result["baseline"]["minutes"] == 39 and result["baseline"]["time_source"] == "estimate"
    assert all(option["time_source"] == "estimate" and "legs" not in option for option in result["options"])
    walk_options = {option["station"]: option for option in result["options"] if option["type"] == "walk_to_station"}
    assert (walk_options["Dongbaek"]["extra_min"], walk_options["Jung-dong"]["extra_min"]) == (15, 20)
    assert [row["option"]["station"] for row in result["ranked"]] == ["Dongbaek", "Jung-dong", "Haeundae"]


def test_USE_MOCK은_fetch_routes를_부르지_않고_추정값을_쓴다(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(
        ro,
        "fetch_routes",
        lambda *args: pytest.fail("USE_MOCK=1에서는 fetch_routes를 부르지 않는다"),
    )

    result = scene7()

    assert result["baseline"]["minutes"] == 39 and result["baseline"]["time_source"] == "estimate"
    assert all(option["time_source"] == "estimate" for option in result["options"])
    assert result["ranked"]


def test_카카오_승하차_이름에_역_표의_언어별_이름을_붙인다(monkeypatch):
    legs = [
        {"mode": "WALKING", "minutes": 2, "distance_m": 120, "lines": [], "from_name": None, "to_name": None},
        {"mode": "BUS", "minutes": 10, "distance_m": 4000, "lines": ["1003"],
         "from_name": "해운대역", "to_name": "센텀시티역.벡스코"},  # 버스 정류장은 역 이름과 같아도 한국어 그대로
        {"mode": "SUBWAY", "minutes": 20, "distance_m": 9000, "lines": ["2호선"],
         "from_name": "센텀시티", "to_name": "서면역"},  # '역'이 있든 없든 역 표와 맞춘다
        {"mode": "SUBWAY", "minutes": 5, "distance_m": 2000, "lines": ["동해선"],
         "from_name": "벡스코", "to_name": "오시리아"},  # 역 표(1~4호선)에 없는 역
    ]

    def fake_fetch(origin_lat, origin_lng, dest_lat, dest_lng):
        route = kakao_routes("Haeundae", 40)[0]
        return [{**route, "legs": [dict(leg) for leg in legs]}]

    monkeypatch.setattr(ro, "fetch_routes", fake_fetch)
    result = scene7()

    got = result["baseline"]["legs"]
    assert [{key: leg[key] for key in legs[0]} for leg in got] == legs  # 카카오가 준 값은 그대로다
    assert [(leg["from_names"], leg["to_names"]) for leg in got] == [
        ({}, {}),
        ({"ko": "해운대역"}, {"ko": "센텀시티역.벡스코"}),
        ({"ko": "센텀시티", "en": "Centum City"}, {"ko": "서면역", "en": "Seomyeon"}),
        ({"ko": "벡스코"}, {"ko": "오시리아"}),
    ]
    # 역 표에는 한국어·영어 이름만 있다. 없는 언어(ja, zh-Hans, zh-Hant)는 만들지 않는다
    assert all(set(names) <= {"ko", "en"} for leg in got for names in (leg["from_names"], leg["to_names"]))
    assert all(option["legs"][2]["to_names"]["en"] == "Seomyeon" for option in result["options"])
    assert result["ranked"][0]["option"]["legs"][2]["from_names"] == {"ko": "센텀시티", "en": "Centum City"}
    assert json.loads(json.dumps(result)) == result
