"""엔드포인트별 요청·응답 모델. docs/api-contract.md 와 일치해야 한다."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_serializer

from app.models.plan import Issue, Language, Place, Plan, Profile, RepairOption, StopChange


class DemoOverride(BaseModel):
    """데모 스위치. 이 요청에서만 기준 시각과 날씨를 바꾼다."""

    now: AwareDatetime | None = None  # 점검 기준 시각. 없으면 DEMO_NOW 또는 현재 시각
    weather_preset: str | None = None  # backend/app/data/weather/{이름}.json 샘플 예보 이름


class Source(BaseModel):
    tool: str  # 도구 이름
    id: str  # 그 도구 결과 안의 항목 ID
    title: str  # 표시용 제목


class ChatRequest(BaseModel):
    session_id: str | None = None  # 없으면 서버가 새로 발급
    plan_id: str | None = None  # 일정이 아직 없으면 null
    message: str
    profile: Profile
    demo: DemoOverride | None = None


class ChatDelta(BaseModel):
    """/chat 스트리밍의 delta 이벤트. 답변 문장 조각."""

    text: str


class PlaceScoreBreakdown(BaseModel):
    """v0.3. 랭킹 엔진(app/ranking/)이 매긴 장소 점수와 근거. 화면의 점수 근거 칩용."""

    place_id: str
    total: float = Field(ge=0, le=100)  # 가중합 점수 0~100
    breakdown: dict[str, float]  # 항목 → 0~1 (interest, crowd, travel, weather, foreigner, dispersal)
    notes: list[str] = []  # 근거 코드. 예: "crowd:high", "interest:sea", "travel_min:15", "dispersal:west"


class ReturnStation(BaseModel):
    names: dict[str, str]
    lat: float
    lng: float


class ReturnRouteOption(BaseModel):
    station: ReturnStation
    travel_min: int
    walk_min: int
    depart_at: AwareDatetime
    time_source: Literal["kakao", "estimate"]


class ChatReturnRoutes(BaseModel):
    origin_place_id: str
    destination: ReturnStation
    options: list[ReturnRouteOption]


class ChatResponse(BaseModel):
    session_id: str
    plan_id: str
    answer: str
    language: Language
    sources: list[Source]
    plan_changes: list[StopChange]
    return_routes: ChatReturnRoutes | None = None
    score_breakdown: list[PlaceScoreBreakdown] = []  # v0.3. 랭킹을 쓰지 않은 응답은 빈 목록

    @model_serializer(mode="wrap")
    def _omit_empty_score_breakdown(self, handler):
        # 비어 있으면 JSON 에서 뺀다. 랭킹을 쓰지 않는 응답은 v0.2 와 같은 모양으로 나간다
        data = handler(self)
        if not data.get("score_breakdown"):
            data.pop("score_breakdown", None)
        if data.get("return_routes") is None:
            data.pop("return_routes", None)
        return data


class PlanResponse(BaseModel):
    plan: Plan
    places: list[Place]


class CheckRequest(BaseModel):
    plan_id: str
    demo: DemoOverride | None = None


class CheckResponse(BaseModel):
    plan_id: str
    checked_at: AwareDatetime
    issues: list[Issue]
    repairs: dict[str, list[RepairOption]]  # issue_id -> 해결안 (변경이 작은 순서)
    places: list[Place]  # repairs 에 새로 등장하는 장소


class DelayRequest(BaseModel):
    """POST /plan/{plan_id}/delay. 본문의 plan_id 는 경로의 값과 같아야 한다."""

    plan_id: str
    delay_min: int = Field(gt=0, le=240)  # 늦어진 시간(분)
    demo: DemoOverride | None = None


class DelayResponse(BaseModel):
    plan_id: str
    now: AwareDatetime  # 재조정 기준 시각. 이 시각 이후의 비고정 Stop만 바꾼다
    repairs: list[RepairOption]  # 변경이 작은 순서. 비어 있으면 고칠 필요 없음
    places: list[Place]  # repairs 에 새로 등장하는 장소


class AlertsResponse(BaseModel):
    """GET /alerts?plan_id=. 예약 점검(EventBridge)이 저장한 마지막 결과."""

    plan_id: str
    checked_at: AwareDatetime | None  # 예약 점검을 아직 안 했으면 null
    issues: list[Issue]


ImageType = Literal["image/jpeg", "image/png"]


class PhotoUploadUrlRequest(BaseModel):
    content_type: ImageType


class PhotoUploadUrlResponse(BaseModel):
    upload_url: str  # S3 presigned PUT URL
    key: str  # 업로드한 사진의 S3 키. /photo/translate 에 넘긴다
    expires_in: int  # URL 유효 시간(초)


class PhotoTranslateRequest(BaseModel):
    key: str
    language: Language


class BoundingBox(BaseModel):
    """Textract BoundingBox 와 같은 기준. 사진 크기 대비 비율(0~1)."""

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class PhotoItem(BaseModel):
    text_ko: str  # 사진에서 읽은 한국어 원문
    translated: str  # language 로 번역한 문장
    bbox: BoundingBox
    spicy: bool | None = None  # 매운 음식이면 true. 판단할 수 없으면 null


class PhotoTranslateResponse(BaseModel):
    key: str
    language: Language
    items: list[PhotoItem]


SpeakLanguage = Literal["ko", "en", "ja", "zh-Hans", "zh-Hant"]


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: SpeakLanguage  # 현지인 카드는 ko


class SpeakResponse(BaseModel):
    content_type: Literal["audio/mpeg"]
    audio_base64: str  # Polly 결과 mp3 를 base64 로 인코딩한 값


TranslationLanguage = Literal["ko", "en", "ja", "zh-Hans", "zh-Hant"]


class VoiceUrlRequest(BaseModel):
    language: TranslationLanguage  # 사용자가 말하는 언어


class TextTranslationRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2500)
    source: TranslationLanguage
    target: TranslationLanguage


class TextTranslationResponse(BaseModel):
    translatedText: str


class VoiceUrlResponse(BaseModel):
    url: str  # Transcribe 스트리밍 WebSocket presigned URL
    expires_in: int  # URL 유효 시간(초)
    sample_rate: int  # 오디오 샘플링 레이트(Hz)
    media_encoding: Literal["pcm"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
