"""문제 구간 해결안 (Guardian 담당). LLM을 쓰지 않는 순수 파이썬.

탐색 순서와 규칙은 .kiro/specs/schedule-guardian/design.md 「해결안 탐색」을 따른다.
locked=true 인 Stop 의 place_id·start·end 는 어떤 해결안에서도 바꾸지 않는다.
"""

import datetime as dt

from app.guardian import thresholds as th
from app.guardian.check import check_plan
from app.guardian.context import CheckContext, Event
from app.guardian.metrics import compute_metrics, total_travel_min
from app.models.plan import Issue, Plan, RepairAction, RepairOption, Severity, Stop, StopChange

# 남은 문제의 심각도 순위. 문제가 사라지면 -1
_SEVERITY_RANK: dict[Severity, int] = {"low": 0, "medium": 1, "high": 2}


def propose_repairs(plan: Plan, issue: Issue, context: CheckContext | dict) -> list[RepairOption]:
    """Issue 하나에 대한 해결안을 변경이 작은 순서로 돌려준다.

    입력: plan, 해결할 issue, check_plan 과 같은 context
    출력: RepairOption 목록. 순서는 시간 이동 → 순서 변경 → 비슷한 장소로 교체 → 제외.
          각 해결안의 metrics 에 보전 지표(changed, kept, extra_travel_min, locked_kept)를 채운다.

    TODO(Guardian 담당, 스펙 작업 5.4~5.6): replace·remove, 고정 일정 검증, 정렬, 상위 3개.
    """
    raise NotImplementedError("TODO(Guardian 담당)")


# ---------- 공통 도구 ----------

def _ordered(stops: list[Stop]) -> list[Stop]:
    return sorted(stops, key=lambda s: s.start)


def _with_stops(plan: Plan, stops: list[Stop]) -> Plan:
    return plan.model_copy(update={"stops": stops})


def _minutes(n: int) -> dt.timedelta:
    return dt.timedelta(minutes=n)


def _required_gap(prev: Stop, nxt: Stop, ctx: CheckContext) -> dt.timedelta:
    """prev 끝과 nxt 시작 사이에 있어야 하는 간격. 이동 시간 + 여유. 이동 시간을 모르면 겹치지만 않게 한다."""
    travel = ctx.travel(prev.place_id, nxt.place_id)
    if travel is None:
        return dt.timedelta(0)
    return _minutes(travel + th.TRANSFER_BUFFER_MIN)


def _changes(before: list[Stop], after: list[Stop]) -> list[StopChange]:
    """바뀐 Stop 마다 StopChange. 시각만 바뀐 Stop 도 넣는다. 제거는 after=None."""
    after_by_id = {s.stop_id: s for s in after}
    changes = []
    for stop in _ordered(before):
        new = after_by_id.get(stop.stop_id)
        if new != stop:
            changes.append(StopChange(stop_id=stop.stop_id, before=stop, after=new))
    return changes


def _option(action: RepairAction, plan: Plan, after: list[Stop], ctx: CheckContext) -> RepairOption:
    return RepairOption(
        action=action,
        changes=_changes(plan.stops, after),
        metrics=compute_metrics(plan.stops, after, ctx),
    )


def _recheck(plan: Plan, after: list[Stop], ctx: CheckContext) -> dict[str, Issue] | None:
    """해결안 적용 후 다시 점검한 Issue (issue_id → Issue).

    원래 없던 high Issue 가 새로 생기면 None (쓸 수 없는 해결안).
    """
    before = {i.issue_id: i for i in check_plan(plan, ctx)}
    after_issues = {i.issue_id: i for i in check_plan(_with_stops(plan, after), ctx)}
    for issue_id, new in after_issues.items():
        old = before.get(issue_id)
        if new.severity == "high" and (old is None or old.severity != "high"):
            return None
    return after_issues


def _remaining_rank(issue: Issue, after_issues: dict[str, Issue]) -> int | None:
    """해결안 적용 후 같은 Issue 의 심각도 순위. 사라지면 -1. 원래보다 나아지지 않았으면 None."""
    same = after_issues.get(issue.issue_id)
    rank = -1 if same is None else _SEVERITY_RANK[same.severity]
    if rank >= _SEVERITY_RANK[issue.severity]:
        return None
    return rank


