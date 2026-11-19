"""문제 구간 해결안 (Guardian 담당). LLM을 쓰지 않는 순수 파이썬. 뼈대 단계: 시그니처만 있다."""

from app.models.plan import Issue, Plan, RepairOption


def propose_repairs(plan: Plan, issue: Issue, context: dict) -> list[RepairOption]:
    """Issue 하나에 대한 해결안을 변경이 작은 순서로 돌려준다.

    입력: plan, 해결할 issue, check_plan 과 같은 context
    출력: RepairOption 목록. 순서는 시간 이동 → 순서 변경 → 비슷한 장소로 교체 → 제외.
          각 해결안의 metrics 에 보전 지표(changed, kept, extra_travel_min, locked_kept)를 채운다.

    TODO(Guardian 담당):
    - locked=true 인 Stop 은 어떤 경우에도 바꾸지 않는다.
    """
    raise NotImplementedError("TODO(Guardian 담당)")
