"""저장소 오류. 호출하는 쪽(agent.py, handler.py)이 api-contract 오류 형식으로 바꾼다.

| 예외 | 뜻 | 변환 |
|---|---|---|
| PlanNotFoundError, SessionNotFoundError | 없는 ID | 404 plan_not_found / session_not_found (code 속성) |
| InvalidDataError | 모델 검증을 통과하지 못한 값 | 호출한 쪽의 버그. 422 또는 500 |
| StorageError | DynamoDB 오류, 깨진 저장 데이터 | 500 internal_error |
"""


class StorageError(Exception):
    """저장소 자체의 오류 (DynamoDB 호출 실패, 설정 누락, 저장된 데이터가 모델과 안 맞음)."""


class InvalidDataError(ValueError):
    """저장하려는 값이 Pydantic 모델 검증을 통과하지 못했다. 메시지에는 필드 위치만 담고 값은 담지 않는다."""


class PlanNotFoundError(LookupError):
    code = "plan_not_found"

    def __init__(self, plan_id: str):
        super().__init__(f"{plan_id} 을 찾을 수 없습니다.")
        self.plan_id = plan_id


class PlanAccessDeniedError(PlanNotFoundError):
    """세션에 연결되지 않은 일정을 요청했다. 일정 존재 여부를 드러내지 않도록 404 와 같게 변환한다."""


class PlanAlreadyExistsError(Exception):
    def __init__(self, plan_id: str):
        super().__init__(f"{plan_id} 은 이미 있습니다.")
        self.plan_id = plan_id


class SessionNotFoundError(LookupError):
    code = "session_not_found"

    def __init__(self, session_id: str):
        super().__init__(f"{session_id} 세션을 찾을 수 없습니다.")
        self.session_id = session_id
