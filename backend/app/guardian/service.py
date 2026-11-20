"""API 경로용 Guardian 조립 (스펙 작업 9). handler.py 는 여기 함수만 부른다. LLM 미사용.

- run_check: POST /plan/check → CheckResponse
- run_delay: POST /plan/{plan_id}/delay → DelayResponse
일정을 저장하지 않는다. 해결안 적용은 프론트엔드가 PUT /plan/{plan_id} 로 한다 (요구사항 5.1).
"""

from typing import Any

from app.guardian.check import check_plan
from app.guardian.context import build_context, with_repair_travel
from app.guardian.delay import propose_delay_repairs
from app.guardian.repair import new_places, propose_repairs
from app.models.api import CheckResponse, DelayResponse, DemoOverride
from app.models.plan import Plan


def run_check(plan: Plan, demo: DemoOverride | None = None, lookups: Any = None) -> CheckResponse:
    """일정을 점검하고 Issue 마다 해결안을 붙인다.

    - checked_at: demo.now → DEMO_NOW → 현재 시각
    - repairs: issue_id → 해결안 (고정 일정 Issue 는 []). 문제가 없으면 issues: [], repairs: {}
    - places: 해결안에 새로 등장하는 장소
    - demo.weather_preset 이 없는 이름이면 WeatherPresetNotFound (handler 가 422 로 바꾼다)
    """
    ctx = build_context(plan, *_demo(demo), lookups=lookups)
    issues = check_plan(plan, ctx)
    ctx = with_repair_travel(ctx, plan, {i.stop_id for i in issues}, lookups=lookups)
    repairs = {i.issue_id: propose_repairs(plan, i, ctx) for i in issues}
    places = new_places(plan, [o for options in repairs.values() for o in options], ctx)
    return CheckResponse(plan_id=plan.plan_id, checked_at=ctx.now, issues=issues, repairs=repairs, places=places)


def run_delay(plan: Plan, delay_min: int, demo: DemoOverride | None = None, lookups: Any = None) -> DelayResponse:
    """일정이 delay_min 분 늦어졌을 때 기준 시각 이후의 비고정 Stop 만 고친 해결안 (요구사항 7)."""
    ctx = build_context(plan, *_demo(demo), lookups=lookups)
    remaining = [s.stop_id for s in plan.stops if not s.locked and s.end > ctx.now]
    ctx = with_repair_travel(ctx, plan, remaining, lookups=lookups)
    repairs = propose_delay_repairs(plan, delay_min, ctx)
    return DelayResponse(plan_id=plan.plan_id, now=ctx.now, repairs=repairs, places=new_places(plan, repairs, ctx))


def _demo(demo: DemoOverride | None) -> tuple:
    return (demo.now, demo.weather_preset) if demo else (None, None)
