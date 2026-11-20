"""조회 도구 (도구 담당). 장소 검색, 혼잡, 날씨, 운영시간.

반환 형식은 .kiro/specs/chat-agent/design.md 「조회 도구 반환 형식 (11/20 결정)」을 따른다.
필드 이름은 app/guardian/context.py 의 모델(HourlyWeather, OpeningHours)과 같다.

- 실패하면 예외를 던지지 않고 {"error": {"code": str, "message": str}} 를 돌려준다.
- config.USE_MOCK 이면 외부 API 를 부르지 않고 app/data/ 의 샘플을 쓴다.
- 외부 API 는 타임아웃 5초, 재시도 1회. serviceKey 는 로그와 오류 메시지에 남기지 않는다.
- 모르는 값(운영시간, 집중률)은 null·빈 목록으로 돌려준다. 지어내지 않는다.

TODO(도구 담당): 집중률 파일 읽기(_concentration), 운영시간 데이터, get_travel_time, get_events.
"""

import datetime as dt
import functools
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from strands import tool

from app import config
from app.guardian.thresholds import WEEKDAY_RULE_PLACES

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
KST = dt.timezone(dt.timedelta(hours=9))
TIMEOUT_SEC = 5
RETRIES = 1  # 첫 시도 외 재시도 횟수

# 기상청 단기예보 (.kiro/steering/data-rules.md)
KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BUSAN_GRID = {"nx": 98, "ny": 76}
KMA_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)  # 발표 시각. 발표 10분 후부터 조회할 수 있다
KMA_PUBLISH_DELAY_MIN = 10
KMA_MAX_DAYS_AHEAD = 4  # 이보다 먼 날짜는 호출하지 않고 "예보 없음". 범위 안이라도 응답에 없으면 빈 목록이 된다
KMA_ROWS = 1500  # 한 번에 받는다 (약 3일 × 24시간 × 12개 항목)


class LookupFailure(Exception):
    """도구가 오류 dict 로 돌려줄 사유."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _safe(func: Callable) -> Callable:
    """도구 본문의 실패를 {"error": {...}} 로 바꾼다. 예외를 밖으로 던지지 않는다."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except LookupFailure as e:
            return {"error": {"code": e.code, "message": e.message}}
        except Exception:  # 도구 하나의 버그가 대화 전체를 끊지 않게 한다
            logger.exception("%s 실패", func.__name__)
            return {"error": {"code": "internal_error", "message": f"{func.__name__} failed unexpectedly."}}

    return wrapper


# ---------- 공통 ----------

def _now() -> dt.datetime:
    """실제 현재 시각(KST). 실제 예보는 실제 시각 기준으로만 조회할 수 있어 DEMO_NOW 를 따르지 않는다."""
    return dt.datetime.now(KST)


def _load_json(name: str):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LookupFailure("data_unavailable", f"{name} could not be read.") from e


def _load_places() -> list[dict]:
    return _load_json("places.json")


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise LookupFailure("invalid_date", "date must be YYYY-MM-DD.") from None


def _require_place(place_id: str) -> None:
    if not any(p["place_id"] == place_id for p in _load_places()):
        raise LookupFailure(
            "place_not_found",
            f"place_id {place_id!r} is not a known place. Use a place_id from a search_places result.",
        )


