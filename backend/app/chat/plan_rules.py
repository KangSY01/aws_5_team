"""일정 검증과 장소 이름 조회. LLM 을 부르지 않는다.

장소 정보의 출처는 places.json 하나다 (tools/plan_edit.py, handler.py 와 같은 파일).
"""

import json
from functools import lru_cache
from pathlib import Path

from app.models.plan import Language, Place, Plan

_PLACES_PATH = Path(__file__).parent.parent / "data" / "places.json"
_FALLBACK_ORDER: tuple[Language, ...] = ("en", "ja", "zh-Hans", "zh-Hant")


@lru_cache(maxsize=1)
def load_places() -> dict[str, Place]:
    """places.json 의 장소를 place_id 로 찾을 수 있게 읽는다. 컨테이너당 한 번만 읽는다."""
    return {p["place_id"]: Place.model_validate(p) for p in json.loads(_PLACES_PATH.read_text(encoding="utf-8"))}


def place_name(place: Place, language: Language) -> str:
    """프로필 언어 이름. 없거나 비어 있으면 다른 언어 이름, 그것도 없으면 place_id (요구사항 1.4)."""
    for key in (language, *_FALLBACK_ORDER):
        if place.names.get(key):
            return place.names[key]
    return place.place_id


def validate_plan(plan: Plan, original: Plan | None = None) -> list[str]:
    """일정의 문제 코드 목록. 비어 있으면 저장해도 된다.

    duplicate_stop_id, bad_time_range(start >= end), overlap(Stop 구간이 겹침), unknown_place(places.json 에 없음),
    locked_changed(original 에서 locked 인 Stop 의 place_id·start·end 가 바뀌었거나 없어짐).
    앞 Stop 이 끝나는 시각에 다음 Stop 이 시작하는 것은 겹침이 아니다.
    """
    problems: list[str] = []
    ids = [s.stop_id for s in plan.stops]
    if len(set(ids)) != len(ids):
        problems.append("duplicate_stop_id")
    if any(s.start >= s.end for s in plan.stops):
        problems.append("bad_time_range")
    ordered = sorted(plan.stops, key=lambda s: s.start)
    if any(prev.end > nxt.start for prev, nxt in zip(ordered, ordered[1:])):
        problems.append("overlap")
    if any(s.place_id not in load_places() for s in plan.stops):
        problems.append("unknown_place")
    if original is not None:
        now = {s.stop_id: s for s in plan.stops}
        for old in original.stops:
            new = now.get(old.stop_id)
            if old.locked and (new is None or (new.place_id, new.start, new.end) != (old.place_id, old.start, old.end)):
                problems.append("locked_changed")
                break
    return problems
