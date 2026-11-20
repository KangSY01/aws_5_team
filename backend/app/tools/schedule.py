"""일정 생성 (도구 담당). 방문 순서와 start·end 를 코드로 계산한다. LLM 을 부르지 않는다.

근거: .kiro/specs/chat-agent/design.md 「시각 계산」「일정 시각 계산 (build_plan)」.
run_chat(A)이 LLM 이 고른 place_id 목록으로 build_plan 을 부른다. @tool 이 아닌 일반 함수다.
"""

import datetime as dt
import hashlib
import json
import logging

from app.models.plan import Plan, Profile, Stop
from app.tools.lookup import KST, LookupFailure, _load_places, get_travel_time

logger = logging.getLogger(__name__)

# category 별 기본 체류 시간(분). 기본값이며 데이터가 아니다(실제 관람 시간을 조사한 값이 아님).
DWELL_MIN = {
    "beach": 60, "market": 60, "village": 90, "observatory": 45, "temple": 60, "park": 60, "shopping": 90,
    "museum": 90, "street": 60, "aquarium": 90, "theme_park": 180, "attraction": 60, "culture": 60,
}
DEFAULT_DWELL_MIN = 60  # 표에 없는 category
DEFAULT_START = dt.time(10, 0)
FALLBACK_TRAVEL_MIN = 30  # 이동 시간 조회가 실패했을 때
ROUND_MIN = 10  # 다음 Stop 시작 시각을 이 단위로 올림
LATE_END = dt.time(22, 0)  # 이보다 늦게 끝나면 경고만 남긴다


class PlanBuildError(Exception):
    """일정을 만들 수 없는 사유. code: no_valid_places, invalid_date, invalid_start, data_unavailable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _parse(kind: type, value, code: str):
    """dt.date·dt.time 은 그대로, 문자열은 ISO 형식("2026-11-28", "10:00")으로 읽는다."""
    if isinstance(value, kind):
        return value
    try:
        return kind.fromisoformat(value)
    except (TypeError, ValueError):
        raise PlanBuildError(code, f"{code}: {value!r}") from None


def _path_minutes(order: list[str], travel) -> int:
    return sum(travel(a, b) for a, b in zip(order, order[1:]))


def _visit_order(place_ids: list[str], travel) -> list[str]:
    """첫 장소를 출발점으로 고정하고 최근접 이웃 → 2-opt 로 총 이동 시간을 줄인다. 동률은 place_id 사전순."""
    order, rest = place_ids[:1], set(place_ids[1:])
    while rest:
        nxt = min(rest, key=lambda p: (travel(order[-1], p), p))
        order.append(nxt)
        rest.remove(nxt)

    # ponytail: 뒤집을 때마다 전체 경로를 다시 더한다(O(n^3)). 하루 일정(10곳 안팎)에는 충분하다.
    # 장소가 수십 곳으로 늘면 바뀐 두 구간만 계산하도록 바꾼다.
    best = _path_minutes(order, travel)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 1):  # 0번(출발점)은 건드리지 않는다
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                minutes = _path_minutes(candidate, travel)
                if minutes < best:  # 줄어들 때만 바꾼다 → 같은 입력이면 같은 결과, 반드시 끝난다
                    order, best, improved = candidate, minutes, True
    return order


def _ceil_to(t: dt.datetime, minutes: int) -> dt.datetime:
    floor = t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)
    return floor if floor == t else floor + dt.timedelta(minutes=minutes)


def build_plan(
    place_ids: list[str],
    date: dt.date | str,
    start: dt.time | str | None,
    profile: Profile,
    plan_id: str | None = None,
) -> Plan:
    """장소 목록으로 하루 일정을 만든다. 같은 입력이면 항상 같은 Plan 이 나온다.

    - places.json 에 없는 place_id 는 빼고, 중복은 처음 것만 남긴다.
    - 방문 순서: place_ids[0] 을 출발점으로 고정, 나머지는 get_travel_time 기준 최근접 이웃 + 2-opt.
    - 체류 시간은 DWELL_MIN (category 별 기본값, 데이터 아님).
    - 첫 Stop 은 start(없으면 10:00)에 시작. 다음 Stop 시작 = 이전 end + 이동 시간을 10분 단위로 올림.
      시각은 Asia/Seoul(+09:00). 이동 시간 조회가 실패하면 30분으로 둔다.
    - Stop 구간은 겹치지 않고 각 start < end 다. 22:00 을 넘겨도 자르지 않고 경고 로그만 남긴다.

    Raises:
        PlanBuildError: 유효한 장소가 0개(code="no_valid_places"), 날짜·시작 시각 형식 오류
            (invalid_date, invalid_start), places.json 을 읽지 못함(data_unavailable).
            호출하는 쪽(run_chat)이 프로필 언어로 안내한다.
    """
    day = _parse(dt.date, date, "invalid_date")
    start_time = DEFAULT_START if start is None else _parse(dt.time, start, "invalid_start")

    try:
        category = {p["place_id"]: p["category"] for p in _load_places()}
    except LookupFailure as e:
        raise PlanBuildError(e.code, e.message) from e

    valid: list[str] = []
    for place_id in place_ids:
        if place_id not in category:
            logger.warning("일정 생성: 모르는 place_id 를 제외했습니다: %r", place_id)
        elif place_id not in valid:
            valid.append(place_id)
    if not valid:
        raise PlanBuildError("no_valid_places", "No valid place_id to build a plan from.")

    cache: dict[frozenset[str], int] = {}  # 같은 쌍을 여러 번 묻는다. 실패 경고도 쌍마다 한 번만 남긴다

    def travel(a: str, b: str) -> int:
        key = frozenset((a, b))
        if key not in cache:
            result = get_travel_time(a, b)
            if "error" in result:
                logger.warning(
                    "일정 생성: %s → %s 이동 시간을 알 수 없어 %d분으로 둡니다 (%s)",
                    a, b, FALLBACK_TRAVEL_MIN, result["error"]["code"],
                )
                cache[key] = FALLBACK_TRAVEL_MIN
            else:
                cache[key] = result["minutes"]
        return cache[key]

    order = _visit_order(valid, travel)

    stops: list[Stop] = []
    begin = dt.datetime.combine(day, start_time.replace(tzinfo=None), KST)
    for n, place_id in enumerate(order, start=1):
        if stops:
            arrive = stops[-1].end + dt.timedelta(minutes=travel(stops[-1].place_id, place_id))
            begin = _ceil_to(arrive, ROUND_MIN)
        end = begin + dt.timedelta(minutes=DWELL_MIN.get(category[place_id], DEFAULT_DWELL_MIN))
        stops.append(Stop(stop_id=f"s{n}", place_id=place_id, start=begin, end=end, locked=False))

    if stops[-1].end > dt.datetime.combine(day, LATE_END, KST):
        logger.warning("일정 생성: 마지막 일정이 22:00 이후(%s)에 끝납니다", stops[-1].end.isoformat())

    if plan_id is None:
        # 입력이 같으면 ID 도 같다. date·start 는 문자열로 주든 객체로 주든 같은 값이 되게 정규화한 뒤 해시한다.
        raw = json.dumps([list(place_ids), day.isoformat(), start_time.isoformat()], ensure_ascii=False)
        plan_id = "plan-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]

    return Plan(plan_id=plan_id, date=day, profile=profile, stops=stops)