def _improvement(plan: Plan, after: list[Stop], issue: Issue, ctx: CheckContext) -> int | None:
    """해결안 적용 후 대상 Issue 의 남은 심각도 순위(사라지면 -1). 쓸 수 없는 해결안이면 None.

    - 원래 없던 high Issue 가 새로 생기면 None
    - crowded 이고 장소가 그대로면: check_crowded 는 하루 단위라 시각을 옮겨도 Issue 가 남는다.
      원래 체류가 행사 시간대와 겹쳤고, 바뀐 뒤 겹치지 않으면 -1. 아니면 None
    - 그 밖(다른 유형, 또는 장소를 바꾼 경우): 같은 Issue 가 사라지거나 심각도가 낮아져야 한다
    """
    after_issues = _recheck(plan, after, ctx)
    if after_issues is None:
        return None
    before_stop = next((s for s in plan.stops if s.stop_id == issue.stop_id), None)
    after_stop = next((s for s in after if s.stop_id == issue.stop_id), None)
    same_place = before_stop is not None and after_stop is not None and before_stop.place_id == after_stop.place_id
    if issue.type == "crowded" and same_place:
        # 장소가 그대로면(시간 이동·순서 변경) 행사 시간대를 벗어났는지로 판단한다
        if not _event_overlaps(before_stop, ctx):
            return None
        return None if _event_overlaps(after_stop, ctx) else -1
    return _remaining_rank(issue, after_issues)


def _find(stops: list[Stop], stop_id: str) -> int | None:
    for i, s in enumerate(stops):
        if s.stop_id == stop_id:
            return i
    return None


# ---------- 1단계: 시간 이동 ----------

def try_move_time(plan: Plan, issue: Issue, ctx: CheckContext) -> list[RepairOption]:
    """대상 Stop 의 시각을 SHIFT_STEPS_MIN 폭으로 앞뒤로 옮기는 해결안 (최대 1개).

    - 장소와 순서는 그대로다. 그래서 metrics.changed 는 0 이다.
    - 이웃과 겹치면 이웃한 비고정 Stop 의 체류 시간을 MIN_DWELL_MIN 까지 줄여 자리를 만든다.
      이전 Stop 은 끝을 앞당기고, 다음 Stop 은 시작을 늦춘다. 고정 이웃이면 그 폭은 쓰지 않는다.
    - 방문일을 벗어나거나 기준 시각(ctx.now)보다 이른 시각으로는 옮기지 않는다.
    - crowded 는 집중률이 하루 단위라 행사 시간대 근거가 있을 때만 시도한다 (요구사항 4.3).
      체류 시간이 그 장소 행사 시간대와 겹칠 때만 만들고, 옮긴 뒤 겹치지 않아야 한다.
    - 다른 유형은 같은 Issue 가 사라지거나 심각도가 낮아지는 후보만 쓴다.
    - 어느 유형이든 원래 없던 high Issue 가 새로 생기는 후보는 뺀다.
      후보가 여럿이면 남은 심각도가 낮은 것 → 옮긴 폭이 작은 것 → 바뀐 Stop 이 적은 것 순으로 하나를 고른다.
    """
    stops = _ordered(plan.stops)
    idx = _find(stops, issue.stop_id)
    if idx is None or stops[idx].locked:
        return []
    if issue.type == "crowded" and not _event_overlaps(stops[idx], ctx):
        return []

    best: tuple[tuple[int, int, int], list[Stop]] | None = None
    for step in th.SHIFT_STEPS_MIN:
        for delta in (-step, step):
            after = _shift_with_neighbors(stops, idx, delta, ctx)
            if after is None:
                continue
            rank = _improvement(plan, after, issue, ctx)
            if rank is None:
                continue
            moved = sum(1 for a, b in zip(stops, after) if a != b)
            key = (rank, step, moved)
            if best is None or key < best[0]:
                best = (key, after)
    if best is None:
        return []
    return [_option("move_time", plan, best[1], ctx)]


