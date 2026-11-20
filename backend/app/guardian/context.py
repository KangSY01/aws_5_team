"""Guardian 점검에 쓰는 외부 정보 묶음(CheckContext)과 그 조립(build_context).

check_plan·propose_repairs 는 boto3·HTTP 를 직접 부르지 않고 이 모델로 데이터를 받는다.
모델은 guardian/ 안에 두므로 공용 모델(app/models/)을 바꾸지 않는다.

조회 도구(app/tools/lookup.py)는 build_context·with_repair_travel 에서만 부른다.
도구 반환 형식(11/20 결정)은 .kiro/specs/chat-agent/design.md 「조회 도구 반환 형식」에 있다. 필드 이름은 이 파일의 모델과 같다.
"""

import datetime as dt
import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError

from app import config
from app.guardian import thresholds as th
from app.models.plan import Place, Plan

logger = logging.getLogger(__name__)

KST = dt.timezone(dt.timedelta(hours=9))
_DATA = Path(__file__).resolve().parent.parent / "data"
WEATHER_PRESET_DIR = _DATA / "weather"
_PRESET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class HourlyWeather(BaseModel):
    """한 시간 단위 예보 (기상청 단기예보 기준)."""

    time: AwareDatetime  # 예보 시각 (정시)
    pop: int = Field(ge=0, le=100)  # 강수확률(%)
    pty: int = 0  # 기상청 강수 형태 코드. 0=없음, 1=비, 2=비/눈, 3=눈, 4=소나기

    @property
    def has_precipitation(self) -> bool:
        return self.pty != 0


class OpeningHours(BaseModel):
    """장소 하나의 운영시간과 휴무일. 모르는 값은 None 이나 빈 목록으로 둔다."""

    opens: dt.time | None = None
    closes: dt.time | None = None
    closed_weekdays: list[int] = []  # datetime.weekday() 값. 0=월 ... 6=일
    closed_dates: list[dt.date] = []


class Event(BaseModel):
    """방문일의 대형 행사. 행사 가중 규칙에 쓴다."""

    name: str
    start: AwareDatetime
    end: AwareDatetime
    place_ids: list[str] = []  # 행사 장소와 그 근처로 보는 장소 ID (places.json 값)


class CheckContext(BaseModel):
    """check_plan·propose_repairs 에 넘기는 외부 정보.

    값이 없으면(None, 빈 dict) 그 값을 쓰는 규칙만 건너뛴다. 점검 전체를 실패시키지 않는다.
    """

    now: AwareDatetime  # 점검 기준 시각 (DEMO_NOW 또는 현재 시각)
    places: dict[str, Place]  # place_id → Place (places.json)
    weather: list[HourlyWeather] | None = None  # None 이면 예보 없음 → rain 규칙 건너뜀
    crowd: dict[str, float] = {}  # place_id → 방문일 집중률 (그 장소 안에서의 상대값)
    hours: dict[str, OpeningHours] = {}  # place_id → 운영 정보. 없으면 closed 규칙 건너뜀
    travel_min: dict[tuple[str, str], int] = {}  # (출발 place_id, 도착 place_id) → 이동 시간(분)
    events: list[Event] = []

    def travel(self, from_id: str, to_id: str) -> int | None:
        """두 장소 사이 이동 시간(분). 한쪽 방향만 있으면 그 값을 쓴다. 모르면 None."""
        if from_id == to_id:
            return 0
        return self.travel_min.get((from_id, to_id), self.travel_min.get((to_id, from_id)))


# ---------- 조립 (스펙 작업 8) ----------

class WeatherPresetNotFound(ValueError):
    """demo.weather_preset 이름에 맞는 샘플 예보가 없다. API 는 422 validation_error 로 답한다."""


def load_places() -> dict[str, Place]:
    """places.json 의 장소 (place_id → Place). 장소 ID 는 이 값만 쓴다."""
    places = TypeAdapter(list[Place]).validate_json((_DATA / "places.json").read_text(encoding="utf-8"))
    return {p.place_id: p for p in places}


PLACES = load_places()


