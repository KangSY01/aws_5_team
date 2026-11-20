"""Guardian 점검에 쓰는 외부 정보 묶음(CheckContext).

check_plan·propose_repairs 는 boto3·HTTP 를 직접 부르지 않고 이 모델로 데이터를 받는다.
모델은 guardian/ 안에 두므로 공용 모델(app/models/)을 바꾸지 않는다.

TODO(Guardian 담당, 스펙 작업 build_context): app/tools/lookup.py 조회 결과로 조립하는 build_context(plan).
도구 반환 형식(11/20 결정)은 .kiro/specs/chat-agent/design.md 「조회 도구 반환 형식」에 있다. 필드 이름은 이 파일의 모델과 같다.
"""

import datetime as dt

from pydantic import AwareDatetime, BaseModel, Field

from app.models.plan import Place


class HourlyWeather(BaseModel):
    """한 시간 단위 예보 (기상청 단기예보 기준)."""

    time: AwareDatetime  # 예보 시각 (정시)
    pop: int = Field(ge=0, le=100)  # 강수확률(%)
    pty: int = 0  # 기상청 강수 형태 코드. 0=없음, 1=비, 2=비/눈, 3=눈, 4=소나기

    @property
    def has_precipitation(self) -> bool:
        return self.pty != 0


class OpeningHours(BaseModel):
    """장소 하나의 운영시간과 휴무일. 모르는 값은 None 이나 빈 목록으로 둔다."""

    opens: dt.time | None = None
    closes: dt.time | None = None
    closed_weekdays: list[int] = []  # datetime.weekday() 값. 0=월 ... 6=일
    closed_dates: list[dt.date] = []


class Event(BaseModel):
    """방문일의 대형 행사. 행사 가중 규칙에 쓴다."""

    name: str
    start: AwareDatetime
    end: AwareDatetime
    place_ids: list[str] = []  # 행사 장소와 그 근처로 보는 장소 ID (places.json 값)


class CheckContext(BaseModel):
    """check_plan·propose_repairs 에 넘기는 외부 정보.

    값이 없으면(None, 빈 dict) 그 값을 쓰는 규칙만 건너뛴다. 점검 전체를 실패시키지 않는다.
    """

    now: AwareDatetime  # 점검 기준 시각 (DEMO_NOW 또는 현재 시각)
    places: dict[str, Place]  # place_id → Place (places.json)
    weather: list[HourlyWeather] | None = None  # None 이면 예보 없음 → rain 규칙 건너뜀
    crowd: dict[str, float] = {}  # place_id → 방문일 집중률 (그 장소 안에서의 상대값)
    hours: dict[str, OpeningHours] = {}  # place_id → 운영 정보. 없으면 closed 규칙 건너뜀
    travel_min: dict[tuple[str, str], int] = {}  # (출발 place_id, 도착 place_id) → 이동 시간(분)
    events: list[Event] = []

    def travel(self, from_id: str, to_id: str) -> int | None:
        """두 장소 사이 이동 시간(분). 한쪽 방향만 있으면 그 값을 쓴다. 모르면 None."""
        if from_id == to_id:
            return 0
        return self.travel_min.get((from_id, to_id), self.travel_min.get((to_id, from_id)))
