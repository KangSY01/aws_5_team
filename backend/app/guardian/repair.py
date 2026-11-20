"""문제 구간 해결안 (Guardian 담당). LLM을 쓰지 않는 순수 파이썬.

탐색 순서와 규칙은 .kiro/specs/schedule-guardian/design.md 「해결안 탐색」을 따른다.
locked=true 인 Stop 의 place_id·start·end 는 어떤 해결안에서도 바꾸지 않는다.
"""

import datetime as dt

from app.guardian import thresholds as th
from app.guardian.check import check_plan
from app.guardian.context import CheckContext, Event
from app.guardian.metrics import compute_metrics
from app.models.plan import Issue, Plan, RepairAction, RepairOption, Severity, Stop, StopChange

# 남은 문제의 심각도 순위. 문제가 사라지면 -1
_SEVERITY_RANK: dict[Severity, int] = {"low": 0, "medium": 1, "high": 2}


def propose_repairs(plan: Plan, issue: Issue, context: CheckContext | dict) -> list[RepairOption]:
    """Issue 하나에 대한 해결안을 변경이 작은 순서로 돌려준다.

    입력: plan, 해결할 issue, check_plan 과 같은 context
    출력: RepairOption 목록. 순서는 시간 이동 → 순서 변경 → 비슷한 장소로 교체 → 제외.
          각 해결안의 metrics 에 보전 지표(changed, kept, extra_travel_min, locked_kept)를 채운다.

    TODO(Guardian 담당, 스펙 작업 5.3~5.6): reorder·replace·remove, 재점검 필터, 정렬, 상위 3개.
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
            after_issues = _recheck(plan, after, ctx)
            if after_issues is None:
                continue
            if issue.type == "crowded":
                # check_crowded 는 하루 단위라 시각을 옮겨도 Issue 가 남는다. 행사 시간대를 벗어났는지로 판단한다
                rank = None if _event_overlaps(after[idx], ctx) else -1
            else:
                rank = _remaining_rank(issue, after_issues)
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
