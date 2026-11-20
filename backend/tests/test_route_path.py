"""GET /route 와 일정 시각 실시간 계산 (app/tools/route_path.py). 네트워크는 부르지 않는다."""
import json

import pytest

from app import config
from app.handler import handler
from app.tools import route_path
from scripts.local_invoke import make_event

DONGBAEK = (35.1534, 129.1525)
RODEO = (35.1622, 129.1602)
SEOMYEON = (35.1578, 129.0594)


def get_route(query):
    result = handler({**make_event("GET", "/route"), "queryStringParameters": query})
    return result["statusCode"], json.loads(result["body"])


def test_short_trip_walks_on_osm_path(monkeypatch):
    path = [[35.1534, 129.1525], [35.158, 129.156], [35.1622, 129.1602]]
    monkeypatch.setattr(route_path, "osm_walk", lambda a, b: {"minutes": 22, "distance_m": 1700, "path": path})
    route = route_path.route_between(DONGBAEK, RODEO)
    assert (route["mode"], route["minutes"], route["source"]) == ("walk", 22, "osm")
    assert route["segments"][0]["path"] == path


def test_long_trip_uses_transit_legs_with_walks_to_stations(monkeypatch):
    legs = [{"mode": "SUBWAY", "lines": ["2호선"], "minutes": 30, "path": [[35.163, 129.158], [35.157, 129.060]]}]
    monkeypatch.setattr(route_path, "fetch_transit", lambda a, b: [{"total_minutes": 40, "legs": legs}])
    monkeypatch.setattr(route_path, "osm_walk", lambda a, b: {"minutes": 3, "distance_m": 200, "path": [list(a), list(b)]})
    route = route_path.route_between(RODEO, SEOMYEON)
    assert (route["mode"], route["minutes"], route["source"]) == ("transit", 40, "kakao")
    assert [s["mode"] for s in route["segments"]] == ["WALKING", "SUBWAY", "WALKING"]
    assert route["segments"][1]["lines"] == ["2호선"]


def test_falls_back_to_straight_line_when_lookups_fail():
    walk = route_path.route_between(DONGBAEK, RODEO)
    assert walk["source"] == "straight" and walk["segments"][0]["path"] == [list(DONGBAEK), list(RODEO)]
    transit = route_path.route_between(RODEO, SEOMYEON)
    assert transit["source"] == "straight" and transit["segments"][0]["mode"] == "ESTIMATE"
    assert route_path.realtime_minutes(RODEO, SEOMYEON) is None or config.USE_MOCK


def test_get_route_endpoint_validates_busan_coordinates():
    status, body = get_route({"from": "35.1534,129.1525", "to": "35.1622,129.1602"})
    assert status == 200 and body["mode"] == "walk" and body["segments"]
    for bad in ({"from": "35.15,129.15"}, {"from": "37.56,126.97", "to": "35.16,129.16"}, {"from": "x", "to": "y"}):
        assert get_route(bad)[0] == 422


@pytest.mark.parametrize("live, expected", [(None, "estimate"), (5, "estimate"), (999, 999)])
def test_build_plan_uses_the_longer_of_live_and_estimated_leg(monkeypatch, live, expected):
    from app.tools import schedule

    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(route_path, "realtime_minutes", lambda a, b: live)
    estimate = schedule._realtime_legs(["haeundae-beach", "haeundae-market"], lambda a, b: 7)
    assert estimate[("haeundae-beach", "haeundae-market")] == (7 if expected == "estimate" else expected)
