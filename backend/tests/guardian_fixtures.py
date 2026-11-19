"""Guardian 테스트용 고정 데이터. sample_plan.json(11/21 토, 4곳, 자갈치시장 고정) 기준.

여기 수치(집중률·강수확률·이동 시간)는 테스트용으로 정한 값이다. 실제 데이터가 아니며 화면에 쓰지 않는다.
테스트마다 make_context(**덮어쓸 값)으로 필요한 부분만 바꿔 쓴다.
"""

import datetime as dt
from pathlib import Path

from pydantic import TypeAdapter

from app.guardian.context import CheckContext, HourlyWeather
from app.models.plan import Place, Plan

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
KST = dt.timezone(dt.timedelta(hours=9))
DATE = dt.date(2026, 11, 21)


def load_places() -> dict[str, Place]:
    places = TypeAdapter(list[Place]).validate_json((DATA_DIR / "places.json").read_text(encoding="utf-8"))
    return {p.place_id: p for p in places}


def load_sample_plan() -> Plan:
    return Plan.model_validate_json((DATA_DIR / "sample_plan.json").read_text(encoding="utf-8"))


def at(hour: int, minute: int = 0) -> dt.datetime:
    """방문일(11/21) 한국 시각."""
    return dt.datetime(DATE.year, DATE.month, DATE.day, hour, minute, tzinfo=KST)


def hourly_weather(pop: int = 20, rain_hours: range = range(0)) -> list[HourlyWeather]:
    """08~20시 예보. rain_hours 에 든 시각은 강수확률 80%·비(pty=1)로 만든다."""
    return [
        HourlyWeather(time=at(h), pop=80, pty=1) if h in rain_hours else HourlyWeather(time=at(h), pop=pop)
        for h in range(8, 21)
    ]


# 일정 순서대로 이동 시간. 모두 이동 여유 10분 이상이 남도록 정했다.
#   s1 감천 11:30 → s2 자갈치 12:00 : 15분 (여유 15분)
#   s2 자갈치 13:00 → s3 부산타워 13:30 : 10분 (여유 20분)
#   s3 부산타워 14:30 → s4 해운대 15:30 : 40분 (여유 20분)
BASE_TRAVEL_MIN = {
    ("gamcheon-village", "jagalchi-market"): 15,
    ("jagalchi-market", "busan-tower"): 10,
    ("busan-tower", "haeundae-beach"): 40,
}

# 집중률은 장소마다 상대값이다. 모두 CROWD_MEDIUM_RATE(85) 미만으로 두어 기본 상태에서는 문제가 없게 한다.
# 감천문화마을은 집중률 데이터에 없는 장소라 넣지 않는다 (요일 규칙 대상).
BASE_CROWD = {
    "jagalchi-market": 60.0,
    "busan-tower": 50.0,
    "haeundae-beach": 70.0,
}


def make_context(**overrides) -> CheckContext:
    """기본 context. 비 없음, 집중률 기준 미만, 이동 여유 충분, 행사 없음, 운영 정보 없음.

    기본 상태에서 sample_plan 에 남는 문제는 토요일 감천문화마을(요일 규칙) 하나뿐이다.
    """
    values = {
        "now": at(9),
        "places": load_places(),
        "weather": hourly_weather(),
        "crowd": dict(BASE_CROWD),
        "hours": {},
        "travel_min": dict(BASE_TRAVEL_MIN),
        "events": [],
    }
    values.update(overrides)
    return CheckContext(**values)
