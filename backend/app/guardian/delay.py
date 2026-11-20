"""지연 재조정 ("늦었어요", 요구사항 7). LLM 을 쓰지 않는 순수 파이썬.

규칙은 .kiro/specs/schedule-guardian/design.md 「지연 재조정」을 따른다.
locked=true 인 Stop 의 place_id·start·end 는 어떤 해결안에서도 바꾸지 않는다.
"""

import datetime as dt
from collections.abc import Iterator

from app.guardian import thresholds as th
from app.guardian.context import CheckContext
from app.guardian.metrics import total_travel_min
from app.guardian.repair import _keeps_locked, _option, _ordered, _recheck, _required_gap
from app.models.plan import Plan, RepairAction, RepairOption, Stop

_STAGES: dict[RepairAction, int] = {"move_time": 0, "reorder": 1, "replace": 2, "remove": 3}


def propose_delay_repairs(plan: Plan, delay_min: int, context: CheckContext | dict) -> list[RepairOption]:
    """일정이 delay_min 분 늦어졌을 때, 기준 시각(ctx.now) 이후의 비고정 Stop 만 고친 해결안 목록.

    입력: plan, 늦어진 시간(분, DelayRequest 에서 1~240 으로 검증됨), check_plan 과 같은 context
    출력: RepairOption 목록 (최대 MAX_REPAIRS 개). 고칠 Stop 이 없으면 [].
      - move_time: 남은 비고정 Stop 을 미루고, 고정 일정 앞에서 모자라면 체류 시간을 MIN_DWELL_MIN 까지 줄인다.
      - reorder·replace: move_time 이 안 될 때만 찾는다. 이웃한 남은 Stop 순서 바꾸기, 같은 category 장소로 바꾸기.
        이동 시간을 모르거나 이동 시간 증가가 REPLACE_MAX_EXTRA_MIN 을 넘으면 뺀다.
      - remove: move_time 이 되더라도 함께 제시한다 (노션 데모 대본 장면 6: 체류 단축 안 다음에 1곳 빼는 안).
      - 어느 안이든 재배치한 뒤 고정 일정이 그대로이고, 원래 없던 high Issue 가 생기지 않아야 한다.
      - 정렬: changed → extra_travel_min → 단계 순서 (propose_repairs 와 같다).
    """
    ctx = context if isinstance(context, CheckContext) else CheckContext.model_validate(context)
    stops = _ordered(plan.stops)
    first = _first_remaining(stops, ctx)
    if delay_min <= 0 or first is None:
        return []
    ready_at = stops[first].start + dt.timedelta(minutes=delay_min)

    found = _build(plan, "move_time", [stops], ready_at, ctx)
    if not found:
        found = _build(plan, "reorder", _reordered(stops, ctx), ready_at, ctx)
        found += _build(plan, "replace", _replaced(stops, ctx), ready_at, ctx)
    found += _build(plan, "remove", _removed(stops, ctx), ready_at, ctx)

    found.sort(key=lambda o: (o.metrics.changed, o.metrics.extra_travel_min, _STAGES[o.action]))
    return found[: th.MAX_REPAIRS]


def delay_shift(stops: list[Stop], ready_at: dt.datetime, ctx: CheckContext) -> list[Stop] | None:
    """남은 비고정 Stop 을 ready_at 이후로 미룬 새 Stop 목록 (시각순). 안 되면 None.

    - 대상: 아직 끝나지 않은(end > ctx.now) 첫 비고정 Stop 과 그 뒤 Stop. 이미 끝난 Stop·고정 Stop 은 그대로 둔다.
    - 첫 대상 Stop 은 ready_at(원래 첫 Stop 시작 + 지연) 이전에는 시작하지 않는다.
      그 뒤 Stop 은 이동 시간 + 여유가 모자랄 때만 필요한 만큼 미룬다. 여유로 흡수되면 그 Stop 은 바꾸지 않는다.
    - 고정 Stop 앞에서 자리가 모자라면 shrink_before_locked 로 체류 시간을 줄인다.
    - 방문일을 넘기면 None. 남은 비고정 Stop 이 없으면 그대로 돌려준다.
    """
    stops = _ordered(stops)
    first = _first_remaining(stops, ctx)
    if first is None:
        return list(stops)

    after = list(stops)
    after[first] = _shifted(stops[first], max(stops[first].start, ready_at))
    segment = first  # 줄일 수 있는 구간의 시작 (마지막 고정 Stop 다음)
    for i in range(first + 1, len(stops)):
        cur = stops[i]
        earliest = after[i - 1].end + _required_gap(after[i - 1], cur, ctx)
        if cur.locked:
            if earliest > cur.start:
                shrunk = shrink_before_locked(stops, after, segment, i, ctx)
                if shrunk is None:
                    return None
                after = shrunk
            segment = i + 1
        elif earliest > cur.start:
            after[i] = _shifted(cur, earliest)  # 여유가 모자라는 만큼만 미룬다

    day = stops[0].start.date()
    if any(s.end.date() != day for s in after):
        return None
    return after


