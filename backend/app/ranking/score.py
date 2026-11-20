"""장소 점수 (score_place, rank_places). LLM 미사용, 순수 파이썬. 같은 입력이면 항상 같은 결과.

흐름: 하드 필터(휴무·운영시간 밖)로 거르고 → 항목별 점수(0~1)의 가중합(0~100)을 매긴다.
LLM 에는 rank_places 상위 몇 개와 breakdown 만 넘긴다.

- 혼잡·비 판단은 Guardian 규칙(guardian/rules.py)을 그대로 쓴다. 배지와 점수가 서로 다른 말을 하지 않게 하기 위해서다.
- 집중률은 장소끼리 비교하지 않는다. 장소마다 "그날 자기 기준으로 붐비는가"(심각도)만 점수로 바꾼다.
- 식단 조건은 장소 데이터에 없어서 거르지 않는다(음식점 데이터에도 식단 정보 없음, data-rules.md).
"""

import datetime as dt
import json
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from app.guardian.context import KST, CheckContext
from app.guardian.rules import check_crowded, check_rain
from app.models.plan import Profile, Stop
from app.ranking import weights as w

_CURATION_PATH = Path(__file__).resolve().parent.parent / "data" / "curation.json"
_NOON = dt.time(12, 0)  # 체류 시간을 모를 때 혼잡 판단에 쓰는 시각. 혼잡은 일 단위라 요일만 영향이 있다


class PlaceScore(BaseModel):
    """장소 하나의 점수. excluded 가 있으면 하드 필터에 걸린 것이고 total 은 0 이다."""

    place_id: str
    total: float  # 0~100, 소수 첫째 자리
    breakdown: dict[str, float]  # 항목 → 0~1 점수 (weights.PLACE_WEIGHTS 의 키)
    notes: list[str] = []  # 점수 근거 코드. 예: "crowd:medium", "rain:high", "interest:sea", "no_data:travel"
    excluded: str | None = None  # 하드 필터 사유: "closed_day", "outside_hours", "unknown_place"


@cache
def load_curation() -> dict[str, dict]:
    """curation.json (place_id → tags·foreigner_friendly 등). 파일은 배포 묶음에 들어 있어 한 번만 읽는다."""
    return json.loads(_CURATION_PATH.read_text(encoding="utf-8"))


def score_place(
    place_id: str,
    profile: Profile,
    ctx: CheckContext,
    *,
    day: dt.date,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    prev_place_id: str | None = None,
    curation: dict[str, dict] | None = None,
) -> PlaceScore:
    """장소 하나를 채점한다.

    입력:
    - ctx: Guardian 과 같은 CheckContext. 이 장소의 집중률·운영시간과 (prev_place_id, place_id) 이동 시간이
      들어 있어야 그 항목을 채점한다. 없으면 그 항목은 NEUTRAL(0.5) 이고 notes 에 "no_data:<항목>" 이 붙는다.
    - day: 방문일. start·end: 체류 시간대(둘 다 있어야 운영시간·비를 본다).
    - prev_place_id: 바로 앞 장소. 없으면 이동 항목은 NEUTRAL.
    - curation: 테스트용. 기본은 curation.json.
    출력: PlaceScore. 하드 필터에 걸리면 excluded 사유와 total=0.
    """
    place = ctx.places.get(place_id)
    if place is None:
        return PlaceScore(place_id=place_id, total=0.0, breakdown={}, excluded="unknown_place")

    excluded = hard_filter(place_id, ctx, day, start, end)
    if excluded:
        return PlaceScore(place_id=place_id, total=0.0, breakdown={}, notes=[excluded], excluded=excluded)

    info = (curation if curation is not None else load_curation()).get(place_id, {})
    window = (start, end) if start and end else None
    stop = _probe_stop(place_id, day, window)
    notes: list[str] = []
    breakdown = {
        "interest": _interest(profile, info, notes),
        "crowd": _crowd(stop, ctx, notes),
        "travel": _travel(prev_place_id, place_id, ctx, notes),
        "weather": _weather(stop, ctx, place.indoor, window is not None, notes),
        "foreigner": _foreigner(info, notes),
        "dispersal": _dispersal(place_id, place.lng, notes),
    }
    total = sum(w.PLACE_WEIGHTS[k] * v for k, v in breakdown.items()) / sum(w.PLACE_WEIGHTS.values()) * 100
    return PlaceScore(
        place_id=place_id,
        total=round(total, 1),
        breakdown={k: round(v, 3) for k, v in breakdown.items()},
        notes=notes,
    )


