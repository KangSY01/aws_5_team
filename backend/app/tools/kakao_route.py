"""카카오맵 REST API에서 대중교통 경로를 실시간으로 조회한다.

이 모듈은 조회 결과를 파일, DynamoDB, 전역 변수 또는 메모리 캐시에 저장하지 않는다. 호출에 실패하면
호출하는 쪽에서 좌표 기반 추정값으로 대체할 수 있도록 None을 돌려준다.
"""

import json
import logging
import math
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app import config

logger = logging.getLogger(__name__)

API_URL = "https://dapi.kakao.com/v2/routing/publictraffic"
TIMEOUT_SEC = 3
ROUTE_TYPES = {"BUS", "SUBWAY", "BUS_AND_SUBWAY"}


class RouteParseError(ValueError):
    """카카오 응답이 필요한 경로 형식과 다르다."""


def _coordinate(value: float, minimum: float, maximum: float) -> str:
    """유한한 위·경도만 쿼리 문자열로 바꾼다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("좌표는 숫자여야 합니다.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError("좌표가 허용 범위를 벗어났습니다.")
    return str(number)


def _build_request(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> urllib.request.Request:
    """WGS84 좌표와 REST API 키 헤더로 카카오 요청을 만든다."""
    params = {
        "start_x": _coordinate(origin_lng, -180, 180),
        "start_y": _coordinate(origin_lat, -90, 90),
        "end_x": _coordinate(dest_lng, -180, 180),
        "end_y": _coordinate(dest_lat, -90, 90),
        "input_coord": "WGS84",
    }
    return urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
        method="GET",
    )


def _required_nonnegative_int(data: dict[str, Any], key: str) -> int:
    """필수 필드를 bool이 아닌 0 이상의 정수로 읽는다."""
    value = data.get(key)
    if type(value) is not int or value < 0:
        raise RouteParseError(f"{key} 형식이 올바르지 않습니다.")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    """필수 문자열 필드를 원문 그대로 읽는다."""
    value = data.get(key)
    if not isinstance(value, str):
        raise RouteParseError(f"{key} 형식이 올바르지 않습니다.")
    return value


def _round_minutes(seconds: int) -> int:
    """0 이상의 초를 가장 가까운 분으로 반올림한다. 30초는 올림한다."""
    return (seconds + 30) // 60


def _fare_value(properties: dict[str, Any]) -> int | None:
    """fare.value가 없으면 None, 있으면 0 이상의 정수로 읽는다."""
    fare = properties.get("fare")
    if fare is None:
        return None
    if not isinstance(fare, dict):
        raise RouteParseError("fare 형식이 올바르지 않습니다.")
    value = fare.get("value")
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise RouteParseError("fare.value 형식이 올바르지 않습니다.")
    return value


def _vehicle_names(properties: dict[str, Any], mode: str) -> list[str]:
    """차량 이름을 응답 순서대로 읽는다. 도보 단계는 항상 빈 목록이다."""
    if mode == "WALKING":
        return []
    vehicles = properties.get("vehicles")
    if vehicles is None:
        return []
    if not isinstance(vehicles, list):
        raise RouteParseError("vehicles 형식이 올바르지 않습니다.")

    names = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            raise RouteParseError("vehicle 형식이 올바르지 않습니다.")
        names.append(_required_string(vehicle, "name"))
    return names


def _stop_names(properties: dict[str, Any]) -> tuple[str | None, str | None]:
    """첫 정류장과 마지막 정류장 이름을 읽는다. stops가 없거나 비면 둘 다 None이다."""
    stops = properties.get("stops")
    if stops is None or stops == []:
        return None, None
    if not isinstance(stops, list):
        raise RouteParseError("stops 형식이 올바르지 않습니다.")
    if not isinstance(stops[0], dict) or not isinstance(stops[-1], dict):
        raise RouteParseError("stop 형식이 올바르지 않습니다.")
    return _required_string(stops[0], "name"), _required_string(stops[-1], "name")


def _parse_leg(step: Any) -> dict[str, Any]:
    """카카오 step 하나를 경량 leg 형식으로 바꾼다."""
    if not isinstance(step, dict) or not isinstance(step.get("properties"), dict):
        raise RouteParseError("step 형식이 올바르지 않습니다.")
    properties = step["properties"]
    mode = _required_string(properties, "type")
    seconds = _required_nonnegative_int(properties, "time")
    distance = _required_nonnegative_int(properties, "distance")
    from_name, to_name = _stop_names(properties)
    return {
        "mode": mode,
        "minutes": _round_minutes(seconds),
        "distance_m": distance,
        "lines": _vehicle_names(properties, mode),
        "from_name": from_name,
        "to_name": to_name,
    }


def _parse_route(route: Any) -> dict[str, Any]:
    """카카오 route 하나를 호출자가 사용할 경량 경로 형식으로 바꾼다."""
    if not isinstance(route, dict) or not isinstance(route.get("properties"), dict):
        raise RouteParseError("route 형식이 올바르지 않습니다.")
    properties = route["properties"]
    route_type = _required_string(properties, "type")
    if route_type not in ROUTE_TYPES:
        raise RouteParseError("알 수 없는 route type입니다.")

    steps = route.get("steps")
    if not isinstance(steps, list):
        raise RouteParseError("steps 형식이 올바르지 않습니다.")
    legs = [_parse_leg(step) for step in steps]
    return {
        "route_type": route_type,
        "total_minutes": _round_minutes(_required_nonnegative_int(properties, "totalTime")),
        "transfers": _required_nonnegative_int(properties, "transfers"),
        "distance_m": _required_nonnegative_int(properties, "totalDistance"),
        "fare": _fare_value(properties),
        "walk_meters": sum(leg["distance_m"] for leg in legs if leg["mode"] == "WALKING"),
        "legs": legs,
    }


def _parse_routes(data: Any) -> list[dict[str, Any]] | None:
    """정상 응답을 입력 순서대로 파싱한다. 비정상 상태와 빈 경로는 None이다."""
    if not isinstance(data, dict):
        raise RouteParseError("응답 최상위 형식이 올바르지 않습니다.")
    if data.get("status") != "OK":
        logger.warning("카카오 대중교통 경로 조회 실패: 응답 status가 OK가 아닙니다.")
        return None

    routes = data.get("routes")
    if not isinstance(routes, list):
        raise RouteParseError("routes 형식이 올바르지 않습니다.")
    if not routes:
        logger.warning("카카오 대중교통 경로 조회 실패: 응답 routes가 비어 있습니다.")
        return None
    return [_parse_route(route) for route in routes]


def _request_body(request: urllib.request.Request) -> bytes | None:
    """3초 제한으로 한 번만 요청하고 실패하면 바로 None을 돌려준다."""
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        logger.warning("카카오 대중교통 경로 조회 실패: HTTP %s", error.code)
        return None
    except (TimeoutError, socket.timeout):
        logger.warning("카카오 대중교통 경로 조회 실패: %s초 시간 제한을 넘었습니다.", TIMEOUT_SEC)
        return None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            logger.warning("카카오 대중교통 경로 조회 실패: %s초 시간 제한을 넘었습니다.", TIMEOUT_SEC)
        else:
            logger.warning("카카오 대중교통 경로 조회 실패: 네트워크 오류입니다.")
        return None
    except Exception as error:
        # 예외 메시지에는 요청 헤더가 포함될 수 있으므로 메시지는 로그에 넣지 않는다.
        logger.warning("카카오 대중교통 경로 조회 실패: 예상하지 못한 네트워크 오류(%s)입니다.", type(error).__name__)
        return None


def fetch_routes(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> list[dict] | None:
    """출발지와 도착지 사이의 카카오 대중교통 경로를 실시간으로 조회한다.

    Args:
        origin_lat: 출발지 WGS84 위도.
        origin_lng: 출발지 WGS84 경도.
        dest_lat: 도착지 WGS84 위도.
        dest_lng: 도착지 WGS84 경도.

    Returns:
        카카오가 준 순서를 유지한 경로 목록. 각 경로에는 route_type, total_minutes, transfers,
        distance_m, fare, walk_meters, legs가 있다. 조회 또는 파싱에 실패하면 None.
    """
    if config.USE_MOCK:
        logger.warning("카카오 대중교통 경로 조회 생략: USE_MOCK=1입니다.")
        return None
    if not config.KAKAO_REST_API_KEY:
        logger.warning("카카오 대중교통 경로 조회 생략: KAKAO_REST_API_KEY가 없습니다.")
        return None

    try:
        request = _build_request(origin_lat, origin_lng, dest_lat, dest_lng)
    except (TypeError, ValueError):
        logger.warning("카카오 대중교통 경로 조회 실패: 입력 좌표가 올바르지 않습니다.")
        return None

    body = _request_body(request)
    if body is None:
        return None

    try:
        data = json.loads(body.decode("utf-8"))
        return _parse_routes(data)
    except (UnicodeDecodeError, json.JSONDecodeError, RouteParseError, TypeError, ValueError) as error:
        # 응답 원문과 예외 메시지는 저장하거나 로그에 남기지 않는다.
        logger.warning("카카오 대중교통 경로 조회 실패: 응답 파싱 오류(%s)입니다.", type(error).__name__)
        return None
    except Exception as error:
        logger.warning("카카오 대중교통 경로 조회 실패: 예상하지 못한 파싱 오류(%s)입니다.", type(error).__name__)
        return None