def shrink_before_locked(
    original: list[Stop], after: list[Stop], first: int, locked_idx: int, ctx: CheckContext
) -> list[Stop] | None:
    """고정 Stop(after[locked_idx]) 앞 비고정 Stop[first:locked_idx] 의 체류 시간을 줄여 자리를 만든다.

    고정 Stop 에 가까운 Stop 부터 MIN_DWELL_MIN 까지 줄인다. 줄인 뒤 뒤 Stop 은 원래 시작 시각보다
    이르지 않게 다시 배치한다. 모두 줄여도 모자라면 None.
    """
    after = list(after)
    for j in range(locked_idx - 1, first - 1, -1):
        deficit = _deficit(after, locked_idx, ctx)
        if deficit <= 0:
            break
        dwell = int((after[j].end - after[j].start).total_seconds() // 60)
        cut = min(deficit, dwell - th.MIN_DWELL_MIN)
        if cut <= 0:
            continue
        trial = list(after)
        trial[j] = after[j].model_copy(update={"end": after[j].end - dt.timedelta(minutes=cut)})
        for k in range(j + 1, locked_idx):
            earliest = trial[k - 1].end + _required_gap(trial[k - 1], trial[k], ctx)
            trial[k] = _shifted(trial[k], max(original[k].start, earliest))
        if _deficit(trial, locked_idx, ctx) < deficit:
            after = trial
    if _deficit(after, locked_idx, ctx) > 0:
        return None
    return after


# ---------- 후보 일정 만들기 ----------

def _build(
    plan: Plan, action: RepairAction, candidates: Iterator[list[Stop]] | list[list[Stop]],
    ready_at: dt.datetime, ctx: CheckContext,
) -> list[RepairOption]:
    """후보 일정마다 delay_shift 로 재배치하고, 조건을 통과한 것만 RepairOption 으로 만든다."""
    old_total = total_travel_min(plan.stops, ctx)
    options = []
    for candidate in candidates:
        after = delay_shift(candidate, ready_at, ctx)
        if after is None or _recheck(plan, after, ctx) is None:
            continue
        if action != "move_time":
            new_total = total_travel_min(after, ctx)
            if old_total is None or new_total is None:
                continue  # 이동 시간을 모르면 재배치가 맞는지 알 수 없다
            if action != "remove" and new_total - old_total > th.REPLACE_MAX_EXTRA_MIN:
                continue
        option = _option(action, plan, after, ctx)
        if _keeps_locked(plan, option):
            options.append(option)
    return options


def _remaining(stops: list[Stop], ctx: CheckContext) -> list[int]:
    """지연의 영향을 받는 비고정 Stop 위치: 첫 남은 비고정 Stop 부터 다음 고정 Stop 앞까지."""
    first = _first_remaining(stops, ctx)
    if first is None:
        return []
    result = []
    for i in range(first, len(stops)):
        if stops[i].locked:
            break
        result.append(i)
    return result


def _reordered(stops: list[Stop], ctx: CheckContext) -> Iterator[list[Stop]]:
    """이웃한 남은 비고정 Stop 두 곳의 순서를 바꾼 일정. 먼저 갈 Stop 이 앞 Stop 의 시작 시각을 쓴다."""
    idx = _remaining(stops, ctx)
    for a, b in zip(idx, idx[1:]):
        first, second = stops[a], stops[b]
        new_first = _shifted(second, first.start)
        new_second = _shifted(first, new_first.end + _required_gap(new_first, first, ctx))
        swapped = list(stops)
        swapped[a], swapped[b] = new_first, new_second
        yield swapped


def _replaced(stops: list[Stop], ctx: CheckContext) -> Iterator[list[Stop]]:
    """남은 비고정 Stop 하나를 같은 category 장소(places.json, 일정에 없는 것)로 바꾼 일정. place_id 순."""
    used = {s.place_id for s in stops}
    for i in _remaining(stops, ctx):
        current = ctx.places.get(stops[i].place_id)
        if current is None:
            continue
        for place_id in sorted(ctx.places):
            place = ctx.places[place_id]
            if place_id in used or place.category != current.category:
                continue
            replaced = list(stops)
            replaced[i] = stops[i].model_copy(update={"place_id": place_id})
            yield replaced


def _removed(stops: list[Stop], ctx: CheckContext) -> Iterator[list[Stop]]:
    """남은 비고정 Stop 하나를 뺀 일정."""
    for i in _remaining(stops, ctx):
        yield stops[:i] + stops[i + 1:]


# ---------- 공통 ----------

def _first_remaining(stops: list[Stop], ctx: CheckContext) -> int | None:
    """아직 끝나지 않은(end > ctx.now) 첫 비고정 Stop 위치."""
    return next((i for i, s in enumerate(stops) if not s.locked and s.end > ctx.now), None)


def _deficit(stops: list[Stop], locked_idx: int, ctx: CheckContext) -> int:
    """고정 Stop 앞에서 모자란 시간(분). 0 이하면 자리가 충분하다."""
    prev, locked = stops[locked_idx - 1], stops[locked_idx]
    need = prev.end + _required_gap(prev, locked, ctx)
    return int((need - locked.start).total_seconds() // 60)


def _shifted(stop: Stop, start: dt.datetime) -> Stop:
    """체류 시간을 그대로 두고 시작 시각만 옮긴 Stop."""
    return stop.model_copy(update={"start": start, "end": start + (stop.end - stop.start)})
