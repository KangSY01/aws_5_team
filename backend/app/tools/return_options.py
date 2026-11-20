"""축제 후 귀가 분산 도구 (도구 담당, 데모 장면 7). .kiro/specs/return-dispersal/ 을 따른다.

행사가 끝나는 시간대에 행사 대표 장소(main_place_id)의 가까운 역 1개가 붐빈다고 보고, 도착역까지 덜 붐비는
출발 시각과 걸어서 갈 다른 역을 제안한다. LLM 을 쓰지 않는 계산이다.

- 역 혼잡은 규칙으로 추정한 값이다. 실측·실시간이 아니고, 혼잡 시간대도 근거 데이터 없이 정한 가정이다.
  집중률(congestion.json)은 쓰지 않는다. 역별 혼잡 숫자·등급을 만들지 않는다.
- 이동 시간은 카카오 실시간 대중교통 경로를 우선하고, 실패하면 역 좌표와 travel_times.json 규칙의 추정값을 쓴다.
  카카오 응답은 파일·DB·메모리 캐시에 저장하지 않는다. 막차 시각·경고만 부산교통공사 표준 시간표(last_trains.json)를 쓴다.
- 현재 시각을 쓰지 않는다. 일정 시각은 입력(date, planned_departure)으로 정하고, 이동 시간만 실시간 경로를 우선한다.
- 출처(sources)는 도구가 돌려주지 않는다. 다른 조회 도구처럼 app/chat/answer.py 가 도구 이름으로 조립한다.
"""

import datetime as dt
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

from strands import tool

from app import config
from app.ranking import rank_routes
from app.tools import lookup
from app.tools.kakao_route import fetch_routes
from app.tools.lookup import LookupFailure, _load_json, _load_places, _parse_date, _safe

logger = logging.getLogger(__name__)

# 기준값. 혼잡 시간대(30·60분)는 실측이 아니라 가정이다. 리허설에서 데모 데이터로 맞추고 고정한다.
STATION_CROWD_BEFORE_MIN = 30  # 행사 종료 몇 분 전부터 혼잡으로 보는지
STATION_CROWD_AFTER_MIN = 60  # 행사 종료 몇 분 뒤까지 혼잡으로 보는지 (끝은 제외)
EARLY_LEAVE_BEFORE_END_MIN = 40  # shift_earlier 출발 시각. 혼잡 시작보다 10분 이르다
WALK_ALT_MAX_MIN = 20  # 다른 역까지 걷는 시간 상한
MAX_OPTIONS = 5  # 제안 최대 개수
DEFAULT_DESTINATION_STATION = "Seomyeon"  # 도착역 기본값(데모 숙소가 서면). 숙소가 바뀌면 이 값만 바꾼다

RULE_KEYS = ("route_factor", "subway_kmh", "subway_overhead_min", "walk_kmh")  # travel_times.json 의 rule 중 쓰는 값
UNKNOWN_HOURS = ("00:00:00", "23:59:59")  # get_events 가 진행 시간을 모르는 행사에 붙이는 시각
NOTE = (
    "Rule-based estimate, not measured or real-time crowding. The crowded window "
    f"({STATION_CROWD_BEFORE_MIN} min before to {STATION_CROWD_AFTER_MIN} min after the event end) is an assumption. "
    "Travel times use live Kakao public-transit routes when available and otherwise fall back to estimates from "
    "station coordinates; they exclude walking to and from places. Kakao route results are not stored or cached. "
    "Last-train warnings use the stored Busan Metro standard timetable when the requested "
    "station and direction are available; actual train times can differ."
)


def station_table() -> dict[str, dict]:
    """stations.json 의 역 표 {역 이름(station): 역}. transit.py·restaurants.py 도 쓴다."""
    return {s["station"]: s for s in _load_json("stations.json")["stations"]}


def travel_rule() -> dict:
    """travel_times.json 의 rule 중 역·도보 추정에 쓰는 값. 기존 이동 시간 표와 같은 값을 쓴다."""
    all_rules = _load_json("travel_times.json")["rule"]
    return {key: all_rules[key] for key in RULE_KEYS}


def _service_day_code(day: dt.date) -> str:
    """열차시각표 요일 코드. 공휴일 달력은 없으므로 토·일만 구분하고 평일 공휴일은 평일로 본다."""
    return "2" if day.weekday() == 5 else "3" if day.weekday() == 6 else "1"


