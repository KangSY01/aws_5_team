"""대중교통(지하철) 정보 도구 (도구 담당). .kiro/specs/info-tools/ 를 따른다.

두 장소(또는 장소와 역) 사이의 가까운 역, 역에 서는 호선, 역까지 도보 분, 지하철 추정 분을 돌려준다. LLM 을 쓰지 않는다.

- 이동 시간은 좌표(places.json, stations.json)와 travel_times.json 의 rule 로 계산한 추정이다. 실제 경로·시간표가 아니다.
  계산은 return_options.py 의 함수(walk_minutes, subway_minutes)를 그대로 써서 귀가 분산 도구와 값이 같다.
- 환승 횟수·환승 위치·타는 호선·막차·배차·요금은 만들지 않는다. lines 는 그 역에 서는 호선(참고 값)이다.
- 역 표에는 부산 도시철도 1~4호선만 있다. 동해선·경전철 역은 없어서 그런 역이 가까운 장소는 no_station 이다.
- 경로 API 를 부르지 않고, 현재 시각도 쓰지 않는다. 결과는 입력과 app/data/ 의 파일로만 정해진다.
"""

from strands import tool

from app.tools.lookup import LookupFailure, _load_places, _safe
from app.tools.return_options import (
    WALK_ALT_MAX_MIN,
    find_station,
    station_table,
    subway_minutes,
    travel_rule,
    walk_minutes,
)

FAR_FROM_STATION_MIN = WALK_ALT_MAX_MIN  # 장소에서 역까지 걷는 시간이 이 값을 넘으면 far_from_station 경고 (귀가 도구의 도보 상한과 같은 값)
NOT_INCLUDED = ["timetable", "real_time", "first_last_train", "fare", "transfer_walk"]  # 데이터에 없는 항목
NOTE = (
    "Estimated from coordinates, not routes or timetables. 'lines' are the lines that serve each station "
    "(reference only). Transfers between the two stations are not computed."
)
COVERAGE = "Busan Metro lines 1-4 only. Donghae Line and light rail stations are not in the station table."


def _station_side(station: dict, place: dict | None, walk_key: str, rule: dict) -> dict:
    """응답의 from·to 한쪽. place 가 없으면(역 이름으로 받은 도착) 걷는 시간은 0 이다."""
    walk_min = walk_minutes(place, station, rule) if place else 0
    return {
        "place_id": place["place_id"] if place else None,
        "station": station["station"],
        "station_ko": station["name_ko"],
        "lines": station["lines"],
        "is_transfer_station": len(station["lines"]) >= 2,
        walk_key: walk_min,
        "warnings": ["far_from_station"] if walk_min > FAR_FROM_STATION_MIN else [],
    }


def transit_info(from_place_id: str, to_place_id: str | None = None, to_station: str | None = None) -> dict:
    """get_transit_info 의 계산. 실패는 LookupFailure 로 알린다 (도구가 오류 dict 로 바꾼다).

    검증 순서(오류 코드가 항상 같게): missing_argument → place_not_found(출발) → same_place → 도착 결정
    (to_station 이 있으면 station_not_found, 없으면 to_place_id 의 place_not_found) → no_station(출발, 도착 순).
    """
    if not to_place_id and not to_station:
        raise LookupFailure("missing_argument", "Pass to_place_id or to_station.")
    places = {p["place_id"]: p for p in _load_places()}
    if from_place_id not in places:
        raise LookupFailure("place_not_found", f"from_place_id {from_place_id!r} is not a known place.")
    if not to_station and to_place_id == from_place_id:
        raise LookupFailure("same_place", "from_place_id and to_place_id are the same place.")
    stations, rule = station_table(), travel_rule()

    def station_of(place_id: str) -> dict:
        station = stations.get(places[place_id]["nearest_station"])
        if station is None:
            raise LookupFailure(
                "no_station",
                f"Place {place_id!r} has no station in the station table. "
                "Only Busan Metro lines 1-4 are covered; Donghae Line and light rail stations are not in the data.",
            )
        return station

    if to_station:  # to_station 이 우선이고 to_place_id 는 검증하지 않는다
        name = find_station(stations, to_station)
        if name is None:
            raise LookupFailure(
                "station_not_found",
                f"to_station {to_station!r} is not in the station table. "
                "Use the English name of a Busan Metro line 1-4 station (for example 'Seomyeon').",
            )
        to_place = None
    elif to_place_id not in places:
        raise LookupFailure("place_not_found", f"to_place_id {to_place_id!r} is not a known place.")
    else:
        to_place = places[to_place_id]
    origin = station_of(from_place_id)
    arrival = stations[name] if to_station else station_of(to_place_id)

    start = _station_side(origin, places[from_place_id], "walk_to_station_min", rule)
    end = _station_side(arrival, to_place, "walk_from_station_min", rule)
    subway_min = subway_minutes(origin, arrival, rule)  # 같은 역이면 0
    return {
        "from": start,
        "to": end,
        "subway": {"minutes": subway_min, "same_station": origin["station"] == arrival["station"]},
        "total_min": start["walk_to_station_min"] + subway_min + end["walk_from_station_min"],
        "basis": {
            "kind": "rule", "measured": False,
            "travel_time_rule": rule,
            "note": NOTE,
            "not_included": NOT_INCLUDED,
            "coverage": COVERAGE,
        },
    }


@tool
@_safe
def get_transit_info(from_place_id: str, to_place_id: str | None = None, to_station: str | None = None) -> dict:
    """Get rough metro travel information between two places, or from a place to a metro station: the nearest
    station on each side, walking minutes to and from the stations, and the estimated subway minutes.
    Use it when the user asks how to get somewhere by subway or how long it takes.
    Pass from_place_id and one of to_place_id or to_station.

    All times are estimates from coordinates, not real routes or timetables. Say "about N minutes".
    "lines" lists the lines that stop at each station, for reference only: do not state which line to take, whether
    or where to transfer, or how many transfers there are. Timetables, real-time arrivals, first and last train
    times, train intervals and fares are unknown: never state them. Only Busan Metro lines 1-4 are covered; the
    Donghae Line and light rail are not in the data (such places return no_station).

    Args:
        from_place_id: Place to leave from (a place_id from search_places).
        to_place_id: Place to go to (a place_id from search_places). Its nearest station is the arrival station.
        to_station: English name of the Busan Metro station to go to, for example "Seomyeon" or "Busan Station".
            Case and surrounding spaces are ignored. Takes priority over to_place_id.

    Returns:
        {"from": {"place_id", "station": English station name, "station_ko": Korean station name,
            "lines": lines serving the station, "is_transfer_station": true when two or more lines stop there,
            "walk_to_station_min": walking minutes from the place to the station, "warnings"},
        "to": {same fields, with "walk_from_station_min" instead; "place_id" is null and the walk is 0 when
            to_station was used},
        "subway": {"minutes": estimated subway minutes between the two stations, "same_station": true when both
            sides use the same station (minutes is then 0, so walking is the better answer)},
        "total_min": walk_to_station_min + subway.minutes + walk_from_station_min,
        "basis": {"kind": "rule", "measured": false, "travel_time_rule", "note",
            "not_included": what the data does not have, "coverage"}}.
        warnings contains "far_from_station" when the walk to or from the station is over 20 minutes; then say the
        station is far and another way (bus or taxi) may be better, without inventing routes.
        On failure returns {"error": {"code", "message"}}: missing_argument, place_not_found, same_place,
        station_not_found, no_station, data_unavailable.
    """
    return transit_info(from_place_id, to_place_id, to_station)