def resolve_now(demo_now: dt.datetime | None = None) -> dt.datetime:
    """점검 기준 시각. 요청의 demo.now → 환경 변수 DEMO_NOW → 현재 시각(KST) 순으로 정한다.

    DEMO_NOW 에 시간대가 없으면 한국 시각으로 본다.
    """
    if demo_now is not None:
        return demo_now
    if config.DEMO_NOW:
        value = dt.datetime.fromisoformat(config.DEMO_NOW)
        return value if value.tzinfo else value.replace(tzinfo=KST)
    return dt.datetime.now(KST)


def load_weather_preset(name: str, preset_dir: Path | None = None) -> list[HourlyWeather] | None:
    """backend/app/data/weather/{name}.json 샘플 예보 (get_weather 와 같은 형식). 없으면 WeatherPresetNotFound."""
    path = (preset_dir or WEATHER_PRESET_DIR) / f"{name}.json"
    if not _PRESET_NAME.match(name) or not path.is_file():
        raise WeatherPresetNotFound(f"weather_preset '{name}' 샘플 예보가 없습니다.")
    return _weather_from(json.loads(path.read_text(encoding="utf-8")))


def build_context(
    plan: Plan,
    demo_now: dt.datetime | None = None,
    weather_preset: str | None = None,
    lookups: ModuleType | Any | None = None,
) -> CheckContext:
    """일정 점검에 필요한 외부 정보를 조회 도구로 모아 CheckContext 를 만든다.

    입력:
    - plan: 점검할 일정 (방문일은 plan.date)
    - demo_now, weather_preset: 요청의 데모 스위치 (DemoOverride). weather_preset 이 있으면 get_weather 대신 샘플 예보
    - lookups: 조회 도구 묶음. 기본은 app.tools.lookup. 테스트는 같은 이름의 함수를 가진 객체를 넘긴다
    출력: CheckContext
    - 도구가 없거나, 아직 구현되지 않았거나, {"error": ...} 를 돌려주거나, 예외를 던지면 그 값만 비워 둔다.
      비어 있는 값을 쓰는 규칙만 건너뛰고 점검은 계속한다 (요구사항 6.4).
    - 집중률·운영시간·이동 시간은 일정에 있는 장소만 조회한다. 교체 후보까지는 with_repair_travel 로 넓힌다.
    - 카카오 경로 결과는 이 요청의 context 에만 두고 저장하지 않는다 (data-rules.md).
    """
    tools = lookups if lookups is not None else _default_lookups()
    date = plan.date.isoformat()
    place_ids = list(dict.fromkeys(s.place_id for s in plan.stops))

    if weather_preset:
        weather = load_weather_preset(weather_preset)
    else:
        weather = _weather_from(_call(tools, "get_weather", date))

    crowd, hours = _place_data(tools, place_ids, date)

    events = [
        e for e in (_model(Event, item) for item in (_call(tools, "get_events", date) or {}).get("events", []))
        if e is not None
    ]
    ctx = CheckContext(
        now=resolve_now(demo_now),
        places=PLACES,
        weather=weather,
        crowd=crowd,
        hours=hours,
        travel_min={},
        events=events,
    )
    pairs = {(a, b) for i, a in enumerate(place_ids) for b in place_ids[i + 1:]}
    return _with_travel(ctx, pairs, tools)