def rank_places(
    place_ids: list[str],
    profile: Profile,
    ctx: CheckContext,
    *,
    day: dt.date,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    prev_place_id: str | None = None,
    limit: int | None = 5,
    curation: dict[str, dict] | None = None,
) -> list[PlaceScore]:
    """후보 장소를 채점해 높은 순으로 돌려준다. 하드 필터에 걸린 장소, 중복, prev_place_id 자신은 뺀다.

    동점은 place_id 사전순. limit=None 이면 전부.
    이미 일정에 있는 다른 장소는 빼지 않는다. 호출하는 쪽이 후보 목록에서 뺀다.
    """
    scores = [
        score_place(p, profile, ctx, day=day, start=start, end=end, prev_place_id=prev_place_id, curation=curation)
        for p in dict.fromkeys(place_ids)
        if p != prev_place_id  # 이동 0분이라 늘 1등이 된다
    ]
    ranked = sorted((s for s in scores if s.excluded is None), key=lambda s: (-s.total, s.place_id))
    return ranked if limit is None else ranked[:limit]


# ---------- 하드 필터 ----------

def hard_filter(
    place_id: str, ctx: CheckContext, day: dt.date, start: dt.datetime | None, end: dt.datetime | None
) -> str | None:
    """guardian.rules.check_closed 와 같은 기준. 영업 정보가 없으면 거르지 않는다."""
    hours = ctx.hours.get(place_id)
    if hours is None:
        return None
    if day in hours.closed_dates or day.weekday() in hours.closed_weekdays:
        return "closed_day"
    if start and end:
        if (hours.opens and start.time() < hours.opens) or (hours.closes and end.time() > hours.closes):
            return "outside_hours"
    return None


# ---------- 항목별 점수 (0~1) ----------

def _probe_stop(place_id: str, day: dt.date, window: tuple[dt.datetime, dt.datetime] | None) -> Stop:
    """Guardian 규칙에 넘길 임시 Stop. 시간대를 모르면 그날 12:00~13:00 (혼잡 판단용)."""
    if window:
        start, end = window
    else:
        start = dt.datetime.combine(day, _NOON, KST)
        end = start + dt.timedelta(hours=1)
    return Stop(stop_id="rank", place_id=place_id, start=start, end=end)


def _interest(profile: Profile, info: dict, notes: list[str]) -> float:
    interests = set(profile.interests)
    if not interests:
        return w.NEUTRAL
    matched = sorted(interests & set(info.get("tags", [])))
    notes.extend(f"interest:{t}" for t in matched)
    return len(matched) / len(interests)


def _crowd(stop: Stop, ctx: CheckContext, notes: list[str]) -> float:
    issue = check_crowded(stop, ctx)
    if issue is None:
        return w.SEVERITY_SCORE[None]
    notes.append(f"crowd:{issue.severity}")
    return w.SEVERITY_SCORE[issue.severity]


def _travel(prev_place_id: str | None, place_id: str, ctx: CheckContext, notes: list[str]) -> float:
    if prev_place_id is None:
        return w.NEUTRAL
    minutes = ctx.travel(prev_place_id, place_id)
    if minutes is None:
        notes.append("no_data:travel")
        return w.NEUTRAL
    notes.append(f"travel_min:{minutes}")
    return max(0.0, 1 - minutes / w.TRAVEL_SCORE_MAX_MIN)


def _weather(stop: Stop, ctx: CheckContext, indoor: bool, has_window: bool, notes: list[str]) -> float:
    if not has_window or ctx.weather is None:
        return w.NEUTRAL  # 시간대나 예보를 모르면 실내·실외를 구분하지 않는다
    if indoor:
        return 1.0
    issue = check_rain(stop, ctx)
    if issue is None:
        return 1.0
    notes.append(f"rain:{issue.severity}")
    return w.SEVERITY_SCORE[issue.severity]


def _foreigner(info: dict, notes: list[str]) -> float:
    value = info.get("foreigner_friendly")
    if value is None:
        notes.append("no_data:foreigner")
        return w.NEUTRAL
    return min(value, w.FOREIGNER_FRIENDLY_MAX) / w.FOREIGNER_FRIENDLY_MAX


def _dispersal(place_id: str, lng: float, notes: list[str]) -> float:
    score = 0.0
    if lng < w.DISPERSAL_MAX_LNG:
        notes.append("dispersal:west")
        score += w.DISPERSAL_WEST
    if place_id not in w.LANDMARKS and place_id not in w.LARGE_COMMERCIAL:
        notes.append("dispersal:not_landmark")
        score += w.DISPERSAL_NOT_LANDMARK
    return score
