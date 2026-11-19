"""일정 점검 (Guardian 담당). LLM을 쓰지 않는 순수 파이썬."""

import logging
from collections.abc import Callable

from app.guardian import rules
from app.guardian.context import CheckContext
from app.models.plan import Issue, Plan, Severity, Stop

logger = logging.getLogger(__name__)

_SEVERITY_ORDER: dict[Severity, int] = {"high": 0, "medium": 1, "low": 2}
_TYPE_ORDER = {"closed": 0, "rain": 1, "crowded": 2, "tight_transfer": 3}


def check_plan(plan: Plan, context: CheckContext | dict) -> list[Issue]:
    """일정에서 문제 구간을 찾는다.

    입력:
    - plan: 점검할 일정
    - context: CheckContext (dict 이면 CheckContext 로 검증한다). 날씨·혼잡·영업 정보·이동 시간·기준 시각.
    출력: Issue 목록 (type: crowded / rain / closed / tight_transfer). 문제가 없으면 [].
      - issue_id 는 `{stop_id}-{type}` 이라 같은 일정·같은 문제면 항상 같다.
      - 고정 일정(locked)의 Issue 는 심각도를 low 로 낮춘다. 해결안은 propose_repairs 가 만들지 않는다.
      - 정렬: 심각도 높은 순 → Stop 시작 이른 순 → 유형 순(closed, rain, crowded, tight_transfer).
      - 데이터가 없거나 규칙 하나가 실패하면 그 규칙만 건너뛰고 나머지 점검은 계속한다.
    """
    ctx = context if isinstance(context, CheckContext) else CheckContext.model_validate(context)
    stops = sorted(plan.stops, key=lambda s: s.start)
    start_of = {s.stop_id: s.start for s in stops}

    issues: list[Issue] = []
    for stop in stops:
        for rule in (rules.check_closed, rules.check_rain, rules.check_crowded):
            _collect(issues, rule, stop, ctx)
    for prev, stop in zip(stops, stops[1:]):
        _collect(issues, rules.check_tight_transfer, prev, stop, ctx)

    locked = {s.stop_id for s in stops if s.locked}
    issues = [_cap_locked(i) if i.stop_id in locked else i for i in issues]
    issues.sort(key=lambda i: (_SEVERITY_ORDER[i.severity], start_of[i.stop_id], _TYPE_ORDER[i.type]))
    return issues


def _collect(issues: list[Issue], rule: Callable[..., Issue | None], *args) -> None:
    """규칙 하나를 실행해 Issue 가 있으면 넣는다. 규칙이 실패해도 점검 전체는 멈추지 않는다."""
    try:
        issue = rule(*args)
    except Exception:
        stop: Stop = args[-2]
        logger.warning("점검 규칙 %s 실패, 건너뜀 (stop_id=%s)", rule.__name__, stop.stop_id, exc_info=True)
        return
    if issue is not None:
        issues.append(issue)


def _cap_locked(issue: Issue) -> Issue:
    """고정 일정의 Issue 는 알리기만 하고 심각도를 low 로 제한한다."""
    return issue.model_copy(update={"severity": "low", "detail": f"{issue.detail} (고정 일정, 원래 {issue.severity})"})
