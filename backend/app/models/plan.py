"""일정 관련 데이터 모델. docs/api-contract.md 의 JSON 필드 이름과 일치해야 한다."""

import datetime as dt
from typing import Literal

from pydantic import AwareDatetime, BaseModel

Language = Literal["en", "ja", "zh-Hans", "zh-Hant"]
IssueType = Literal["crowded", "rain", "closed", "tight_transfer"]
Severity = Literal["low", "medium", "high"]
RepairAction = Literal["move_time", "reorder", "replace", "remove"]


class Profile(BaseModel):
    language: Language
    interests: list[str] = []
    companions: str | None = None  # 예: solo, couple, family_with_kids
    diet: list[str] = []  # 예: halal, vegetarian
    budget: str | None = None  # 예: low, mid, high


class Place(BaseModel):
    place_id: str
    names: dict[Language, str]
    lat: float
    lng: float
    category: str
    indoor: bool
    nearest_station: str | None = None


class Stop(BaseModel):
    stop_id: str
    place_id: str
    start: AwareDatetime  # 시간대 포함 ISO 시각 (예: 2026-11-21T10:00:00+09:00)
    end: AwareDatetime
    locked: bool = False  # true면 어떤 경우에도 수정하지 않는다


class Plan(BaseModel):
    plan_id: str
    date: dt.date
    profile: Profile
    stops: list[Stop]


class Issue(BaseModel):
    issue_id: str
    type: IssueType
    stop_id: str
    severity: Severity
    detail: str


class PreservationMetrics(BaseModel):
    changed: int  # 바뀐 곳 수
    kept: int  # 유지한 곳 수
    extra_travel_min: int  # 늘어난 이동 시간(분)
    locked_kept: bool  # 고정 일정 유지 여부


class StopChange(BaseModel):
    """Stop 하나의 변경 전후. before=None이면 추가, after=None이면 제거."""

    stop_id: str
    before: Stop | None = None
    after: Stop | None = None


class RepairOption(BaseModel):
    action: RepairAction
    changes: list[StopChange]
    metrics: PreservationMetrics
