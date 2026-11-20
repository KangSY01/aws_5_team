"""방문 순서 점수 (rank_orders). LLM 미사용, 순수 파이썬. 같은 입력이면 항상 같은 결과.

3~7곳이면 가능한 순서(첫 장소 고정, 최대 6! = 720가지)를 모두 만들어 채점한다.
- 하드 필터: 고정 일정(locked) 시각에 늦거나, 운영시간 밖이거나, 휴무인 순서는 뺀다.
- 점수: 총 이동 시간(적을수록) · 실외 Stop 의 비 노출(적을수록) · 고정 일정 앞 여유(많을수록, 상한 있음).
  여유가 "늦어도 무너지지 않는 일정"의 근거다.
- 혼잡은 일 단위 값이라 순서와 무관해서 순서 점수에 넣지 않는다.

시각 계산은 tools/schedule.py 의 build_plan 과 같은 규칙이다:
다음 시작 = 올림(이전 끝 + 이동 + TRANSFER_BUFFER_MIN, 10분 단위). 그래서 만든 순서에 tight_transfer 가 붙지 않는다.
"""

import datetime as dt
from itertools import permutations

from pydantic import BaseModel

from app.guardian.context import KST, CheckContext
from app.guardian.rules import check_rain
from app.guardian.thresholds import TRANSFER_BUFFER_MIN
from app.models.plan import Stop
from app.ranking import weights as w
from app.ranking.score import hard_filter


class LockedSlot(BaseModel):
    """고정 일정 하나. 이 장소는 순서와 무관하게 이 시각에 있어야 한다."""

    start: dt.datetime
    end: dt.datetime


class OrderScore(BaseModel):
    order: list[str]  # place_id 방문 순서
    score: float  # 높을수록 좋다 (weights 의 ORDER_* 참고)
    travel_min: int  # 총 이동 시간(분). 모르는 구간은 FALLBACK_TRAVEL_MIN
    rain_points: int  # 실외 Stop 의 비 심각도 합 (medium=1, high=2)
    locked_slack_min: int | None  # 고정 일정 앞 여유(분) 중 가장 작은 값. 고정 일정이 없으면 None
    stops: list[Stop]  # 이 순서로 계산한 시각 (stop_id 는 s1, s2, ...)


def rank_orders(
    place_ids: list[str],
    ctx: CheckContext,
    *,
    day: dt.date,
    start_time: dt.time,
    dwell_min: dict[str, int],
    locked: dict[str, LockedSlot] | None = None,
    limit: int | None = 3,
) -> list[OrderScore]:
    """가능한 방문 순서를 채점해 좋은 순으로 돌려준다.

    입력:
    - place_ids: 방문할 장소. 첫 장소는 출발점으로 고정한다(build_plan 과 같음). 중복은 처음 것만.
    - ctx: CheckContext. travel_min 에 장소 쌍 이동 시간, weather·hours 가 있으면 비·운영시간도 본다.
    - day, start_time: 방문일과 첫 장소 시작 시각 (한국 시각).
    - dwell_min: place_id → 체류 분. 고정 일정은 LockedSlot 의 시간을 쓴다.
    - locked: place_id → LockedSlot. 첫 장소는 고정 일정일 수 없다(출발점이라).
    - limit: 돌려줄 개수. None 이면 전부.
    출력: OrderScore 목록. 점수 높은 순, 동점은 이동 시간 → 순서(사전순).
    - 장소가 MAX_ORDER_PLACES 보다 많거나 2곳 미만이면, 또는 가능한 순서가 없으면 빈 목록.
      호출하는 쪽은 기존 방식(최근접 이웃 + 2-opt)으로 돌아간다.
    """
    ids = list(dict.fromkeys(place_ids))
    locked = locked or {}
    if not 2 <= len(ids) <= w.MAX_ORDER_PLACES or ids[0] in locked:
        return []

    first = dt.datetime.combine(day, start_time.replace(tzinfo=None), KST)
    results = []
    for rest in permutations(ids[1:]):
        order = [ids[0], *rest]
        scored = _score_order(order, ctx, day, first, dwell_min, locked)
        if scored is not None:
            results.append(scored)
    results.sort(key=lambda r: (-r.score, r.travel_min, r.order))
    return results if limit is None else results[:limit]


def _ceil_to(t: dt.datetime, minutes: int) -> dt.datetime:
    floor = t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)
    return floor if floor == t else floor + dt.timedelta(minutes=minutes)


def _travel(ctx: CheckContext, a: str, b: str) -> int:
    minutes = ctx.travel(a, b)
    return w.FALLBACK_TRAVEL_MIN if minutes is None else minutes


def _score_order(
    order: list[str],
    ctx: CheckContext,
    day: dt.date,
    first: dt.datetime,
    dwell_min: dict[str, int],
    locked: dict[str, LockedSlot],
) -> OrderScore | None:
    """순서 하나의 시각을 계산하고 채점한다. 하드 필터에 걸리면 None."""
    stops: list[Stop] = []
    travel_total = 0
    slacks: list[int] = []
    for n, place_id in enumerate(order, start=1):
        if stops:
            minutes = _travel(ctx, stops[-1].place_id, place_id)
            travel_total += minutes
            ready = stops[-1].end + dt.timedelta(minutes=minutes + TRANSFER_BUFFER_MIN)
        else:
            ready = first

        if place_id in locked:
            slot = locked[place_id]
            slack = int((slot.start - ready).total_seconds() // 60)
            if slack < 0:
                return None  # 고정 일정에 늦는다
            slacks.append(slack)
            begin, end = slot.start, slot.end
        else:
            begin = ready if not stops else _ceil_to(ready, w.ROUND_MIN)
            end = begin + dt.timedelta(minutes=dwell_min[place_id])

        if hard_filter(place_id, ctx, day, begin, end):
            return None
        stops.append(Stop(stop_id=f"s{n}", place_id=place_id, start=begin, end=end, locked=place_id in locked))

    rain = sum(w.RAIN_POINTS.get(_rain_severity(s, ctx), 0) for s in stops)
    slack_min = min(slacks) if slacks else None
    score = -w.ORDER_W_TRAVEL * travel_total - w.ORDER_W_RAIN * rain
    if slack_min is not None:
        score += w.ORDER_W_SLACK * min(slack_min, w.ORDER_SLACK_CAP_MIN)
    return OrderScore(
        order=order,
        score=round(score, 1),
        travel_min=travel_total,
        rain_points=rain,
        locked_slack_min=slack_min,
        stops=stops,
    )


def _rain_severity(stop: Stop, ctx: CheckContext) -> str | None:
    issue = check_rain(stop, ctx)  # 실내 장소·예보 없음은 None
    return issue.severity if issue else None
