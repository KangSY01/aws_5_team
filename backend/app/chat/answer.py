"""모델 답변 검증과 sources 조립. LLM 을 부르지 않는다.

모델은 장소를 [place:PLACE_ID] 표식으로만 쓴다. 코드가 그 ID 가 이번 요청의 도구 결과나 현재 일정에서 나온 것인지
확인하고, 프로필 언어의 장소 이름으로 바꾼다. 그래서 답변에 없는 장소가 들어갈 수 없고, 장소 이름도 모델이 번역하지 않는다.
"""

import re

from app.chat.messages import message
from app.chat.plan_rules import load_places, place_name
from app.chat.tools import ToolOutput, place_ids_in
from app.models.api import Source
from app.models.plan import Language

TOKEN = re.compile(r"\[place:\s*([^\]\s]+)\s*\]")
MIN_NAME_LEN = 3  # 이보다 짧은 장소 이름은 일반 단어와 겹칠 수 있어 본문 검사에서 뺀다


class InvalidAnswer(ValueError):
    """모델 답변이 근거 없는 장소를 담고 있다."""


def referenced_ids(text: str) -> list[str]:
    return list(dict.fromkeys(TOKEN.findall(text)))


def _all_names(place_id: str) -> list[str]:
    place = load_places()[place_id]
    return sorted((n for n in place.names.values() if n), key=len, reverse=True)


def restaurant_names(outputs: list[ToolOutput]) -> dict[str, dict[str, str]]:
    """이번 요청의 get_restaurants 결과에 실제로 나온 음식점: restaurant_id → 이름들 ({"ko": name_ko, 언어: 이름}).

    restaurant_id("kto-…")는 places.json 의 place_id 가 아니다. 답변 표식으로만 쓸 수 있고 일정에는 넣을 수 없다
    (일정 도구는 places.json 의 ID 만 받는다).
    """
    found: dict[str, dict[str, str]] = {}
    for out in outputs:
        if out.name != "get_restaurants" or not isinstance(out.data, dict):
            continue
        for item in out.data.get("restaurants") or []:
            if not isinstance(item, dict) or not isinstance(item.get("restaurant_id"), str):
                continue
            names = {k: v for k, v in (item.get("names") or {}).items() if isinstance(v, str) and v}
            if isinstance(item.get("name_ko"), str) and item["name_ko"]:
                names["ko"] = item["name_ko"]
            if names:
                found[item["restaurant_id"]] = names
    return found


def _restaurant_name(names: dict[str, str], language: Language) -> str:
    """프로필 언어 이름, 없으면 한국어 원래 이름 (get_restaurants docstring: 언어가 없으면 name_ko)."""
    return names.get(language) or names.get("ko") or next(iter(names.values()))


def render_answer(text: str, language: Language, grounded: set[str],
                  restaurants: dict[str, dict[str, str]] | None = None) -> str:
    """[place:ID] 를 프로필 언어 이름으로 바꾼다. 근거 없는 장소가 있으면 InvalidAnswer.

    grounded: 이번 요청에서 근거가 있는 place_id (성공한 도구 결과에 나온 장소, 현재 일정, 만든 일정).
    restaurants: 이번 요청의 get_restaurants 가 돌려준 음식점 (restaurant_names). 그 restaurant_id 표식만 음식점 이름으로 바꾼다.
    표식 없이 쓴 장소 이름도 검사한다: places.json 의 장소인데 grounded 가 아니면 모델이 기억에서 꺼낸 것으로 본다.
    """
    places = load_places()
    restaurants = restaurants or {}

    def known(pid: str) -> bool:
        return (pid in grounded and pid in places) or pid in restaurants

    bad = [pid for pid in referenced_ids(text) if not known(pid)]
    if bad:
        raise InvalidAnswer(f"근거 없는 place_id 가 답변에 있습니다: {', '.join(bad)}")

    def name(match: re.Match) -> str:
        pid = match.group(1)
        return place_name(places[pid], language) if pid in places else _restaurant_name(restaurants[pid], language)

    rendered = TOKEN.sub(name, text).strip()

    remaining = rendered
    for pid in grounded & places.keys():  # 근거 있는 이름을 먼저 지워 다른 장소 이름의 일부와 겹쳐도 오탐하지 않는다
        for name in _all_names(pid):
            remaining = re.sub(re.escape(name), " ", remaining, flags=re.IGNORECASE)
    for pid in places.keys() - grounded:
        if any(len(name) >= MIN_NAME_LEN and name.casefold() in remaining.casefold() for name in _all_names(pid)):
            raise InvalidAnswer(f"도구 결과에 없는 장소 {pid} 가 답변에 있습니다.")
    return rendered


