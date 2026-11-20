"""축제 후 귀가 분산 도구 (도구 담당, 데모 장면 7). .kiro/specs/return-dispersal/ 을 따른다.

행사가 끝나는 시간대에 행사 대표 장소(main_place_id)의 가까운 역 1개가 붐빈다고 보고, 도착역까지 덜 붐비는
출발 시각과 걸어서 갈 다른 역을 제안한다. LLM 을 쓰지 않는 계산이다.

- 역 혼잡은 규칙으로 추정한 값이다. 실측·실시간이 아니고, 혼잡 시간대도 근거 데이터 없이 정한 가정이다.
  집중률(congestion.json)은 쓰지 않는다. 역별 혼잡 숫자·등급을 만들지 않는다.
- 이동 시간은 역 좌표(stations.json)와 travel_times.json 의 rule 로 계산한 추정이다. 실제 경로·시간표가 아니고,
  경로 API 를 부르거나 그 결과를 저장하지 않는다.
- 현재 시각을 쓰지 않는다. 결과는 입력(date, planned_departure)과 app/data/ 의 파일로만 정해진다.
- 출처(sources)는 도구가 돌려주지 않는다. 다른 조회 도구처럼 app/chat/answer.py 가 도구 이름으로 조립한다.
"""

import datetime as dt
import math

from strands import tool

from app.tools import lookup
from app.tools.lookup import LookupFailure, _load_json, _load_places, _parse_date, _safe

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
    "Travel times are estimated from station coordinates, not routes or timetables, "
    "and exclude walking to and from stations."
)


def station_table() -> dict[str, dict]:
    """stations.json 의 역 표 {역 이름(station): 역}. transit.py·restaurants.py 도 쓴다."""
    return {s["station"]: s for s in _load_json("stations.json")["stations"]}


def travel_rule() -> dict:
    """travel_times.json 의 rule 중 역·도보 추정에 쓰는 값. 기존 이동 시간 표와 같은 값을 쓴다."""
    all_rules = _load_json("travel_times.json")["rule"]
    return {key: all_rules[key] for key in RULE_KEYS}


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
    baseline_min = subway_minutes(origin, dest, rule)
    options = []
    if congested:
        def shift(kind: str, at: dt.datetime, warning: str) -> dict:
            return {"type": kind, "depart_at": at.isoformat(), "station": crowded["station"], "walk_min": 0,
                    "extra_min": 0, "avoids_congestion": not in_window(at), "warnings": [warning]}

        earlier = end - dt.timedelta(minutes=EARLY_LEAVE_BEFORE_END_MIN)
        if earlier > start:  # 행사가 시작하기도 전에 떠나라는 제안은 하지 않는다
            options.append(shift("shift_earlier", earlier, "leaves_before_event_end"))
        options.append(shift("shift_later", window_to, "last_train_unknown"))  # 막차 시각은 모른다. 경고만 붙인다
        walks = sorted(
            (straight_km(crowded, s), s["station"]) for s in stations.values() if s["station"] != crowded["station"]
        )
        for _, name in walks:  # 가까운 순
            walk_min = walk_minutes(crowded, stations[name], rule)
            if walk_min > WALK_ALT_MAX_MIN:
                break
            options.append({
                "type": "walk_to_station", "depart_at": depart.isoformat(), "station": name, "walk_min": walk_min,
                "extra_min": walk_min + subway_minutes(stations[name], dest, rule) - baseline_min,
                "avoids_congestion": name != crowded["station"], "warnings": [],
            })
        # extra_min 이 작은 순. 같으면 시각 제안이 먼저(안정 정렬이라 그 안의 순서는 그대로)
        options = sorted(options, key=lambda o: (o["extra_min"], o["type"] == "walk_to_station"))[:MAX_OPTIONS]

    return {
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
        "baseline": {"depart_at": depart.isoformat(), "station": origin["station"], "congested": congested,
                     "minutes": baseline_min, "mode": "subway"},
        "options": options,
    }


@tool
@_safe
def get_return_options(date: str, place_id: str | None = None, event_name: str | None = None,
                       destination_station: str | None = None, destination_place_id: str | None = None,
                       planned_departure: str | None = None) -> dict:
    """Suggest less crowded ways to get back after an event: a different departure time, or walking to another
    metro station. Use it when the user asks how to return (for example to their hotel) after a festival or event ends.
    Pass the date and at least one of event_name or place_id.

    Everything here is a rule-based estimate, not measured or real-time crowding. Only one station is treated as
    crowded: the station nearest to the event's main place. The crowded window (30 minutes before to 60 minutes after
    the event end) is an assumption made without supporting data. Travel times are rough estimates from station
    coordinates, not real routes or timetables, and they exclude walking between places and stations. The last train
    time is unknown. So say "expected to be crowded" and "about N minutes", never state lines or transfers, and when
    an option has the warning last_train_unknown tell the user to check the last train.
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
        "baseline": {"depart_at", "station", "congested", "minutes": estimated minutes from the origin station to the
            destination station, "mode": "subway"},
        "options": up to 5 suggestions sorted by extra_min, each {"type": "shift_earlier" | "shift_later" |
            "walk_to_station", "depart_at", "station": station to board at, "walk_min": walking minutes to that
            station, "extra_min": estimated extra minutes versus the baseline (can be negative),
            "avoids_congestion", "warnings": "leaves_before_event_end" | "last_train_unknown"}}.
        Times are ISO strings (+09:00). options is empty and baseline.congested is false when the planned departure
        is outside the crowded window or the origin's station is not the crowded station.
        On failure returns {"error": {"code", "message"}}: invalid_date, invalid_time, missing_argument,
        place_not_found, event_not_found, ambiguous_event, no_time_basis (event hours unknown), no_event_station,
        station_not_found, no_station, same_station, data_unavailable.
    """
    return return_options(date, place_id, event_name, destination_station, destination_place_id, planned_departure)
