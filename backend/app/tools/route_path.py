"""지도에 그릴 실제 이동 경로 (GET /route). 저장·캐시하지 않고 요청마다 실시간으로 조회한다.

- 가까운 구간(직선 WALK_MAX_KM 이하): OSM 도보 경로 (routing.openstreetmap.de, © OpenStreetMap contributors)
- 먼 구간: 카카오 대중교통 첫 번째 경로의 버스·지하철 구간 좌표 + 출발지→첫 정류장, 마지막 정류장→도착지 OSM 도보 경로
- 조회 실패: 직선(source "straight"). 분은 좌표 추정 규칙(lookup.get_travel_time 과 같은 식)

카카오 결과는 data-rules 에 따라 저장하지 않는다 (이 모듈은 전역 변수·파일·DB 에 결과를 남기지 않는다).
"""
from __future__ import annotations

import json
import logging
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app import config
from app.tools import kakao_route

logger = logging.getLogger(__name__)

OSM_FOOT_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/{a_lng},{a_lat};{b_lng},{b_lat}?overview=full&geometries=geojson"
OSM_TIMEOUT_SEC = 4
USER_AGENT = "busannow-hackathon-demo/0.1"
WALK_MAX_KM = 1.5  # 직선거리가 이보다 짧으면 걷는다 (도보 약 20분)
WALK_KMH = 4.5
TRANSIT_KMH = 25
TRANSIT_WAIT_MIN = 10
BUSAN_BOUNDS = (34.8, 35.5, 128.7, 129.4)  # 위도 최소·최대, 경도 최소·최대 (부산 밖 좌표는 거절)


def in_busan(lat: float, lng: float) -> bool:
    return BUSAN_BOUNDS[0] <= lat <= BUSAN_BOUNDS[1] and BUSAN_BOUNDS[2] <= lng <= BUSAN_BOUNDS[3]


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def estimate_minutes(a: tuple[float, float], b: tuple[float, float]) -> tuple[int, str]:
    """좌표 추정 (lookup.get_travel_time 과 같은 규칙: 경로 = 직선 × 1.3)."""
    km = _km(a, b) * 1.3
    if km <= 1.2:
        return math.ceil(km / WALK_KMH * 60), "walk"
    return math.ceil(km / TRANSIT_KMH * 60 + TRANSIT_WAIT_MIN), "subway"


def osm_walk(a: tuple[float, float], b: tuple[float, float]) -> dict | None:
    """OSM 도보 경로. {"minutes", "distance_m", "path": [[위도, 경도], ...]} 또는 실패 시 None."""
    if config.USE_MOCK:
        return None
    url = OSM_FOOT_URL.format(a_lat=a[0], a_lng=a[1], b_lat=b[0], b_lng=b[1])
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=OSM_TIMEOUT_SEC) as response:
            data = json.load(response)
        route = data["routes"][0]
        path = [[float(lat), float(lng)] for lng, lat in route["geometry"]["coordinates"]]
        if data.get("code") != "Ok" or len(path) < 2:
            return None
        return {"minutes": max(1, math.ceil(route["duration"] / 60)), "distance_m": round(route["distance"]), "path": path}
    except Exception as error:  # 네트워크·형식 오류는 직선으로 대신한다
        logger.warning("OSM 도보 경로 조회 실패(%s)", type(error).__name__)
        return None


def _walk_segment(a: tuple[float, float], b: tuple[float, float]) -> dict:
    walk = osm_walk(a, b)
    if walk:
        return {"mode": "WALKING", "lines": [], **walk, "source": "osm"}
    minutes = math.ceil(_km(a, b) * 1.3 / WALK_KMH * 60)
    return {"mode": "WALKING", "lines": [], "minutes": minutes, "distance_m": round(_km(a, b) * 1300),
            "path": [list(a), list(b)], "source": "straight"}


def fetch_transit(a: tuple[float, float], b: tuple[float, float]) -> list[dict] | None:
    """카카오 대중교통 경로 (지도용 path 포함). 테스트는 이 함수만 바꿔 끼운다."""
    return kakao_route.fetch_routes(a[0], a[1], b[0], b[1], include_path=True)


def route_between(a: tuple[float, float], b: tuple[float, float]) -> dict:
    """a → b 지도 경로. {"mode": "walk"|"transit", "minutes", "source", "segments": [...]}.

    segments 의 각 항목: {"mode": "WALKING"|"BUS"|"SUBWAY"|..., "lines", "minutes", "path"}.
    """
    if _km(a, b) <= WALK_MAX_KM:
        segment = _walk_segment(a, b)
        return {"mode": "walk", "minutes": segment["minutes"], "source": segment["source"], "segments": [segment]}

    routes = fetch_transit(a, b)
    transit = [leg for leg in (routes[0]["legs"] if routes else []) if leg.get("path")]
    if not transit:
        minutes, _ = estimate_minutes(a, b)
        return {"mode": "transit", "minutes": minutes, "source": "straight",
                "segments": [{"mode": "ESTIMATE", "lines": [], "minutes": minutes, "path": [list(a), list(b)]}]}

    first, last = tuple(transit[0]["path"][0]), tuple(transit[-1]["path"][-1])
    with ThreadPoolExecutor(max_workers=2) as pool:  # 정류장까지 걷는 두 구간을 함께 조회
        before, after = pool.map(lambda pair: _walk_segment(*pair), [(a, first), (last, b)])
    segments = [before, *({"mode": leg["mode"], "lines": leg.get("lines", []), "minutes": leg["minutes"],
                           "path": leg["path"]} for leg in transit), after]
    return {"mode": "transit", "minutes": routes[0]["total_minutes"], "source": "kakao", "segments": segments}


def realtime_minutes(a: tuple[float, float], b: tuple[float, float]) -> int | None:
    """일정 시각 계산용 실시간 이동 분. 실패하면 None (호출하는 쪽이 추정값을 쓴다)."""
    if config.USE_MOCK:
        return None
    try:
        route = route_between(a, b)
    except Exception as error:
        logger.warning("실시간 이동 시간 조회 실패(%s)", type(error).__name__)
        return None
    return None if route["source"] == "straight" else int(route["minutes"])


# ---------- GET /route 응답 모델 ----------
from pydantic import BaseModel  # noqa: E402


class RouteSegment(BaseModel):
    mode: str  # WALKING | BUS | SUBWAY | ESTIMATE ...
    lines: list[str] = []
    minutes: int
    path: list[list[float]]  # [[위도, 경도], ...]


class RouteResponse(BaseModel):
    mode: str  # walk | transit
    minutes: int
    source: str  # osm | kakao | straight
    segments: list[RouteSegment]


def parse_point(text: str | None) -> tuple[float, float] | None:
    """"위도,경도" 문자열을 좌표로. 형식이 틀리거나 부산 밖이면 None."""
    try:
        lat, lng = (float(v) for v in (text or "").split(","))
    except ValueError:
        return None
    return (lat, lng) if math.isfinite(lat) and math.isfinite(lng) and in_busan(lat, lng) else None