def _get_json(url: str, params: dict) -> dict:
    """외부 API GET. 타임아웃 5초. 5xx·타임아웃·네트워크·형식 오류는 1회 재시도, 4xx 는 바로 실패."""
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    reason = ""
    for _ in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(full_url, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
            if e.code < 500:
                break
        except Exception as e:  # URL 에 serviceKey 가 있으므로 예외 메시지는 쓰지 않고 종류만 남긴다
            reason = type(e).__name__
    logger.warning("외부 API 호출 실패: %s (%s)", url, reason)
    raise LookupFailure("upstream_error", f"External API call failed ({reason}).")


# ---------- 혼잡 ----------

def _concentration(place_id: str, day: dt.date) -> float | None:
    """그 장소의 그 날짜 집중률(0~100). 데이터가 없으면 None.

    TODO(도구 담당, 다음 작업): app/data/ 의 집중률 파일을 읽는다. 지금은 파일이 없어 항상 None.
    """
    return None


# ---------- 날씨 ----------

def _sample_weather(day: dt.date) -> list[dict]:
    """USE_MOCK=1: app/data/sample_weather.json 의 그 날짜 예보. 없는 날짜는 빈 목록."""
    return _load_json("sample_weather.json").get("days", {}).get(day.isoformat(), [])


def latest_kma_base(now: dt.datetime) -> dt.datetime:
    """now 에 조회할 수 있는 가장 최근 단기예보 발표 시각."""
    t = now - dt.timedelta(minutes=KMA_PUBLISH_DELAY_MIN)
    hours = [h for h in KMA_BASE_HOURS if h <= t.hour]
    if not hours:  # 02:10 이전이면 전날 23시 발표분
        t -= dt.timedelta(days=1)
    return t.replace(hour=hours[-1] if hours else KMA_BASE_HOURS[-1], minute=0, second=0, microsecond=0)


def kma_to_hourly(data: dict, day: dt.date) -> list[dict]:
    """getVilageFcst 응답에서 그 날짜의 POP(강수확률)·PTY(강수 형태)를 시간별로 묶는다."""
    try:
        header = data["response"]["header"]
        if header["resultCode"] == "03":  # NO_DATA
            return []
        if header["resultCode"] != "00":
            raise LookupFailure("upstream_error", f"Weather API returned resultCode {header['resultCode']}.")
        ymd = day.strftime("%Y%m%d")
        by_time: dict[str, dict[str, int]] = {}
        for item in data["response"]["body"]["items"]["item"]:
            if item["fcstDate"] == ymd and item["category"] in ("POP", "PTY"):
                by_time.setdefault(item["fcstTime"], {})[item["category"]] = int(item["fcstValue"])
        return [
            {
                "time": dt.datetime.combine(day, dt.time(int(hhmm[:2]), int(hhmm[2:])), KST).isoformat(),
                "pop": values["POP"],
                "pty": values.get("PTY", 0),
            }
            for hhmm, values in sorted(by_time.items())
            if "POP" in values
        ]
    except (KeyError, TypeError, ValueError):
        raise LookupFailure("upstream_error", "Weather API returned an unexpected format.") from None


def _kma_weather(day: dt.date) -> list[dict]:
    """USE_MOCK=0: 기상청 단기예보를 호출한다. 예보 범위 밖 날짜는 호출하지 않고 빈 목록."""
    now = _now()
    if not 0 <= (day - now.date()).days <= KMA_MAX_DAYS_AHEAD:
        return []
    if not config.DATA_GO_KR_KEY:
        raise LookupFailure("missing_key", "DATA_GO_KR_KEY_DECODING is not set.")
    base = latest_kma_base(now)
    data = _get_json(KMA_URL, {
        "serviceKey": config.DATA_GO_KR_KEY,
        "pageNo": 1,
        "numOfRows": KMA_ROWS,
        "dataType": "JSON",
        "base_date": base.strftime("%Y%m%d"),
        "base_time": base.strftime("%H%M"),
        **BUSAN_GRID,
    })
    return kma_to_hourly(data, day)


# ---------- 도구 ----------

@tool
@_safe
def search_places(query: str, category: str | None = None, indoor: bool | None = None) -> list[dict] | dict:
    """부산 관광지를 찾는다. 일정에 넣을 장소나 교체 후보가 필요할 때, 장소의 place_id 를 알아야 할 때 쓴다.
    query 는 장소 이름의 일부다(영어·일본어·중국어 간체·번체 이름과 place_id 에서 대소문자 구분 없이 부분 일치).
    "비 올 때 갈 곳" 같은 조건은 query 를 "" 로 두고 category·indoor 로 좁힌다.
    결과에 없는 장소는 답변이나 일정에 쓰지 않는다.

    Args:
        query: 장소 이름의 일부 (예: "haeundae", "market", "市場", "博物"). "" 이면 이름으로 거르지 않는다.
        category: 장소 분류로 좁힐 때. beach, market, village, temple, park, observatory, museum, shopping,
            street, attraction, aquarium, culture, theme_park 중 하나. None 이면 전부.
        indoor: True 면 실내만, False 면 실외만, None 이면 전부.

    Returns:
        Place 형식 dict 목록. 각 항목은 place_id, names({"en", "ja", "zh-Hans", "zh-Hant"} 중 있는 언어만),
        lat, lng, category, indoor, nearest_station(없으면 null). 맞는 장소가 없으면 빈 목록.
        실패하면 {"error": {"code", "message"}}.
    """
    needle = (query or "").strip().casefold()
    wanted_category = (category or "").strip().casefold()
    found = []
    for place in _load_places():
        if wanted_category and place["category"].casefold() != wanted_category:
            continue
        if indoor is not None and place["indoor"] != indoor:
            continue
        if needle and not any(needle in text.casefold() for text in (place["place_id"], *place["names"].values())):
            continue
        found.append(place)
    return found


@tool
@_safe
def get_crowd(place_id: str, date: str) -> dict:
    """장소의 해당 날짜 혼잡 정도를 가져온다. 그 장소가 언제 붐비는지 확인할 때 쓴다.
    ratio 는 그 장소 자신의 가장 붐비는 시기를 100 으로 둔 상대값이다. 서로 다른 장소의 ratio 를 비교하면 안 된다.
    하루 단위 값이라 시간대별 혼잡은 알 수 없다.

    Args:
        place_id: 장소 ID (search_places 결과의 place_id)
        date: 날짜 (YYYY-MM-DD)

    Returns:
        {"place_id", "date", "ratio": 0~100 또는 null, "source": "concentration" | "weekday_rule"}.
        ratio 가 null 이고 source 가 "weekday_rule" 이면 집중률 데이터가 없는 장소다. 이때는 숫자를 말하지 말고
        요일로만 판단한다(평일 한산, 토요일 가장 붐빔, 일요일 붐빔).
        실패하면 {"error": {"code", "message"}} (invalid_date, place_not_found 등).
    """
    day = _parse_date(date)
    _require_place(place_id)
    ratio = None if place_id in WEEKDAY_RULE_PLACES else _concentration(place_id, day)
    return {
        "place_id": place_id,
        "date": day.isoformat(),
        "ratio": ratio,
        "source": "weekday_rule" if ratio is None else "concentration",
    }


@tool
@_safe
def get_weather(date: str) -> dict:
    """부산의 해당 날짜 시간별 예보(기상청 단기예보)를 가져온다. 비가 오는지, 실외 일정을 옮겨야 하는지 확인할 때 쓴다.
    예보는 오늘부터 약 3일 뒤까지만 있다. hourly 가 빈 목록이면 "아직 예보가 없다"고 답하고 날씨를 추측하지 않는다.

    Args:
        date: 날짜 (YYYY-MM-DD)

    Returns:
        {"date": "YYYY-MM-DD", "hourly": [{"time": ISO 시각(+09:00), "pop": 강수확률 0~100, "pty": 강수 형태}]}.
        pty 는 기상청 코드다: 0 없음, 1 비, 2 비/눈, 3 눈, 4 소나기. 예보가 없는 날짜는 hourly 가 빈 목록.
        실패하면 {"error": {"code", "message"}} (invalid_date, upstream_error 등).
    """
    day = _parse_date(date)
    hourly = _sample_weather(day) if config.USE_MOCK else _kma_weather(day)
    return {"date": day.isoformat(), "hourly": hourly}


@tool
@_safe
def get_hours(place_id: str) -> dict:
    """장소의 운영시간과 휴무일을 가져온다. 문을 여는 시간, 닫는 시간, 쉬는 날을 답하거나 일정 시각을 정할 때 쓴다.
    값이 null 이거나 빈 목록이면 모르는 것이다. 운영시간을 추측하지 말고 모른다고 답한다
    (현장 직원이나 1330 관광통역안내전화로 확인하도록 안내).

    Args:
        place_id: 장소 ID (search_places 결과의 place_id)

    Returns:
        {"place_id", "opens": "HH:MM" 또는 null, "closes": "HH:MM" 또는 null,
        "closed_weekdays": [0~6] (0=월 ... 6=일), "closed_dates": ["YYYY-MM-DD"]}.
        지금은 운영시간 데이터가 없어 모든 장소가 opens·closes null, 빈 목록이다.
        실패하면 {"error": {"code", "message"}} (place_not_found 등).
    """
    _require_place(place_id)
    # 운영시간 데이터를 아직 넣지 않았다. 모르는 값으로 돌려준다(지어내지 않는다).
    return {"place_id": place_id, "opens": None, "closes": None, "closed_weekdays": [], "closed_dates": []}
