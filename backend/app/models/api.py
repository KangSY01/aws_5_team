"""엔드포인트별 요청·응답 모델. docs/api-contract.md 와 일치해야 한다."""

from pydantic import AwareDatetime, BaseModel

from app.models.plan import Issue, Language, Place, Plan, Profile, RepairOption, StopChange


class Source(BaseModel):
    tool: str  # 도구 이름
    id: str  # 그 도구 결과 안의 항목 ID
    title: str  # 표시용 제목


class ChatRequest(BaseModel):
    session_id: str | None = None  # 없으면 서버가 새로 발급
    plan_id: str | None = None  # 일정이 아직 없으면 null
    message: str
    profile: Profile


class ChatResponse(BaseModel):
    session_id: str
    plan_id: str
    answer: str
    language: Language
    sources: list[Source]
    plan_changes: list[StopChange]


class PlanResponse(BaseModel):
    plan: Plan
    places: list[Place]


class CheckRequest(BaseModel):
    plan_id: str


class CheckResponse(BaseModel):
    plan_id: str
    checked_at: AwareDatetime
    issues: list[Issue]
    repairs: dict[str, list[RepairOption]]  # issue_id -> 해결안 (변경이 작은 순서)
    places: list[Place]  # repairs 에 새로 등장하는 장소


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
