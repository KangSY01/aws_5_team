"""일정 생성 (도구 담당). 방문 순서와 start·end 를 코드로 계산한다. LLM 을 부르지 않는다.

근거: .kiro/specs/chat-agent/design.md 「시각 계산」「일정 시각 계산 (build_plan)」.
run_chat(A)이 LLM 이 고른 place_id 목록으로 build_plan 을 부른다. @tool 이 아닌 일반 함수다.
방문 순서는 랭킹 엔진(app/ranking/orders.py 의 rank_orders)이 고르고, 시각은 이 파일이 계산한다.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import logging
import uuid

from pydantic import ValidationError

from app.guardian.context import PLACES, CheckContext, HourlyWeather, OpeningHours, resolve_now
from app.guardian.thresholds import TRANSFER_BUFFER_MIN  # Guardian 의 "빠듯한 이동" 기준. 그쪽이 바뀌면 같이 맞춰진다
from app.models.plan import Plan, Profile, Stop
from app.ranking.orders import rank_orders
from app import config
from app.tools.lookup import KST, LookupFailure, _load_places, get_hours, get_travel_time, get_weather

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


def _known_travel(place_ids: list[str]) -> dict[tuple[str, str], int]:
    """장소 쌍마다 get_travel_time 을 한 번 부른다. 실패한 쌍은 넣지 않고 경고를 남긴다(그 구간은 30분으로 본다)."""
    known: dict[tuple[str, str], int] = {}
    for i, a in enumerate(place_ids):
        for b in place_ids[i + 1:]:
            result = get_travel_time(a, b)
            if "error" in result:
                logger.warning(
                    "일정 생성: %s → %s 이동 시간을 알 수 없어 %d분으로 둡니다 (%s)",
                    a, b, FALLBACK_TRAVEL_MIN, result["error"]["code"],
                )
            else:
                known[(a, b)] = result["minutes"]
    return known


def _known_hours(place_ids: list[str]) -> dict[str, OpeningHours]:
    """장소마다 get_hours. 실패한 장소는 넣지 않는다(rank_orders 가 그 장소를 운영시간으로 거르지 않는다)."""
    hours: dict[str, OpeningHours] = {}
    for place_id in place_ids:
        result = get_hours(place_id)
        if "error" in result:
            logger.warning("일정 생성: %s 운영시간을 알 수 없어 순서를 정할 때 보지 않습니다 (%s)", place_id, result["error"]["code"])
            continue
        try:
            hours[place_id] = OpeningHours.model_validate(result)
        except ValidationError:
            logger.warning("일정 생성: %s 운영시간 형식이 맞지 않아 순서를 정할 때 보지 않습니다", place_id)
    return hours


def _forecast(day: dt.date) -> list[HourlyWeather] | None:
    """get_weather(date) 의 시간별 예보. 오류이거나 예보가 없으면(약 3일 이후) None 이라 rank_orders 가 비를 보지 않는다."""
    result = get_weather(day.isoformat())
    if "error" in result:
        logger.warning("일정 생성: 예보를 가져오지 못해 순서를 정할 때 비를 보지 않습니다 (%s)", result["error"]["code"])
        return None
    try:
        return [HourlyWeather.model_validate(slot) for slot in result["hourly"]] or None
    except ValidationError:
        logger.warning("일정 생성: 예보 형식이 맞지 않아 순서를 정할 때 비를 보지 않습니다")
        return None


def _order_context(place_ids: list[str], day: dt.date) -> CheckContext:
    """rank_orders 에 넘길 CheckContext. 조회에 실패한 값은 넣지 않아 그 값을 쓰는 채점만 건너뛴다."""
    return CheckContext(
        now=resolve_now(),  # DEMO_NOW 또는 현재 시각(KST)
        places=PLACES,  # places.json
        travel_min=_known_travel(place_ids),
        hours=_known_hours(place_ids),
        weather=_forecast(day),
    )


def _ceil_to(t: dt.datetime, minutes: int) -> dt.datetime:
    floor = t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)
    return floor if floor == t else floor + dt.timedelta(minutes=minutes)


def _realtime_legs(order: list[str], travel) -> dict[tuple[str, str], int]:
    """정해진 방문 순서의 인접 구간 이동 분. USE_MOCK=0 이면 실시간 경로(도보 OSM·대중교통 카카오, app/tools/route_path.py)를
    구간마다 동시에 조회해 max(실시간, 추정)을 쓴다. Guardian 은 추정값으로 이동 여유를 보므로, 더 짧은 실시간 값을 쓰면
    방금 만든 일정에 tight_transfer 가 붙는다. 조회에 실패한 구간과 USE_MOCK=1 은 추정값 그대로다 (결과를 저장하지 않는다).
    """
    pairs = list(zip(order, order[1:]))
    legs = {pair: travel(*pair) for pair in pairs}
    if config.USE_MOCK or not pairs:
        return legs
    try:
        coords = {p["place_id"]: (p["lat"], p["lng"]) for p in _load_places()}
    except LookupFailure:
        return legs
    from app.tools import route_path  # 테스트·목 경로에서는 불러오지 않는다

    with ThreadPoolExecutor(max_workers=min(6, len(pairs))) as pool:
        live = list(pool.map(lambda pair: route_path.realtime_minutes(coords[pair[0]], coords[pair[1]]), pairs))
    for pair, minutes in zip(pairs, live):
        if minutes is not None:
            legs[pair] = max(legs[pair], minutes)
    logger.info("일정 생성: 인접 구간 %d개 중 %d개를 실시간 이동 시간으로 계산", len(pairs), sum(m is not None for m in live))
    return legs


def build_plan(
    place_ids: list[str],
    date: dt.date | str,
    start: dt.time | str | None,
    profile: Profile,
    plan_id: str | None = None,
) -> Plan:
    """장소 목록으로 하루 일정을 만든다. 같은 입력·같은 조회 결과면 항상 같은 stops(방문 순서·시각)가 나온다.

    plan_id: run_chat 은 저장소가 발급한 plan_id 를 넘길 것. 넘기지 않으면 저장소와 같은 형식의 무작위 ID
    (plan-<uuid4 hex>)를 새로 만든다. 입력으로 계산한 ID 는 남이 추측할 수 있어서 쓰지 않는다.

    - places.json 에 없는 place_id 는 빼고, 중복은 처음 것만 남긴다.
    - 방문 순서: place_ids[0] 을 출발점으로 고정하고, rank_orders(app/ranking/orders.py)가 고른 1위 순서를 쓴다.
      나머지 장소의 가능한 순서를 모두 채점한다. 총 이동 시간이 짧을수록, 실외 Stop 이 비 오는 시간대에 덜 걸릴수록
      점수가 높고, 운영시간 밖이거나 휴무인 Stop 이 생기는 순서는 뺀다. 채점에 쓰는 CheckContext 는 이동 시간
      (장소 쌍마다 get_travel_time), 운영시간(get_hours), 예보(get_weather(date))로 만든다. 조회에 실패한 값은 넣지 않아
      그 항목만 보지 않는다.
    - rank_orders 가 빈 목록이면 예전 방식(get_travel_time 기준 최근접 이웃 + 2-opt)으로 정하고 로그를 한 줄 남긴다.
      장소가 1곳이거나 MAX_ORDER_PLACES(app/ranking/weights.py)보다 많을 때, 모든 순서가 운영시간 밖이거나 휴무일 때다
      (예: 그날 쉬는 장소가 있거나, 첫 장소가 시작 시각에 문을 열지 않았을 때).
    - USE_MOCK=0 이면 get_weather 가 날씨 캐시(DynamoDB)와 기상청을 부를 수 있다. 예보는 방문일 약 3일 전부터 생기므로
      같은 입력이라도 부르는 때에 따라 순서가 달라질 수 있다. USE_MOCK=1 은 app/data/ 의 파일만 읽는다.
    - 체류 시간은 DWELL_MIN (category 별 기본값, 데이터 아님). rank_orders 채점에도 같은 값을 넘긴다.
    - 첫 Stop 은 start(없으면 10:00)에 시작. 다음 Stop 시작 = 이전 end + 이동 시간 + 이동 여유(TRANSFER_BUFFER_MIN,
      Guardian 기준값)를 10분 단위로 올림. 그래서 이동 여유(다음 start - 이전 end - 이동 시간)는 항상
      TRANSFER_BUFFER_MIN 이상이고, 만든 일정에 Guardian 의 tight_transfer 가 붙지 않는다.
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

    ctx = _order_context(valid, day)  # 이동 시간은 여기서 쌍마다 한 번만 조회하고, 실패 경고도 쌍마다 한 번 남긴다

    def travel(a: str, b: str) -> int:
        minutes = ctx.travel(a, b)
        return FALLBACK_TRAVEL_MIN if minutes is None else minutes  # rank_orders 도 모르는 구간을 같은 값으로 본다

    dwell_min = {place_id: DWELL_MIN.get(category[place_id], DEFAULT_DWELL_MIN) for place_id in valid}
    ranked = rank_orders(valid, ctx, day=day, start_time=start_time, dwell_min=dwell_min, limit=1)
    if ranked:
        order = ranked[0].order
    else:
        logger.info(
            "일정 생성: 순서 점수 결과가 없어 기존 방식(최근접 이웃 + 2-opt)으로 방문 순서를 정합니다 (장소 %d곳)",
            len(valid),
        )
        order = _visit_order(valid, travel)

    leg_minutes = _realtime_legs(order, travel)

    stops: list[Stop] = []
    begin = dt.datetime.combine(day, start_time.replace(tzinfo=None), KST)
    for n, place_id in enumerate(order, start=1):
        if stops:
            # 도착한 뒤 이동 여유까지 지난 시각. 여유가 이 값보다 작으면 Guardian 이 tight_transfer 를 붙인다
            ready = stops[-1].end + dt.timedelta(minutes=leg_minutes[(stops[-1].place_id, place_id)] + TRANSFER_BUFFER_MIN)
            begin = _ceil_to(ready, ROUND_MIN)
        end = begin + dt.timedelta(minutes=DWELL_MIN.get(category[place_id], DEFAULT_DWELL_MIN))
        stops.append(Stop(stop_id=f"s{n}", place_id=place_id, start=begin, end=end, locked=False))

    if stops[-1].end > dt.datetime.combine(day, LATE_END, KST):
        logger.warning("일정 생성: 마지막 일정이 22:00 이후(%s)에 끝납니다", stops[-1].end.isoformat())

    if plan_id is None:
        plan_id = f"plan-{uuid.uuid4().hex}"  # app/storage/service.py 의 new_plan_id 와 같은 형식

    return Plan(plan_id=plan_id, date=day, profile=profile, stops=stops)