def _return_route(data: dict) -> tuple[str, str] | None:
    """get_return_options 결과의 (출발역, 도착역). 계산 결과가 아니면(오류 dict 등) None. 역 이름은 도구가 준 영어 이름 그대로다."""
    origin = (data.get("baseline") or {}).get("station")
    destination = (data.get("destination") or {}).get("station")
    if isinstance(origin, str) and origin and isinstance(destination, str) and destination:
        return origin, destination
    return None


def _transit_route(data: dict) -> tuple[str, str] | None:
    """get_transit_info 결과의 (출발역, 도착역). 계산 결과가 아니면(오류 dict 등) None. 역 이름은 도구가 준 영어 이름 그대로다."""
    start, end = data.get("from"), data.get("to")
    origin = start.get("station") if isinstance(start, dict) else None
    destination = end.get("station") if isinstance(end, dict) else None
    if isinstance(origin, str) and origin and isinstance(destination, str) and destination:
        return origin, destination
    return None


def build_sources(outputs: list[ToolOutput], referenced: set[str], language: Language) -> list[Source]:
    """성공한 도구 결과에서 답변의 근거를 만든다. 같은 (tool, id) 는 처음 한 번만, 나온 순서대로 넣는다.

    장소 검색은 답변이나 일정에 쓴 장소만, 나머지 조회 도구는 값이 있는 결과만 근거로 삼는다.
    title 은 프로필 언어(없으면 다른 언어, 그것도 없으면 ID)다. 도구를 부르지 않았으면 빈 목록이다.
    """
    places = load_places()

    def name_of(pid: str) -> str:
        return place_name(places[pid], language) if pid in places else pid

    found: dict[tuple[str, str], Source] = {}

    def add(tool_name: str, item_id: str, title: str) -> None:
        found.setdefault((tool_name, item_id), Source(tool=tool_name, id=item_id, title=title or item_id))

    for out in outputs:
        data = out.data
        if out.name == "search_places":
            for pid in place_ids_in(data):
                if pid in referenced and pid in places:
                    add("search_places", pid, name_of(pid))
        elif out.name == "get_place_info" and isinstance(data, dict) and data.get("place_id"):
            if data["place_id"] in referenced and data["place_id"] in places:
                add("get_place_info", data["place_id"], name_of(data["place_id"]))
        elif out.name == "get_weather" and isinstance(data, dict) and data.get("hourly"):
            add("get_weather", f"busan-{data.get('date', '')}", message("source_weather", language))
        elif out.name == "get_crowd" and isinstance(data, dict) and data.get("place_id"):
            add("get_crowd", data["place_id"], name_of(data["place_id"]))
        elif out.name == "get_hours" and isinstance(data, dict) and data.get("place_id"):
            if any(data.get(k) for k in ("opens", "closes", "closed_weekdays", "closed_dates", "raw_text")):
                add("get_hours", data["place_id"], name_of(data["place_id"]))
        elif out.name == "get_travel_time" and isinstance(data, dict) and data.get("from_place_id"):
            origin, destination = data["from_place_id"], data["to_place_id"]
            title = message("source_travel", language, origin=name_of(origin), destination=name_of(destination))
            add("get_travel_time", f"{origin}>{destination}", title)
        elif out.name == "get_events" and isinstance(data, dict) and data.get("events"):
            add("get_events", data.get("date", ""), message("source_events", language, date=data.get("date", "")))
        elif out.name == "get_transit_info" and isinstance(data, dict) and _transit_route(data):
            origin, destination = _transit_route(data)
            title = message("source_transit", language, origin=origin, destination=destination)
            add("get_transit_info", f"{origin}>{destination}", title)
        elif out.name == "get_restaurants" and isinstance(data, dict) and data.get("restaurants"):
            # 음식점이 하나라도 있을 때만 근거다. id 는 검색한 장소(place_id) 또는 역(station:<역 이름>)
            pid, station = data.get("place_id"), data.get("station")
            if isinstance(pid, str) and pid:
                add("get_restaurants", pid, message("source_restaurants", language, area=name_of(pid)))
            elif isinstance(station, str) and station:
                add("get_restaurants", f"station:{station}", message("source_restaurants", language, area=station))
        elif out.name == "get_return_options" and isinstance(data, dict) and _return_route(data):
            origin, destination = _return_route(data)
            title = message("source_return", language, origin=origin, destination=destination)
            add("get_return_options", f"{data.get('date', '')}:{origin}>{destination}", title)
    return list(found.values())