def _shift_with_neighbors(stops: list[Stop], idx: int, delta_min: int, ctx: CheckContext) -> list[Stop] | None:
    """stops[idx] 를 delta_min 분 옮기고, 필요하면 이웃 체류 시간을 줄인 새 Stop 목록. 안 되면 None."""
    target = stops[idx]
    delta = _minutes(delta_min)
    moved = target.model_copy(update={"start": target.start + delta, "end": target.end + delta})
    day = target.start.date()
    if moved.start.date() != day or moved.end.date() != day or moved.start < ctx.now:
        return None

    after = list(stops)
    after[idx] = moved

    if idx > 0:
        prev = stops[idx - 1]
        latest_end = moved.start - _required_gap(prev, moved, ctx)
        if prev.end > latest_end:
            shrunk = _shrink(prev, end=latest_end)
            if shrunk is None:
                return None
            after[idx - 1] = shrunk

    if idx < len(stops) - 1:
        nxt = stops[idx + 1]
        earliest_start = moved.end + _required_gap(moved, nxt, ctx)
        if nxt.start < earliest_start:
            shrunk = _shrink(nxt, start=earliest_start)
            if shrunk is None:
                return None
            after[idx + 1] = shrunk
    return after


# ---------- 2단계: 순서 변경 ----------

def try_reorder(plan: Plan, issue: Issue, ctx: CheckContext) -> list[RepairOption]:
    """대상 Stop 과 이웃한 비고정 Stop 의 순서를 바꾸는 해결안 (앞 이웃, 뒤 이웃 각각 최대 1개씩).

    - 두 Stop 이 쓰던 시간 구간 [앞 Stop 시작, 뒤 Stop 끝] 안에서 순서만 바꾼다.
      먼저 갈 Stop 은 구간 시작에, 나중 갈 Stop 은 구간 끝에 붙이고 체류 시간은 그대로 둔다.
      그래서 구간 밖 Stop 의 시각은 바뀌지 않는다.
    - 두 Stop 사이, 구간 앞뒤 이웃과의 간격이 이동 시간 + 여유보다 짧으면 만들지 않는다.
    - 구간 시작이 기준 시각(ctx.now)보다 이르면 만들지 않는다 (이미 시작한 일정).
    - 이동 시간을 모르는 구간이 있거나 이동 시간 증가가 REPLACE_MAX_EXTRA_MIN 을 넘으면 뺀다.
    - 대상 Issue 개선 여부와 새 high Issue 검사는 try_move_time 과 같다.
    - 장소는 그대로라 metrics.changed 는 0 이다. 시각이 바뀐 두 Stop 이 changes 에 들어간다.
    """
    stops = _ordered(plan.stops)
    idx = _find(stops, issue.stop_id)
    if idx is None or stops[idx].locked:
        return []

    old_total = total_travel_min(stops, ctx)
    if old_total is None:
        return []

    options = []
    for first in (idx - 1, idx):  # (앞 이웃, 대상), (대상, 뒤 이웃) 두 쌍
        if first < 0 or first + 1 >= len(stops):
            continue
        after = _swap_pair(stops, first, ctx)
        if after is None:
            continue
        new_total = total_travel_min(after, ctx)
        if new_total is None or new_total - old_total > th.REPLACE_MAX_EXTRA_MIN:
            continue
        if _improvement(plan, after, issue, ctx) is None:
            continue
        options.append(_option("reorder", plan, after, ctx))
    return options


def _swap_pair(stops: list[Stop], first: int, ctx: CheckContext) -> list[Stop] | None:
    """stops[first] 와 stops[first+1] 의 순서를 바꾼 새 Stop 목록 (시각순). 안 되면 None."""
    a, b = stops[first], stops[first + 1]
    if a.locked or b.locked or a.start < ctx.now:
        return None

    new_b = b.model_copy(update={"start": a.start, "end": a.start + (b.end - b.start)})
    new_a = a.model_copy(update={"start": b.end - (a.end - a.start), "end": b.end})
    if new_a.start - new_b.end < _required_gap(new_b, new_a, ctx):
        return None
    if first > 0 and new_b.start - stops[first - 1].end < _required_gap(stops[first - 1], new_b, ctx):
        return None
    if first + 2 < len(stops) and stops[first + 2].start - new_a.end < _required_gap(new_a, stops[first + 2], ctx):
        return None

    after = list(stops)
    after[first], after[first + 1] = new_b, new_a
    return after


# ---------- 3단계: 비슷한 장소로 교체 ----------

