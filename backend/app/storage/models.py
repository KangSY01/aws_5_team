"""저장소 안에서만 쓰는 모델. 공용 models/ 는 건드리지 않는다.

대화 이력은 이번 단계에서 저장하지 않는다. 필요해지면 이 모델에 필드를 더한다
(읽을 때 모르는 필드는 무시하므로 이미 저장된 세션과 호환된다).
"""

from pydantic import AwareDatetime, BaseModel

from app.models.plan import Profile


class SessionState(BaseModel):
    """채팅 세션의 최소 상태. 사용자 프로필과 연결된 일정 하나."""

    session_id: str
    plan_id: str | None = None  # 아직 일정이 없으면 None
    profile: Profile
    created_at: AwareDatetime
    updated_at: AwareDatetime
