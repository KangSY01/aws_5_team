"""예약 점검 (요구사항 8, 스펙 작업 11). LLM 을 쓰지 않는 순수 파이썬.

EventBridge Scheduler(예보 갱신 시각) → 점검 Lambda → 여기 run_scheduled_check → 결과 저장 → GET /alerts 가 읽는다.
- 이 모듈은 일정을 어떻게 읽고 결과를 어디에 저장하는지 모른다. load_plan·save_result 를 넘겨받는다.
  Lambda 연결·EventBridge 스케줄(infra/)과 DynamoDB 저장 형식(app/storage/)은 A 담당이다 (design.md 「예약 점검」).
- 해결안은 만들지 않는다. 배지를 누르면 프론트엔드가 POST /plan/check 로 해결안을 받는다 (api-contract 「GET /alerts」).
"""

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from typing import Any

from app.guardian.check import check_plan
from app.guardian.context import KST, build_context, resolve_now
from app.models.api import AlertsResponse
from app.models.plan import Plan

logger = logging.getLogger(__name__)

FORECAST_DAYS_AHEAD = 3  # 단기예보가 있는 범위(약 3일, data-rules.md). 이보다 먼 일정은 예약 점검하지 않는다


def is_due(plan: Plan, now: dt.datetime, days_ahead: int = FORECAST_DAYS_AHEAD) -> bool:
    """예약 점검 대상인지. 방문일이 오늘부터 days_ahead 일 뒤 사이면 True.

    지난 일정은 점검하지 않고, 예보가 없는 먼 일정은 rain 규칙이 건너뛰어져 점검해도 바뀌는 게 적다.
    """
    today = now.astimezone(KST).date()
    return today <= plan.date <= today + dt.timedelta(days=days_ahead)


def check_one(plan: Plan, now: dt.datetime, lookups: Any = None) -> AlertsResponse:
    """일정 하나를 점검한 결과 (GET /alerts 응답과 같은 형식). 해결안은 넣지 않는다."""
    ctx = build_context(plan, demo_now=now, lookups=lookups)
    return AlertsResponse(plan_id=plan.plan_id, checked_at=ctx.now, issues=check_plan(plan, ctx))


def run_scheduled_check(
    plan_ids: Iterable[str],
    load_plan: Callable[[str], Plan],
    save_result: Callable[[AlertsResponse], None],
    now: dt.datetime | None = None,
    lookups: Any = None,
) -> list[AlertsResponse]:
    """저장된 일정들을 점검하고 결과를 save_result 로 넘긴다. 점검 Lambda 가 부른다.

    입력:
    - plan_ids: 점검할 일정 ID 목록 (어떤 일정을 넘길지는 A 의 storage·Lambda 가 정한다)
    - load_plan: plan_id → Plan (예: app.storage.get_plan). 없으면 예외를 던져도 된다
    - save_result: 점검 결과(AlertsResponse) 하나를 저장한다
    - now: 기준 시각. 없으면 DEMO_NOW → 현재 시각(KST)
    - lookups: 조회 도구 묶음 (기본 app.tools.lookup, 테스트용)
    출력: 저장한 결과 목록
    - 방문일이 예보 범위 밖(is_due 가 False)이면 건너뛴다. 저장도 하지 않는다
    - 일정 하나를 읽거나 점검·저장하다 실패해도 로그만 남기고 다음 일정을 계속한다
    """
    now = resolve_now(now)
    saved = []
    for plan_id in plan_ids:
        try:
            plan = load_plan(plan_id)
            if not is_due(plan, now):
                logger.info("예약 점검 건너뜀: %s (방문일 %s, 예보 범위 밖)", plan_id, plan.date)
                continue
            result = check_one(plan, now, lookups)
            save_result(result)
        except Exception:
            logger.exception("예약 점검 실패, 다음 일정 계속: %s", plan_id)
            continue
        logger.info("예약 점검 저장: %s (Issue %d건)", plan_id, len(result.issues))
        saved.append(result)
    return saved
