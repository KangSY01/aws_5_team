"""보전 지표 계산. 해결안이 원래 일정을 얼마나 지켰는지 숫자로 보여 준다. LLM 미사용.

지표 뜻은 .kiro/specs/schedule-guardian/design.md 의 "보전 지표" 표를 따른다.
"""

import logging

from app.guardian.context import CheckContext
from app.models.plan import PreservationMetrics, Stop

logger = logging.getLogger(__name__)


def total_travel_min(stops: list[Stop], ctx: CheckContext) -> int | None:
    """시각 순서대로 이웃한 Stop 사이 이동 시간 합(분). 한 구간이라도 모르면 None."""
    ordered = sorted(stops, key=lambda s: s.start)
    total = 0
    for prev, stop in zip(ordered, ordered[1:]):
        minutes = ctx.travel(prev.place_id, stop.place_id)
        if minutes is None:
            return None
        total += minutes
    return total


def compute_metrics(before: list[Stop], after: list[Stop], ctx: CheckContext) -> PreservationMetrics:
    """원래 일정(before)과 해결안 적용 후 일정(after)의 보전 지표.

    - changed: 장소가 교체·제거된 Stop 수. 시각·순서만 바뀐 Stop 은 세지 않는다
    - kept: 원래 Stop 중 같은 장소가 새 일정에 남은 수
    - extra_travel_min: 새 일정 총 이동 시간 − 원래 총 이동 시간 (음수 가능).
      어느 한쪽 이동 시간을 모르면 0 으로 두고 경고 로그를 남긴다.
      교체 후보를 고를 때는 total_travel_min 이 None 인 후보를 먼저 걸러야 한다.
    - locked_kept: 원래 고정 Stop 이 모두 같은 stop_id 로 place_id·start·end 그대로 남았으면 True
    """
    after_by_id = {s.stop_id: s for s in after}
    after_places = {s.place_id for s in after}

    changed = 0
    for stop in before:
        new = after_by_id.get(stop.stop_id)
        if new is None or new.place_id != stop.place_id:
            changed += 1
    kept = sum(1 for s in before if s.place_id in after_places)

    old_total = total_travel_min(before, ctx)
    new_total = total_travel_min(after, ctx)
    if old_total is None or new_total is None:
        logger.warning("이동 시간을 모르는 구간이 있어 extra_travel_min 을 0 으로 둠")
        extra = 0
    else:
        extra = new_total - old_total

    return PreservationMetrics(
        changed=changed,
        kept=kept,
        extra_travel_min=extra,
        locked_kept=all(_same_locked(s, after_by_id.get(s.stop_id)) for s in before if s.locked),
    )


def _same_locked(original: Stop, new: Stop | None) -> bool:
    return (
        new is not None
        and new.place_id == original.place_id
        and new.start == original.start
        and new.end == original.end
    )
