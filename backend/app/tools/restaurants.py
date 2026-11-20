"""주변 음식점 도구 (도구 담당). .kiro/specs/info-tools/ 를 따른다.

한국관광공사 TourAPI 음식점 정보를 scripts/fetch_restaurants.py 로 미리 받아 둔 app/data/restaurants.json 만 읽는다.
외부 API 와 LLM 을 쓰지 않는다 (USE_MOCK·FAKE_LLM 과 무관).

- 수집해 둔 기준(Anchor) 장소와 역 주변만 답할 수 있다. 그 밖의 장소는 restaurants_not_collected 다.
- 식단(할랄·채식·알레르기), 영업시간, 휴무, 가격, 평점, 순위는 데이터에 없고 만들지도 않는다.
  파일 모델이 모르는 필드를 막는다(extra="forbid").
- restaurant_id("kto-<국문 contentid>")는 places.json 의 place_id 가 아니다. 장소 ID 로 쓰지 않는다.
- 거리는 직선거리, 도보 분은 return_options.walk_minutes 와 같은 추정이다 (길·경사는 반영하지 않는다).
"""

import functools
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from strands import tool

from app.tools import lookup
from app.tools.lookup import LookupFailure, _load_places, _safe
from app.tools.return_options import find_station, station_table, straight_km, travel_rule, walk_minutes

DEFAULT_RADIUS_M, MAX_RADIUS_M = 500, 1000  # 실제 상한은 수집 반경(파일의 radius_m)과 MAX_RADIUS_M 중 작은 값
DEFAULT_LIMIT, MAX_LIMIT = 10, 20
SOURCE = "한국관광공사 TourAPI 음식점 정보 (공공데이터포털)"
NOTE = (
    "Opening hours, closed days, prices, menus and dietary options (halal, vegetarian, allergens) are not included. "
    "Ask the restaurant."
)

Cuisine = Literal["korean", "western", "japanese", "chinese", "cafe", "other"]
NameLang = Literal["en", "ja", "zh-Hans", "zh-Hant"]


class RestaurantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 식단 같은 모르는 필드가 파일에 들어오지 못하게 한다

    restaurant_id: str  # "kto-" + 국문 contentid. place_id 가 아니다
    name_ko: str
    names: dict[NameLang, str] = {}  # 찾은 언어만
    lat: float
    lng: float
    address_ko: str
    cuisine: Cuisine | None  # 국문 분류 코드로 정한 값. 표에 없는 코드는 null
    kor_class: dict[str, str | None]  # 국문 분류 코드 원본
    menu_raw: str | None = None  # 국문 대표 메뉴 원문. 받지 않은 곳은 null


class RestaurantTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str
    collected_at: str
    radius_m: int  # 수집 반경. 이보다 넓은 반경은 답할 수 없다
    anchors: dict[str, list[str]]  # place_id → 그 장소 반경 안의 restaurant_id
    station_anchors: dict[str, list[str]] = {}  # 역 이름(stations.json) → 그 역 반경 안의 restaurant_id
    restaurants: list[RestaurantRecord]

    @model_validator(mode="after")
    def _ids_are_consistent(self) -> "RestaurantTable":
        ids = [r.restaurant_id for r in self.restaurants]
        if len(ids) != len(set(ids)):
            raise ValueError("restaurant_id 가 중복된다")
        listed = {rid for group in (self.anchors, self.station_anchors) for rids in group.values() for rid in rids}
        if not listed <= set(ids):
            raise ValueError("anchors 에 restaurants 에 없는 restaurant_id 가 있다")
        return self


def dump_restaurants(table: RestaurantTable) -> str:
    """restaurants.json 본문. restaurant_id 오름차순, 음식점 하나를 한 줄로 쓴다. 같은 입력이면 바이트까지 같다."""
    data = table.model_dump(mode="json")
    rows = sorted(data.pop("restaurants"), key=lambda r: r["restaurant_id"])
    for key in ("anchors", "station_anchors"):
        data[key] = {name: sorted(ids) for name, ids in sorted(data[key].items())}
    body = ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in rows)
    listing = f'  "restaurants": [\n{body}\n  ]\n' if rows else '  "restaurants": []\n'
    return json.dumps(data, ensure_ascii=False, indent=2)[:-2] + ",\n" + listing + "}\n"


@functools.lru_cache(maxsize=4)
def _table(path: Path) -> RestaurantTable:
    """restaurants.json 을 모델로 검증해 읽는다. 요청마다 다시 읽지 않게 한 번만 읽는다 (경로가 다르면 따로)."""
    try:
        return RestaurantTable.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # pydantic ValidationError 는 ValueError 다
        raise LookupFailure("data_unavailable", f"{path.name} could not be read.") from e


