"""일정 점검 (Guardian 담당). LLM을 쓰지 않는 순수 파이썬. 뼈대 단계: 시그니처만 있다."""

from app.models.plan import Issue, Plan


def check_plan(plan: Plan, context: dict) -> list[Issue]:
    """일정에서 문제 구간을 찾는다.

    입력:
    - plan: 점검할 일정
    - context: 점검에 필요한 외부 정보 (날씨, 혼잡, 영업 정보, 이동 시간, 기준 시각).
      TODO(Guardian 담당): 형식을 정하고 모델로 만든다.
    출력: Issue 목록 (type: crowded / rain / closed / tight_transfer). 문제가 없으면 [].

    TODO(Guardian 담당):
    - 집중률은 장소끼리 비교하지 않는다. 집중률에 없는 명소는 요일 규칙으로 대체한다.
    - 대형 행사일은 행사 가중 규칙을 따로 적용한다.
    """
    raise NotImplementedError("TODO(Guardian 담당)")