def _last_train(day: dt.date, station: str, toward: str) -> tuple[str, dt.datetime] | None:
    """저장된 표에서 해당 역·방향·요일의 막차 ("HH:MM", 그 시각). 파일·행·값이 없거나 이상하면 None.

    자정 뒤 막차는 "24:05"처럼 24시 이상 그대로 두고, 시각은 운행일(day) 00:00 에 더한 값이다.
    """
    try:
        row = _load_json("last_trains.json")["stations"][station]
        if row["toward"] != toward:
            return None
        hour_text, minute_text = row["last_train"][_service_day_code(day)].split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 47 or not 0 <= minute < 60:
            return None
    except (LookupFailure, AttributeError, KeyError, TypeError, ValueError):
        return None
    at = dt.datetime.combine(day, dt.time(), lookup.KST) + dt.timedelta(hours=hour, minutes=minute)
    return f"{hour:02d}:{minute:02d}", at


def last_train_text(day: dt.date, station: str, toward: str) -> str | None:
    """응답의 last_train 값: 막차 시각 "HH:MM" (자정 뒤는 24시 이상). 표에 없으면 None."""
    found = _last_train(day, station, toward)
    return found[0] if found else None


def last_train_warnings(day: dt.date, station: str, toward: str, departure: dt.datetime) -> list[str]:
    """막차 표가 없으면 unknown, 막차 뒤면 missed, 탈 수 있는 시각이면 빈 목록."""
    found = _last_train(day, station, toward)
    if found is None:
        return ["last_train_unknown"]
    return ["last_train_missed"] if departure > found[1] else []


def find_station(stations: dict[str, dict], name: str) -> str | None:
    """영어 역 이름을 대소문자와 앞뒤 공백을 무시하고 역 표의 이름으로 바꾼다. 없으면 None."""
    return {key.casefold(): key for key in stations}.get(name.strip().casefold())


def straight_km(a: dict, b: dict) -> float:
    """두 좌표 사이의 직선거리(km, haversine). a·b 는 lat·lng 가 있는 dict (역, 장소, 음식점)."""
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lng"] - a["lng"]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def subway_minutes(a: dict, b: dict, rule: dict) -> int:
    """역 a → 역 b 지하철 추정 시간(분, 올림). 같은 역이면 0. scripts/build_travel_times.py 의 subway 규칙과 같다."""
    if a["station"] == b["station"]:
        return 0
    raw = straight_km(a, b) * rule["route_factor"] / rule["subway_kmh"] * 60 + rule["subway_overhead_min"]
    return math.ceil(round(raw, 6))  # round: 부동소수점 오차로 1분이 더 올라가지 않게 한다


def walk_minutes(a: dict, b: dict, rule: dict) -> int:
    """역 a → 역 b 도보 추정 시간(분, 올림)."""
    return math.ceil(round(straight_km(a, b) * rule["route_factor"] / rule["walk_kmh"] * 60, 6))


KAKAO_DETAIL_KEYS = ("route_type", "transfers", "distance_m", "fare", "walk_meters", "legs")


def _first_kakao_route(origin: dict, destination: dict) -> dict | None:
    """두 역 사이 카카오 경로의 첫 항목. fetch_routes의 예외나 형식 오류도 실패로 본다."""
    try:
        routes = fetch_routes(origin["lat"], origin["lng"], destination["lat"], destination["lng"])
    except Exception as error:
        logger.warning("카카오 역간 경로 조회 실패: %s", type(error).__name__)
        return None
    if not routes:
        return None
    route = routes[0]
    if (
        not isinstance(route, dict)
        or type(route.get("total_minutes")) is not int
        or route["total_minutes"] < 0
        or any(key not in route for key in KAKAO_DETAIL_KEYS)
        or not isinstance(route.get("legs"), list)
    ):
        logger.warning("카카오 역간 경로 조회 실패: 첫 경로 형식이 올바르지 않습니다.")
        return None
    return route