def restaurants_near(place_id: str | None = None, station: str | None = None,
                     radius_m: int = DEFAULT_RADIUS_M, limit: int = DEFAULT_LIMIT) -> dict:
    """get_restaurants 의 계산. 실패는 LookupFailure 로 알린다 (도구가 오류 dict 로 바꾼다)."""
    if not place_id and not station:
        raise LookupFailure("missing_argument", "Pass place_id or station.")
    for name, value, top in (("radius_m", radius_m, MAX_RADIUS_M), ("limit", limit, MAX_LIMIT)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
            raise LookupFailure("invalid_argument", f"{name} must be an integer from 1 to {top}.")
    if place_id:  # 둘 다 주면 place_id 가 우선이다
        origin = next((p for p in _load_places() if p["place_id"] == place_id), None)
        if origin is None:
            raise LookupFailure("place_not_found", f"place_id {place_id!r} is not a known place.")
        station_name = None
    else:
        stations = station_table()
        station_name = find_station(stations, station)
        if station_name is None:
            raise LookupFailure(
                "station_not_found",
                f"station {station!r} is not in the station table. Use the English name of a Busan Metro station.",
            )
        origin = stations[station_name]
    table = _table(lookup.DATA_DIR / "restaurants.json")
    collected = table.anchors if place_id else table.station_anchors
    if (place_id or station_name) not in collected:
        available = ", ".join([*table.anchors, *(f"station {name}" for name in table.station_anchors)])
        raise LookupFailure(
            "restaurants_not_collected",
            f"Restaurants were not collected around this {'place' if place_id else 'station'}. Available: {available}.",
        )
    if radius_m > table.radius_m:
        raise LookupFailure(
            "invalid_argument",
            f"radius_m must be an integer from 1 to {table.radius_m} (restaurants were collected within {table.radius_m} m).",
        )

    rule = travel_rule()
    found = []
    for record in table.restaurants:
        here = {"lat": record.lat, "lng": record.lng}
        meters = straight_km(origin, here) * 1000
        if meters <= radius_m:  # 반올림하기 전 거리로 판단한다 (경계 값이 반올림 때문에 들어오거나 빠지지 않게)
            found.append({
                **record.model_dump(exclude={"kor_class"}),
                "distance_m": round(meters),
                "walk_min": walk_minutes(origin, here, rule),
            })
    found.sort(key=lambda r: (r["distance_m"], r["restaurant_id"]))
    return {
        "place_id": place_id or None,
        "station": station_name,
        "radius_m": radius_m,
        "total_in_radius": len(found),
        "restaurants": found[:limit],
        "basis": {
            "kind": "collected_public_data",
            "source": SOURCE,
            "collected_at": table.collected_at,
            "distance": "straight_line_estimate",
            "diet_info": "not_available",
            "note": NOTE,
        },
    }


@tool
@_safe
def get_restaurants(place_id: str | None = None, station: str | None = None,
                    radius_m: int = DEFAULT_RADIUS_M, limit: int = DEFAULT_LIMIT) -> dict:
    """Find restaurants near a place or a metro station, nearest first. Use it when the user asks where to eat
    near a place in the plan or near a station. Pass place_id or station (place_id wins if both are given).

    The list is public data (Korea Tourism Organization TourAPI) collected in advance, only around a few places and
    stations; other places return restaurants_not_collected. It is not a ranking: there are no ratings, popularity,
    prices, opening hours or closed days, so never state them. There is no dietary information either (halal,
    vegetarian, vegan, allergens, gluten): never say a restaurant is suitable for a diet, and tell the user to ask
    the restaurant. menu_raw is the Korean original text of the main menu when known; do not infer dietary
    suitability from it. Distances are straight-line and walk_min is an estimate: say "about N minutes".
    restaurant_id is not a place_id and cannot be added to a plan.

    Args:
        place_id: Place to search around (a place_id from search_places).
        station: English name of a Busan Metro station to search around, for example "Seomyeon". Case and
            surrounding spaces are ignored. Use it when the area has no place_id.
        radius_m: Search radius in meters, 1 to 500 (the collected radius). Default 500.
        limit: Maximum number of restaurants to return, 1 to 20. Default 10.

    Returns:
        {"place_id": the place searched around or null, "station": the station searched around or null,
        "radius_m", "total_in_radius": number of restaurants in the radius before limit,
        "restaurants": [{"restaurant_id", "name_ko": Korean name, "names": {"en", "ja", "zh-Hans", "zh-Hant"} only
            the languages that exist (use name_ko when the user's language is missing), "lat", "lng",
            "address_ko": Korean address, "cuisine": "korean" | "western" | "japanese" | "chinese" | "cafe" |
            "other" | null, "menu_raw": Korean text or null, "distance_m": straight-line meters,
            "walk_min": estimated walking minutes}],
        "basis": {"kind", "source", "collected_at", "distance": "straight_line_estimate",
            "diet_info": "not_available", "note"}}.
        restaurants is an empty list when nothing is in the radius.
        On failure returns {"error": {"code", "message"}}: missing_argument, invalid_argument (radius_m or limit out
        of range), place_not_found, station_not_found, restaurants_not_collected, data_unavailable.
    """
    return restaurants_near(place_id, station, radius_m, limit)