def with_repair_travel(
    ctx: CheckContext, plan: Plan, stop_ids: Iterable[str], lookups: ModuleType | Any | None = None
) -> CheckContext:
    """해결안 탐색에 필요한 조회 값을 더한 context. 문제가 있는 비고정 Stop 만 넘겨 조회 수를 줄인다.

    교체 후보(같은 category, 실내 장소, 시장·거리)마다
    - 그 Stop 의 앞뒤 Stop 과의 이동 시간
    - 방문일 집중률과 운영시간. 없으면 후보가 "데이터 없음"으로 보여 붐비거나 휴무인 장소가 대안에 나온다
    을 조회한다. 시장·거리는 도보권 상권 후보 판정용으로 그 Stop 장소와의 이동 시간도 조회한다.
    """
    tools = lookups if lookups is not None else _default_lookups()
    stops = sorted(plan.stops, key=lambda s: s.start)
    wanted = set(stop_ids)
    pairs: set[tuple[str, str]] = set()
    candidates: set[str] = set()
    for i, stop in enumerate(stops):
        current = ctx.places.get(stop.place_id)
        if stop.stop_id not in wanted or stop.locked or current is None:
            continue
        neighbors = [stops[j].place_id for j in (i - 1, i + 1) if 0 <= j < len(stops)]
        for place in ctx.places.values():
            local = place.category in th.LOCAL_COMMERCE_CATEGORIES
            if place.category == current.category or place.indoor or local:
                candidates.add(place.place_id)
                pairs.update((n, place.place_id) for n in neighbors if n != place.place_id)
            if local and place.place_id != current.place_id:
                pairs.add((current.place_id, place.place_id))

    # 일정에 있는 장소는 build_context 가 이미 조회했다
    new = sorted(candidates - {s.place_id for s in plan.stops})
    crowd, hours = _place_data(tools, new, plan.date.isoformat())
    ctx = ctx.model_copy(update={"crowd": ctx.crowd | crowd, "hours": ctx.hours | hours})
    return _with_travel(ctx, pairs, tools)


def _place_data(tools: Any, place_ids: Iterable[str], date: str) -> tuple[dict[str, float], dict[str, OpeningHours]]:
    """장소별 방문일 집중률과 운영시간. 값이 없거나 조회에 실패한 장소는 넣지 않는다."""
    crowd: dict[str, float] = {}
    hours: dict[str, OpeningHours] = {}
    for place_id in place_ids:
        ratio = (_call(tools, "get_crowd", place_id, date) or {}).get("ratio")
        if ratio is not None:  # ratio null 은 요일 규칙 대상이라 넣지 않는다
            crowd[place_id] = float(ratio)
        opening = _model(OpeningHours, _call(tools, "get_hours", place_id))
        if opening is not None:
            hours[place_id] = opening
    return crowd, hours


def _with_travel(ctx: CheckContext, pairs: set[tuple[str, str]], tools: Any) -> CheckContext:
    travel = dict(ctx.travel_min)
    for a, b in sorted(pairs):
        if a == b or (a, b) in travel or (b, a) in travel:
            continue  # 이미 알거나 같은 장소. 양방향은 같은 값으로 본다 (CheckContext.travel)
        minutes = (_call(tools, "get_travel_time", a, b) or {}).get("minutes")
        if isinstance(minutes, int) and minutes >= 0:
            travel[(a, b)] = minutes
    return ctx.model_copy(update={"travel_min": travel})


def _default_lookups() -> ModuleType:
    from app.tools import lookup  # strands 를 불러오므로 필요할 때만 import 한다

    return lookup


def _call(tools: Any, name: str, *args) -> dict | None:
    """조회 도구 하나를 부른다. 없거나 실패하면 None (그 값을 쓰는 규칙만 건너뛴다)."""
    func = getattr(tools, name, None)
    if func is None:
        return None
    try:
        result = func(*args)
    except Exception as e:  # 미구현(NotImplementedError)·외부 API 오류 모두 점검 전체를 멈추지 않는다
        logger.warning("조회 도구 %s 실패, 건너뜀: %s", name, type(e).__name__)
        return None
    if not isinstance(result, dict) or "error" in result:
        logger.warning("조회 도구 %s 결과 없음, 건너뜀", name)
        return None
    return result


def _model[T: BaseModel](model: type[T], data: dict | None) -> T | None:
    if data is None:
        return None
    try:
        return model.model_validate(data)
    except ValidationError:
        logger.warning("%s 형식이 맞지 않아 건너뜀", model.__name__)
        return None


def _weather_from(data: dict | None) -> list[HourlyWeather] | None:
    """get_weather 형식 → 시간대별 예보. hourly 가 비어 있으면(예보 없는 날짜) None 이라 rain 규칙을 건너뛴다."""
    if not data or not data.get("hourly"):
        return None
    try:
        return TypeAdapter(list[HourlyWeather]).validate_python(data["hourly"])
    except ValidationError:
        logger.warning("예보 형식이 맞지 않아 건너뜀")
        return None
