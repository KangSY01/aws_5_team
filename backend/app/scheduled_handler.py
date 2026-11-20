"""예약 점검 Lambda 진입점 (에이전트 담당).

EventBridge Scheduler(예보 갱신 시각) → 이 Lambda → guardian.scheduled.run_scheduled_check(D) → 결과를 DynamoDB 에 저장
→ GET /alerts 가 읽는다. 점검 로직은 전부 D 의 코드이고, 여기서는 일정 읽기·결과 저장(app/storage)만 연결한다.
LLM 을 부르지 않고 해결안도 만들지 않는다. 일정을 바꾸지 않는다(알림 항목 ALERTS 만 쓴다).

이벤트(JSON, 모두 선택):
  {"plan_ids": ["plan-1", ...]}   점검할 일정을 직접 지정한다 (수동 데모 실행). 없으면 저장된 일정 전부를 점검한다.
  {"now": "2026-11-21T11:10:00+09:00"}   기준 시각. 없으면 DEMO_NOW 환경 변수, 그것도 없으면 현재 시각.
날짜 필터(방문일이 예보 범위 안인 일정만 점검)는 run_scheduled_check 가 한다. 여기서는 거르지 않는다.
"""

import datetime as dt
import logging
from typing import Any

from app import storage
from app.guardian.context import KST
from app.guardian.scheduled import run_scheduled_check

logger = logging.getLogger(__name__)


def _parse_plan_ids(value: Any) -> list[str] | None:
    """없으면(None) 전부 점검한다는 뜻이다. 빈 목록은 "점검할 일정이 없다"는 뜻이라 그대로 둔다."""
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError("plan_ids 는 비어 있지 않은 문자열의 목록이어야 합니다.")
    return list(dict.fromkeys(value))  # 중복은 한 번만


def _parse_now(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("now 는 ISO 8601 시각이어야 합니다 (예: 2026-11-21T11:10:00+09:00).") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)  # 시간대가 없으면 한국 시간으로 본다


def handler(event: dict | None, context: Any = None) -> dict:
    """점검한 일정 수를 돌려준다. 일정 하나가 실패해도 나머지는 계속 점검한다 (run_scheduled_check).

    반환: {"requested": 점검 대상 수, "saved": 저장한 결과 수, "results": [{"plan_id", "checked_at", "issues"(건수)}]}
    저장한 결과가 requested 보다 적은 이유는 예보 범위 밖이라 건너뛰었거나 일정 하나가 실패해서다 (로그에 일정 ID 가 남는다).
    잘못된 이벤트나 목록 조회 실패는 예외로 끝낸다. 호출한 사람이 오류를 바로 볼 수 있다.
    """
    event = event if isinstance(event, dict) else {}
    plan_ids = _parse_plan_ids(event.get("plan_ids"))
    now = _parse_now(event.get("now"))
    if plan_ids is None:
        plan_ids = storage.list_plan_ids()

    results = run_scheduled_check(plan_ids, storage.get_plan, storage.save_alerts, now=now)

    logger.info("예약 점검 종료: 대상 %d건, 저장 %d건", len(plan_ids), len(results))
    return {
        "requested": len(plan_ids),
        "saved": len(results),
        "results": [
            {"plan_id": r.plan_id, "checked_at": r.checked_at.isoformat(), "issues": len(r.issues)} for r in results
        ],
    }
