"""카카오 대중교통 실시간 조회 모듈 테스트. 응답은 직접 만든 값이며 네트워크를 쓰지 않는다."""

import json
import logging
import urllib.error
import urllib.parse

import pytest

from app import config
from app.tools import kakao_route

TEST_KEY = "TEST-KAKAO-SECRET"
ORIGIN = (35.158011, 129.05932)
DESTINATION = (35.163672, 129.158908)


class FakeResponse:
    def __init__(self, data):
        self.body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def live_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", TEST_KEY)


def install_response(monkeypatch, data, seen=None):
    def fake_urlopen(request, timeout):
        if seen is not None:
            seen.update(request=request, timeout=timeout)
        return FakeResponse(data)

    monkeypatch.setattr(kakao_route.urllib.request, "urlopen", fake_urlopen)


def minimal_route(route_type: str, *, fare=True, total_time=600) -> dict:
    properties = {
        "type": route_type,
        "totalDistance": 5000,
        "totalTime": total_time,
        "transfers": 0,
    }
    if fare:
        properties["fare"] = {"value": 1600}
    return {
        "properties": properties,
        "steps": [{
            "properties": {
                "guidance": "이동",
                "type": route_type,
                "distance": 5000,
                "time": total_time,
                "stops": [{"name": "서면"}, {"name": "해운대"}],
                "vehicles": [{"type": "일반", "name": "노선 A"}],
            },
            "path": {"points": [[129.05932, 35.158011], [129.158908, 35.163672]]},
        }],
    }


def test_지하철_한_구간을_파싱하고_요청_좌표와_헤더가_맞다(monkeypatch):
    payload = {
        "status": "OK",
        "properties": {"total": 1, "subway": 1, "landingURL": "https://map.kakao.com/ignored"},
        "routes": [{
            "properties": {
                "type": "SUBWAY",
                "totalDistance": 15200,
                "totalTime": 1830,
                "transfers": 0,
                "fare": {"value": 1650, "min": 1650, "max": 1650},
            },
            "steps": [{
                "properties": {
                    "guidance": "2호선 승차",
                    "type": "SUBWAY",
                    "distance": 15200,
                    "time": 1830,
                    "stops": [{"name": "서면"}, {"name": "전포"}, {"name": "해운대"}],
                    "vehicles": [{"type": "일반", "name": "2호선"}],
                },
                "path": {"points": [[129.05932, 35.158011], [129.158908, 35.163672]]},
            }],
        }],
    }
    seen = {}
    install_response(monkeypatch, payload, seen)

    result = kakao_route.fetch_routes(*ORIGIN, *DESTINATION)

    assert result == [{
        "route_type": "SUBWAY",
        "total_minutes": 31,
        "transfers": 0,
        "distance_m": 15200,
        "fare": 1650,
        "walk_meters": 0,
        "legs": [{
            "mode": "SUBWAY",
            "minutes": 31,
            "distance_m": 15200,
            "lines": ["2호선"],
            "from_name": "서면",
            "to_name": "해운대",
        }],
    }]
    request = seen["request"]
    assert request.method == "GET"
    assert request.get_header("Authorization") == f"KakaoAK {TEST_KEY}"
    assert seen["timeout"] == 3
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query) == {
        "start_x": ["129.05932"],
        "start_y": ["35.158011"],
        "end_x": ["129.158908"],
        "end_y": ["35.163672"],
        "input_coord": ["WGS84"],
    }
    assert "path" not in result[0]["legs"][0] and "landingURL" not in result[0]


def test_도보_버스_지하철_혼합_경로의_walk_meters와_legs(monkeypatch):
    payload = {
        "status": "OK",
        "properties": {"total": 1, "busAndSubway": 1},
        "routes": [{
            "properties": {
                "type": "BUS_AND_SUBWAY",
                "totalDistance": 14200,
                "totalTime": 1470,
                "transfers": 2,
                "fare": {"value": 1800},
            },
            "steps": [
                {"properties": {
                    "type": "WALKING", "distance": 120, "time": 95,
                    "vehicles": [{"name": "도보에는 넣지 않을 값"}],
                }},
                {"properties": {
                    "type": "BUS", "distance": 4000, "time": 605,
                    "vehicles": [{"name": "1003"}, {"name": "급행1001"}],
                    "stops": [{"name": "서면"}, {"name": "중간정류장"}, {"name": "수영역"}],
                }},
                {"properties": {
                    "type": "SUBWAY", "distance": 8000, "time": 750,
                    "vehicles": [{"name": "2호선"}],
                    "stops": [{"name": "수영"}, {"name": "해운대"}],
                }},
                {"properties": {
                    "type": "WALKING", "distance": 80, "time": 20, "stops": [],
                }},
            ],
        }],
    }
    install_response(monkeypatch, payload)

    result = kakao_route.fetch_routes(*ORIGIN, *DESTINATION)

    assert result == [{
        "route_type": "BUS_AND_SUBWAY",
        "total_minutes": 25,
        "transfers": 2,
        "distance_m": 14200,
        "fare": 1800,
        "walk_meters": 200,
        "legs": [
            {"mode": "WALKING", "minutes": 2, "distance_m": 120, "lines": [],
             "from_name": None, "to_name": None},
            {"mode": "BUS", "minutes": 10, "distance_m": 4000, "lines": ["1003", "급행1001"],
             "from_name": "서면", "to_name": "수영역"},
            {"mode": "SUBWAY", "minutes": 13, "distance_m": 8000, "lines": ["2호선"],
             "from_name": "수영", "to_name": "해운대"},
            {"mode": "WALKING", "minutes": 0, "distance_m": 80, "lines": [],
             "from_name": None, "to_name": None},
        ],
    }]