def try_replace(plan: Plan, issue: Issue, ctx: CheckContext) -> list[RepairOption]:
    """대상 Stop 의 장소를 비슷한 장소로 바꾸는 해결안 목록. 시각은 그대로 둔다.

    - 후보는 ctx.places(places.json)에 있는 장소만 쓴다. 일정에 이미 있는 장소는 빼고 새 ID 를 만들지 않는다.
    - 후보 조건: 같은 category. rain 이면 category 가 달라도 실내(indoor) 장소를 넣는다 (요구사항 4.4).
    - 이동 시간을 모르는 구간이 생기거나 이동 시간 증가가 REPLACE_MAX_EXTRA_MIN 을 넘으면 뺀다.
    - 바꾼 뒤 같은 Issue 가 사라지거나 낮아져야 하고, 새 high Issue 가 생기면 뺀다.
    - 순서: rain 이면 실내 장소 먼저 → 이동 시간 증가가 작은 순 → place_id 순 (항상 같은 결과).
    - metrics.changed 는 1 이다 (장소가 바뀐 Stop 1곳).
    """
    stops = _ordered(plan.stops)
    idx = _find(stops, issue.stop_id)
    if idx is None or stops[idx].locked:
        return []
    target = stops[idx]
    current = ctx.places.get(target.place_id)
    old_total = total_travel_min(stops, ctx)
    if current is None or old_total is None:
        return []

    used = {s.place_id for s in stops}
    found: list[tuple[tuple[bool, int, str], RepairOption]] = []
    for place in ctx.places.values():
        if place.place_id in used:
            continue
        same_category = place.category == current.category
        if not (same_category or (issue.type == "rain" and place.indoor)):
            continue
        after = list(stops)
        after[idx] = target.model_copy(update={"place_id": place.place_id})
        new_total = total_travel_min(after, ctx)
        if new_total is None or new_total - old_total > th.REPLACE_MAX_EXTRA_MIN:
            continue
        if _improvement(plan, after, issue, ctx) is None:
            continue
        indoor_first = issue.type == "rain" and not place.indoor
        found.append(((indoor_first, new_total - old_total, place.place_id), _option("replace", plan, after, ctx)))
    found.sort(key=lambda item: item[0])
    return [option for _, option in found]


# ---------- 4단계: 제외 ----------

def try_remove(plan: Plan, issue: Issue, ctx: CheckContext) -> list[RepairOption]:
    """대상 Stop 을 일정에서 빼는 해결안 (최대 1개).

    - 다른 Stop 의 시각은 바꾸지 않는다. changes 에는 대상 Stop 하나가 after=None 으로 들어간다.
    - 다른 단계 해결안이 없을 때만 쓰는지는 propose_repairs 가 정한다 (요구사항 4.9).
    - 빼고 나서 원래 없던 high Issue 가 생기면 만들지 않는다.
    - 앞뒤 Stop 사이 이동 시간을 모르면 extra_travel_min 은 0 으로 둔다 (compute_metrics 규칙, 경고 로그).
    - metrics.changed 는 1 이다.
    """
    idx = _find(plan.stops, issue.stop_id)
    if idx is None or plan.stops[idx].locked:
        return []
    after = [s for s in plan.stops if s.stop_id != issue.stop_id]
    if _improvement(plan, after, issue, ctx) is None:
        return []
    return [_option("remove", plan, after, ctx)]


def _shrink(stop: Stop, *, start: dt.datetime | None = None, end: dt.datetime | None = None) -> Stop | None:
    """비고정 Stop 의 체류 시간을 줄인다. 고정 일정이거나 MIN_DWELL_MIN 미만이 되면 None."""
    if stop.locked:
        return None
    new_start = start or stop.start
    new_end = end or stop.end
    if new_end - new_start < _minutes(th.MIN_DWELL_MIN):
        return None
    return stop.model_copy(update={"start": new_start, "end": new_end})


def _event_window(event: Event, day: dt.date) -> tuple[dt.datetime, dt.datetime] | None:
    """방문일 하루 안의 행사 시간대. 여러 날 행사는 매일 같은 시각에 열린다고 본다.

    끝 시각이 시작 시각보다 이르면(자정을 넘기면) 그날 자정까지로 본다.
    """
    if not (event.start.date() <= day <= event.end.date()):
        return None
    start = dt.datetime.combine(day, event.start.timetz())
    end = dt.datetime.combine(day, event.end.timetz())
    if end <= start:
        end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, tzinfo=start.tzinfo))
    return start, end


def _event_overlaps(stop: Stop, ctx: CheckContext) -> bool:
    """Stop 체류 시간이 그 장소(또는 근처) 행사 시간대와 겹치면 True. crowded 시간 이동의 근거."""
    for event in ctx.events:
        if stop.place_id not in event.place_ids:
            continue
        window = _event_window(event, stop.start.date())
        if window and stop.start < window[1] and window[0] < stop.end:
            return True
    return False
