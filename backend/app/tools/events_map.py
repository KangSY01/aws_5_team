"""지도 행사 레이어용 날짜 조회. Guardian의 get_events와 달리 기간 중인 행사를 모두 돌려준다."""

import datetime as dt
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from app.tools.lookup import _load_json, _parse_date

EventType = Literal["festival", "performance", "exhibition", "event"]
LANGUAGES = ("ko", "en", "ja", "zh-Hans", "zh-Hant")


class MapEvent(BaseModel):
    """GET /events의 행사 한 건."""

    contentid: str
    name: str
    names: dict[str, str]
    type: EventType
    lat: float | None
    lng: float | None
    main_place_id: str | None
    place_ids: list[str]
    start: AwareDatetime
    end: AwareDatetime
    period_start: AwareDatetime
    period_end: AwareDatetime


class EventsResponse(BaseModel):
    """GET /events 응답."""

    date: dt.date
    events: list[MapEvent]


def events_on_date(date: str) -> EventsResponse:
    """기간에 date가 포함된 모든 행사를 지도 응답 형식으로 만든다.

    events.json의 start·end는 행사 전체 기간이며 시각 부분은 하루 중 운영 시각이다. 행사 시각을 모르면
    00:00:00~23:59:59이다. Guardian의 장·단기 행사 가중 규칙은 적용하지 않는다.
    """
    day = _parse_date(date)
    found: list[MapEvent] = []
    for event in _load_json("events.json")["events"]:
        period_start = dt.datetime.fromisoformat(event["start"])
        period_end = dt.datetime.fromisoformat(event["end"])
        if not period_start.date() <= day <= period_end.date():
            continue
        names = {
            language: value
            for language in LANGUAGES
            if isinstance((value := event.get("names", {}).get(language)), str) and value.strip()
        }
        names["ko"] = event["name"]
        found.append(MapEvent(
            contentid=str(event["contentid"]),
            name=event["name"],
            names=names,
            type=event.get("type", "event"),
            lat=event.get("lat"),
            lng=event.get("lng"),
            main_place_id=event.get("main_place_id"),
            place_ids=event.get("place_ids", []),
            start=day.isoformat() + event["start"][10:],
            end=day.isoformat() + event["end"][10:],
            period_start=period_start,
            period_end=period_end,
        ))
    return EventsResponse(date=day, events=found)