def test_fare가_없으면_None이고_routes_순서를_유지한다(monkeypatch):
    payload = {
        "status": "OK",
        "routes": [
            minimal_route("BUS", fare=False, total_time=300),
            minimal_route("SUBWAY", total_time=600),
        ],
    }
    install_response(monkeypatch, payload)

    result = kakao_route.fetch_routes(*ORIGIN, *DESTINATION)

    assert [route["route_type"] for route in result] == ["BUS", "SUBWAY"]
    assert [route["fare"] for route in result] == [None, 1600]


def test_USE_MOCK이면_호출하지_않고_None(monkeypatch, caplog):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(
        kakao_route.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("USE_MOCK=1에서는 네트워크를 호출하지 않는다"),
    )

    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert "USE_MOCK=1" in caplog.text and TEST_KEY not in caplog.text


def test_키가_없으면_호출하지_않고_None(monkeypatch, caplog):
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "")
    monkeypatch.setattr(
        kakao_route.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("키가 없으면 네트워크를 호출하지 않는다"),
    )

    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert "KAKAO_REST_API_KEY가 없습니다" in caplog.text


def test_3초_타임아웃은_None이고_키를_로그에_남기지_않는다(monkeypatch, caplog):
    seen_timeouts = []

    def timeout(request, timeout):
        seen_timeouts.append(timeout)
        raise TimeoutError(f"시간 초과: {TEST_KEY}")

    monkeypatch.setattr(kakao_route.urllib.request, "urlopen", timeout)
    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert seen_timeouts == [3]
    assert "3초 시간 제한" in caplog.text and TEST_KEY not in caplog.text


def test_HTTP_500도_재시도하지_않고_None(monkeypatch, caplog):
    calls = []

    def http_error(request, timeout):
        calls.append(timeout)
        raise urllib.error.HTTPError(kakao_route.API_URL, 500, "temporary", {}, None)

    monkeypatch.setattr(kakao_route.urllib.request, "urlopen", http_error)
    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert calls == [3]
    assert "HTTP 500" in caplog.text


def test_HTTP_오류는_None이고_키를_로그에_남기지_않는다(monkeypatch, caplog):
    def http_error(request, timeout):
        raise urllib.error.HTTPError(
            f"{kakao_route.API_URL}?secret={TEST_KEY}", 403, TEST_KEY, {}, None
        )

    monkeypatch.setattr(kakao_route.urllib.request, "urlopen", http_error)
    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert "HTTP 403" in caplog.text and TEST_KEY not in caplog.text


def test_routes가_비면_None(monkeypatch, caplog):
    install_response(monkeypatch, {"status": "OK", "routes": []})

    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert "routes가 비어 있습니다" in caplog.text


@pytest.mark.parametrize("payload", [
    {"status": "NO_RESULTS"},
    {"status": "OK", "routes": [{"properties": {"type": "SUBWAY"}, "steps": []}]},
    b"not-json",
])
def test_비정상_status와_파싱_실패는_None(monkeypatch, payload, caplog):
    install_response(monkeypatch, payload)

    with caplog.at_level(logging.WARNING, logger=kakao_route.__name__):
        assert kakao_route.fetch_routes(*ORIGIN, *DESTINATION) is None

    assert caplog.records and TEST_KEY not in caplog.text


def test_결과를_메모리_캐시하지_않고_매번_호출한다(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(1)
        return FakeResponse({"status": "OK", "routes": [minimal_route("SUBWAY", total_time=60 * len(calls))]})

    monkeypatch.setattr(kakao_route.urllib.request, "urlopen", fake_urlopen)
    first = kakao_route.fetch_routes(*ORIGIN, *DESTINATION)
    second = kakao_route.fetch_routes(*ORIGIN, *DESTINATION)

    assert len(calls) == 2
    assert first[0]["total_minutes"] == 1
    assert second[0]["total_minutes"] == 2
