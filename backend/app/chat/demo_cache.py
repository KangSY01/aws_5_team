"""데모 장면 1 일정 캐시. DEMO_CACHE_ENABLED=1 이고 대본 문장이 그대로 들어왔을 때만 쓴다. LLM 을 부르지 않는다.

배포 API 의 실제 Bedrock 은 같은 문장에도 매번 다른 일정을 만들어 시연이 흔들린다 (docs/demo-readiness.md 「점검 2」 결정).
그래서 대본 문장 하나에 한해 대본 일정(흰여울 → 자갈치 → 해운대 → 해운대 빛축제)을 돌려준다.

- 문장 비교는 유니코드 정규화(NFKC)와 공백 제거만 한다. 뜻이 비슷한 다른 문장에는 쓰지 않는다.
- 장소 ID 는 places.json 에 있는 값이다. 빛축제는 행사이고, 그 장소가 haeundae-beach 다 (events.json, Guardian 장면 1 과 같다).
- 일정은 다른 대화와 같은 저장 경로(storage.create_plan, link_plan)로 저장하고, 요청마다 새 plan_id 를 쓴다.
  그래서 이전 시연에서 바꾼 일정이 다음 시연에 남지 않는다.
- Guardian 배지·대안은 이 모듈이 만들지 않는다. 저장된 일정을 /plan/check 가 평소처럼 점검한다.
"""

import datetime as dt
import re
import unicodedata

from app import config
from app.models.plan import Plan, Profile, Stop

# 대본 문장 (노션 대본 장면 1, 일본어)
TRIGGER = "11月28日(土)に釜山で一日過ごしたいです。海が見える所と、夜は光の祭りに行きたいです。辛いものは苦手です。"

DATE = dt.date(2026, 11, 28)
KST = dt.timezone(dt.timedelta(hours=9))
FESTIVAL_NAME = "해운대 빛축제"  # events.json 의 행사 이름 (한국어 원문 그대로 답변에 쓴다)
FESTIVAL_STOP_ID = "s4"
# (stop_id, place_id, 시작, 끝). 빛축제 자리(s4)는 처음에 고정하지 않는다. 발표자가 화면에서 누른다
STOPS: tuple[tuple[str, str, str, str], ...] = (
    ("s1", "huinnyeoul-village", "10:00", "11:30"),
    ("s2", "jagalchi-market", "12:00", "13:00"),
    ("s3", "haeundae-beach", "14:30", "16:00"),
    (FESTIVAL_STOP_ID, "haeundae-beach", "17:30", "19:30"),
)


def normalize(text: str) -> str:
    """전각·반각 차이(NFKC)와 공백·줄바꿈만 없앤다."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


_TRIGGER_KEY = normalize(TRIGGER)


def matches(message: str) -> bool:
    """데모 캐시를 쓸 요청인지. DEMO_CACHE_ENABLED 가 꺼져 있으면 언제나 False."""
    return config.DEMO_CACHE_ENABLED and isinstance(message, str) and normalize(message) == _TRIGGER_KEY


def _at(hhmm: str) -> dt.datetime:
    return dt.datetime.combine(DATE, dt.time.fromisoformat(hhmm), KST)


def build_plan(plan_id: str, profile: Profile) -> Plan:
    """대본 일정. 프로필은 요청 값을 그대로 쓴다."""
    stops = [Stop(stop_id=sid, place_id=pid, start=_at(start), end=_at(end), locked=False) for sid, pid, start, end in STOPS]
    return Plan(plan_id=plan_id, date=DATE, profile=profile, stops=stops)