def _kakao_routes_by_station(origins: list[dict], destination: dict) -> dict[str, dict]:
    """서로 다른 출발역을 병렬 조회한다. 결과는 이 호출 안에서 중복 조회를 피할 때만 쓴다."""
    if config.USE_MOCK or not config.KAKAO_REST_API_KEY:
        return {}
    unique = {station["station"]: station for station in origins}
    if not unique:
        return {}

    # fetch_routes가 역마다 최대 3초 한 번만 기다리므로 모두 병렬로 실행하면 전체도 3초대에 끝난다.
    found: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(unique)) as executor:
        futures = {
            executor.submit(_first_kakao_route, station, destination): name
            for name, station in unique.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                route = future.result()
            except Exception as error:
                logger.warning("카카오 병렬 경로 조회 실패: %s", type(error).__name__)
                continue
            if route is not None:
                found[name] = route
    return found


def _stop_names(name: object, mode: object, stations: dict[str, dict]) -> dict[str, str]:
    """카카오 승하차 이름의 언어별 이름. 장소의 names 처럼 있는 언어만 넣는다.

    en 은 역 표의 station, ja·zh-Hans·zh-Hant 는 역 표의 names 에 있을 때만 넣는다 (지금은 2호선 역 일부).

    지하철 구간의 이름만 '역'을 떼고 역 표의 name_ko 와 비교한다. 카카오는 "서면"처럼 '역' 없이 준다.
    버스 정류장과 역 표에 없는 역은 한국어 원문만 넣고, 이름이 없으면(도보 구간) 빈 dict 다.
    """
    if not isinstance(name, str) or not name:
        return {}
    names = {"ko": name}
    if mode == "SUBWAY":
        by_ko = {station["name_ko"].removesuffix("역"): station for station in stations.values()}
        station = by_ko.get(name.strip().removesuffix("역"))
        if station:
            names = {**names, "en": station["station"], **station.get("names", {})}
    return names


def _time_source_fields(route: dict | None, stations: dict[str, dict]) -> dict:
    """후보 시간의 출처와, 카카오 성공 시 첫 경로의 노선·승하차 요약을 만든다."""
    if route is None:
        return {"time_source": "estimate"}
    fields = {"time_source": "kakao", **{key: route[key] for key in KAKAO_DETAIL_KEYS}}
    # 카카오가 준 leg 는 그대로 두고 언어별 이름만 덧붙인 사본을 넣는다
    fields["legs"] = [
        {**leg, "from_names": _stop_names(leg.get("from_name"), leg.get("mode"), stations),
         "to_names": _stop_names(leg.get("to_name"), leg.get("mode"), stations)}
        if isinstance(leg, dict) else leg
        for leg in route["legs"]
    ]
    return fields


def _destination(stations: dict, places: dict, station: str | None, place_id: str | None) -> dict:
    """도착역 결정: destination_station → destination_place_id 의 nearest_station → 기본값. 앞의 것이 있으면 뒤는 보지 않는다."""
    if not station and place_id:
        if place_id not in places:
            raise LookupFailure("place_not_found", f"destination_place_id {place_id!r} is not a known place.")
        name = places[place_id]["nearest_station"]
        if name not in stations:
            raise LookupFailure("no_station", f"Place {place_id!r} has no station in the station table.")
        return {"station": name, "place_id": place_id, "is_default": False}
    name = find_station(stations, station or DEFAULT_DESTINATION_STATION)
    if name is None:
        raise LookupFailure(
            "station_not_found",
            f"destination_station {station or DEFAULT_DESTINATION_STATION!r} is not in the station table. "
            "Use the English name of a Busan Metro line 1-4 station (for example 'Seomyeon').",
        )
    return {"station": name, "place_id": None, "is_default": not station}


def _find_event(events: list[dict], day: dt.date, event_name: str | None, place_id: str | None) -> dict:
    if event_name:
        found = [e for e in events if e["name"] == event_name]
    else:
        found = [e for e in events if place_id in e["place_ids"]]
    if not found:
        raise LookupFailure("event_not_found", f"No matching event on {day.isoformat()}. Check get_events for that date.")
    if len(found) > 1 and not event_name:
        names = ", ".join(e["name"] for e in found)
        raise LookupFailure("ambiguous_event", f"More than one event includes this place. Pass event_name: {names}")
    return found[0]


def return_options(date: str, place_id: str | None = None, event_name: str | None = None,
                   destination_station: str | None = None, destination_place_id: str | None = None,
                   planned_departure: str | None = None) -> dict:
    """get_return_options 의 계산. 실패는 LookupFailure 로 알린다 (도구가 오류 dict 로 바꾼다)."""
    day = _parse_date(date)
    if not place_id and not event_name:
        raise LookupFailure("missing_argument", "Pass event_name or place_id (or both).")
    places = {p["place_id"]: p for p in _load_places()}
    if place_id and place_id not in places:
        raise LookupFailure("place_not_found", f"place_id {place_id!r} is not a known place.")
    stations, rule = station_table(), travel_rule()
    destination = _destination(stations, places, destination_station, destination_place_id)

    # get_events 는 @tool 이지만 그대로 부를 수 있다(Guardian 도 그렇게 부른다). 오류 dict 는 같은 코드로 다시 알린다.
    found = lookup.get_events(date=day.isoformat())
    if "error" in found:
        raise LookupFailure(found["error"]["code"], found["error"]["message"])
    event = _find_event(found["events"], day, event_name, place_id)
    if (event["start"][11:19], event["end"][11:19]) == UNKNOWN_HOURS:
        raise LookupFailure("no_time_basis", "The event's hours are unknown, so there is no basis for a crowded window.")
    start, end = dt.datetime.fromisoformat(event["start"]), dt.datetime.fromisoformat(event["end"])

    # 혼잡 역은 행사 대표 장소의 역 1개뿐이다. 다른 행사 장소의 역은 혼잡 역으로 보지 않는다.
    main_place_id = event["main_place_id"]
    crowded = stations.get(places.get(main_place_id, {}).get("nearest_station"))
    if crowded is None:
        raise LookupFailure("no_event_station", "The event's main place has no station in the station table.")
    origin_place_id = place_id or main_place_id
    origin = stations.get(places[origin_place_id]["nearest_station"])
    if origin is None:
        raise LookupFailure("no_station", f"Place {origin_place_id!r} has no station in the station table.")
    if destination["station"] in (crowded["station"], origin["station"]):
        raise LookupFailure("same_station", "The destination is the station you would leave from, so there is nothing to suggest.")
    dest = stations[destination["station"]]

    window_from = end - dt.timedelta(minutes=STATION_CROWD_BEFORE_MIN)
    window_to = end + dt.timedelta(minutes=STATION_CROWD_AFTER_MIN)

    def in_window(t: dt.datetime) -> bool:
        return window_from <= t < window_to  # 시작 포함, 끝 제외

    depart = end
    if planned_departure:
        try:
            depart = dt.datetime.combine(day, dt.time.fromisoformat(planned_departure.strip()), start.tzinfo)
        except ValueError:
            raise LookupFailure("invalid_time", "planned_departure must be HH:MM.") from None
        if depart < start:  # 행사 시작보다 이른 시각은 자정을 넘긴 다음 날로 본다
            depart += dt.timedelta(days=1)

    congested = in_window(depart) and origin["station"] == crowded["station"]
    baseline_estimate = subway_minutes(origin, dest, rule)
    options = []
    if congested:
        def shift(kind: str, at: dt.datetime, warnings: list[str]) -> dict:
            return {"type": kind, "depart_at": at.isoformat(), "station": crowded["station"], "walk_min": 0,
                    "extra_min": 0, "avoids_congestion": not in_window(at), "warnings": warnings}

        earlier = end - dt.timedelta(minutes=EARLY_LEAVE_BEFORE_END_MIN)
        if earlier > start:  # 행사가 시작하기도 전에 떠나라는 제안은 하지 않는다
            options.append(shift("shift_earlier", earlier, ["leaves_before_event_end"]))
        options.append(shift("shift_later", window_to, []))
        walks = sorted(
            (straight_km(crowded, s), s["station"]) for s in stations.values() if s["station"] != crowded["station"]
        )
        for _, name in walks:  # 가까운 순
            walk_min = walk_minutes(crowded, stations[name], rule)
            if walk_min > WALK_ALT_MAX_MIN:
                break
            options.append({
                "type": "walk_to_station", "depart_at": depart.isoformat(), "station": name, "walk_min": walk_min,
                "extra_min": walk_min + subway_minutes(stations[name], dest, rule) - baseline_estimate,
                "avoids_congestion": name != crowded["station"], "warnings": [],
            })

    def last_train_fields(station: str, boards_at: dt.datetime) -> dict:
        """그 역에서 도착역 방향 막차 시각과, 역에 닿는 시각(boards_at)을 막차와 비교한 경고."""
        if station == destination["station"]:  # 걸어서 도착역까지 가는 안은 열차를 타지 않는다
            return {"last_train": None, "warnings": []}
        return {"last_train": last_train_text(day, station, destination["station"]),
                "warnings": last_train_warnings(day, station, destination["station"], boards_at)}

    for option in options:  # 도보안은 걸어서 그 역에 도착하는 시각으로 비교한다
        boards_at = dt.datetime.fromisoformat(option["depart_at"]) + dt.timedelta(minutes=option["walk_min"])
        fields = last_train_fields(option["station"], boards_at)
        option["last_train"] = fields["last_train"]
        option["warnings"] = option["warnings"] + fields["warnings"]

    # 기준역과 후보 출발역을 한 번씩만, 서로 다른 역은 병렬로 조회한다. 이 지역 변수는 함수 밖에 보관하지 않는다.
    departure_stations = [origin, *(stations[option["station"]] for option in options)]
    kakao_by_station = _kakao_routes_by_station(departure_stations, dest)
    baseline_route = kakao_by_station.get(origin["station"])
    baseline_min = baseline_route["total_minutes"] if baseline_route is not None else baseline_estimate

    for option in options:
        departure_station = stations[option["station"]]
        route = kakao_by_station.get(option["station"])
        station_minutes = (
            route["total_minutes"] if route is not None else subway_minutes(departure_station, dest, rule)
        )
        option["extra_min"] = option["walk_min"] + station_minutes - baseline_min
        option.update(_time_source_fields(route, stations))

    # 기존 options 필드는 유지하고, 갱신된 시간 기준으로 기존 상한과 안정 정렬을 적용한다.
    options = sorted(options, key=lambda o: (o["extra_min"], o["type"] == "walk_to_station"))[:MAX_OPTIONS]
    baseline = {
        "depart_at": depart.isoformat(), "station": origin["station"], "congested": congested,
        "minutes": baseline_min, "mode": "subway", **last_train_fields(origin["station"], depart),
        **_time_source_fields(baseline_route, stations),
    }
    result = {
        "date": day.isoformat(),
        "basis": {
            "kind": "rule", "measured": False,
            "assumed_window": {"before_end_min": STATION_CROWD_BEFORE_MIN, "after_end_min": STATION_CROWD_AFTER_MIN},
            "travel_time_rule": rule,
            "note": NOTE,
        },
        "event": {"name": event["name"], "start": event["start"], "end": event["end"], "main_place_id": main_place_id},
        "origin": {"place_id": origin_place_id, "station": origin["station"]},
        "destination": destination,
        "congested_station": {"station": crowded["station"], "main_place_id": main_place_id,
                              "from": window_from.isoformat(), "to": window_to.isoformat()},
        "baseline": baseline,
        "options": options,
    }
    result["ranked"] = [route.model_dump() for route in rank_routes(result)]
    return result


@tool
@_safe
def get_return_options(date: str, place_id: str | None = None, event_name: str | None = None,
                       destination_station: str | None = None, destination_place_id: str | None = None,
                       planned_departure: str | None = None) -> dict:
    """Suggest less crowded ways to get back after an event: a different departure time, or walking to another
    metro station. Use it when the user asks how to return (for example to their hotel) after a festival or event ends.
    Pass the date and at least one of event_name or place_id.

    Station crowding is a rule-based estimate, not measured or real-time crowding. Only one station is treated as
    crowded: the station nearest to the event's main place. The crowded window (30 minutes before to 60 minutes after
    the event end) is an assumption made without supporting data. Travel times use live Kakao public-transit routes
    when available and otherwise fall back to rough estimates from station coordinates. Neither source includes the
    walk between a place and its station. Kakao route results are never stored or cached. When time_source is
    "kakao", route_type, transfers, fare, walk_meters, and legs come from Kakao; for "estimate", do not invent lines
    or transfers. Last-train warnings use a stored standard timetable only for the available station and direction.
    Actual train times can differ. The baseline and every option carry last_train, the last train from that
    station toward the destination, and are compared with it at the time the user reaches the station (departure
    plus walking minutes): last_train_missed when that is after the last train, no last-train warning when it is
    not, or last_train_unknown when no matching timetable is stored. State the last_train time when it is present
    and tell the user to check the live timetable for either warning. Say "expected to be crowded" and
    "about N minutes".
    The destination defaults to Seomyeon station (the demo hotel area). If destination.is_default is true, tell the
    user the result is based on Seomyeon. If the user names another destination, pass it as destination_station or
    destination_place_id.

    Args:
        date: Event date (YYYY-MM-DD).
        place_id: Place the user leaves from (a place_id from search_places or get_events). Without event_name,
            the event is the one on that date whose place_ids include this place.
        event_name: Event name exactly as returned by get_events (Korean original). Without place_id, the user is
            assumed to leave from the event's main place (main_place_id).
        destination_station: English name of the Busan Metro (lines 1-4) station to return to, for example
            "Seomyeon" or "Busan Station". Defaults to Seomyeon. Takes priority over destination_place_id.
        destination_place_id: A place_id to return to instead of a station name. Its nearest station is used.
        planned_departure: Planned departure time "HH:MM". A time earlier than the event start means the next day.
            Defaults to the event end time.

    Returns:
        {"date", "basis": {"kind": "rule", "measured": false, "assumed_window": {"before_end_min", "after_end_min"},
            "travel_time_rule": {...}, "note": the caveats above},
        "event": {"name", "start", "end", "main_place_id"},
        "origin": {"place_id", "station"},
        "destination": {"station", "place_id": set only when destination_place_id was used, "is_default"},
        "congested_station": {"station", "main_place_id", "from", "to"} (window start included, end excluded),
        "baseline": {"depart_at", "station", "congested", "minutes": travel minutes from the origin station
            to the destination station, "mode": "subway", "last_train", "warnings": "last_train_unknown" |
            "last_train_missed", "time_source": "kakao" | "estimate"},
        "options": up to 5 unranked suggestions sorted by extra_min, each {"type": "shift_earlier" | "shift_later" |
            "walk_to_station", "depart_at", "station": station to board at, "walk_min": walking minutes to that
            station, "extra_min": extra minutes versus the baseline (can be negative),
            "avoids_congestion", "last_train", "warnings": "leaves_before_event_end" | "last_train_unknown" |
            "last_train_missed", "time_source": "kakao" | "estimate"},
        last_train is the last train time "HH:MM" from that item's station toward the destination, from the
            Busan Transportation Corporation train timetable. Times after midnight stay at 24 or above ("24:05"
            means 00:05 the next day). null means the timetable has no entry (or the option walks all the way to
            the destination station). Actual service can differ.
        "ranked": rank_routes output in score order, with last_train_missed removed. Each item has {"option": the
            original option, "score", "travel_min", "arrive_at", "breakdown", "labels", "excluded"}. Labels are
            "best", "earliest_arrival", and "least_walking".
        When time_source is "kakao", baseline or option also has {"route_type", "transfers", "distance_m", "fare",
            "walk_meters", "legs": [{"mode", "minutes", "distance_m", "lines", "from_name", "to_name",
            "from_names", "to_names"}]}. from_name and to_name are Kakao's Korean stop names. from_names and to_names
            map a language to the same stop's name and hold only the languages in the data: "ko" always, plus "en"
            when a SUBWAY leg's stop is in the station table, plus "ja", "zh-Hans", "zh-Hant" where the station
            table has them (line 2 stations only). Use the user's language when it is present, otherwise
            the Korean name as it is; never translate or invent a stop name. Bus stops have only "ko"; legs without
            a stop name (walking) have {}.
        Times are ISO strings (+09:00). options and ranked are empty and baseline.congested is false when the planned
        departure is outside the crowded window or the origin's station is not the crowded station.
        On failure returns {"error": {"code", "message"}}: invalid_date, invalid_time, missing_argument,
        place_not_found, event_not_found, ambiguous_event, no_time_basis (event hours unknown), no_event_station,
        station_not_found, no_station, same_station, data_unavailable.
    """
    return return_options(date, place_id, event_name, destination_station, destination_place_id, planned_departure)
