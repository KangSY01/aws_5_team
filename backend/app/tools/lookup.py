"""조회 도구 (도구 담당). 장소 검색, 장소 정보(큐레이션), 혼잡, 날씨, 운영시간, 이동 시간, 행사.

반환 형식은 .kiro/specs/chat-agent/design.md 「조회 도구 반환 형식 (11/20 결정)」을 따른다.
필드 이름은 app/guardian/context.py 의 모델(HourlyWeather, OpeningHours, Event)과 같다.
Guardian 의 build_context 도 이 함수들을 그대로 부른다.

- 실패하면 예외를 던지지 않고 {"error": {"code": str, "message": str}} 를 돌려준다.
- config.USE_MOCK 이면 날씨는 외부 API 를 부르지 않고 app/data/weather/{날짜}.json 샘플을 쓴다.
- USE_MOCK=0 의 날씨는 DynamoDB 캐시(config.CACHE_TABLE)를 거친다. 60분 이내 값은 그대로 쓰고, 기상청 호출이
  실패하면 오래된 값이라도 돌려준다. DynamoDB 가 실패하면 캐시 없이 동작한다.
- 외부 API 는 타임아웃 5초, 재시도 1회. serviceKey 는 로그와 오류 메시지에 남기지 않는다.
- 모르는 값(운영시간, 집중률)은 null·빈 목록으로 돌려준다. 지어내지 않는다.
- 이동 시간(travel_times.json), 행사(events.json), 운영시간(hours.json), 큐레이션(curation.json),
  집중률(congestion.json)은 USE_MOCK 과 무관하게 app/data/ 의 파일을 읽는다.
  만드는 스크립트: scripts/build_travel_times.py, fetch_events.py, fetch_hours.py, build_curation.py, build_congestion.py
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

import boto3
from botocore.config import Config as BotocoreConfig
from strands import tool

from app import config

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

# 날씨 캐시 (DynamoDB config.CACHE_TABLE). 항목: pk="WEATHER#<날짜>", sk="KMA", hourly, fetched_at, base_time, ttl
WEATHER_CACHE_FRESH = dt.timedelta(minutes=60)  # 이 시간 안에 받은 값이 있으면 기상청을 부르지 않는다
WEATHER_CACHE_TTL = dt.timedelta(days=2)  # 항목의 ttl(유닉스 초) = fetched_at + 이 값. 지나면 DynamoDB 가 지운다
CACHE_TIMEOUT_SEC = 2  # 캐시는 없어도 되는 것이라 짧게 기다리고 재시도하지 않는다 (느린 DynamoDB 가 답변을 늦추지 않게)


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

    congestion.json(scripts/build_congestion.py 가 만든다)을 읽는다. 표에 없는 장소와 받아 둔 기간 밖의 날짜는 None.
    """
    return _load_json("congestion.json")["places"].get(place_id, {}).get(day.isoformat())


# ---------- 운영시간 ----------

def _hours(place_id: str) -> dict:
    """hours.json(scripts/fetch_hours.py 가 만든다)의 그 장소 값. 파일에 없는 장소는 모르는 값(지어내지 않는다)."""
    known = _load_json("hours.json")["hours"].get(place_id, {})
    return {
        "place_id": place_id,
        "opens": known.get("opens"),
        "closes": known.get("closes"),
        "closed_weekdays": known.get("closed_weekdays", []),
        "closed_dates": known.get("closed_dates", []),
        "raw_text": known.get("raw_text"),
    }


# ---------- 이동 시간 ----------

@functools.lru_cache(maxsize=4)
def _travel_table(path: Path) -> tuple[frozenset[str], dict[frozenset[str], dict]]:
    """travel_times.json → (표에 있는 장소 ID, {장소 쌍: 행}). 요청마다 여러 번 불리므로 한 번만 읽는다."""
    try:
        pairs = json.loads(path.read_text(encoding="utf-8"))["pairs"]
        table = {frozenset((p["from_place_id"], p["to_place_id"])): p for p in pairs}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise LookupFailure("data_unavailable", f"{path.name} could not be read.") from e
    return frozenset().union(*table), table


# ---------- 행사 ----------

SHORT_EVENT_MAX_DAYS = 7  # 첫날과 마지막 날을 포함한 일수. 이보다 긴 행사는 개막일만 행사일로 본다


def _event_kind_on(event: dict, day: dt.date) -> str | None:
    """그 날짜가 이 행사의 행사일이면 "short"(7일 이하 행사의 기간 중) 또는 "opening_day"(긴 행사의 개막일), 아니면 None.

    1년 내내 하는 상설 행사가 매일 혼잡 가중을 받지 않게 한다. events.json 에는 모든 행사가 그대로 있다.
    """
    start = dt.date.fromisoformat(event["start"][:10])  # 파일의 start·end 는 +09:00 ISO 시각
    end = dt.date.fromisoformat(event["end"][:10])
    if (end - start).days + 1 <= SHORT_EVENT_MAX_DAYS:
        return "short" if start <= day <= end else None
    return "opening_day" if day == start else None


# ---------- 날씨 ----------

def _sample_weather(day: dt.date) -> list[dict]:
    """USE_MOCK=1: app/data/weather/{YYYY-MM-DD}.json 샘플 예보의 hourly. 파일이 없는 날짜는 빈 목록.

    파일 형식은 get_weather 반환값과 같다({"date", "hourly"}). 같은 폴더의 이름 붙은 파일(rain-afternoon 등)은
    데모 스위치(demo.weather_preset)용이라 여기서 읽지 않는다.
    """
    name = f"weather/{day.isoformat()}.json"
    return _load_json(name).get("hourly", []) if (DATA_DIR / name).is_file() else []


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


def _kma_weather(day: dt.date, now: dt.datetime) -> tuple[list[dict], dt.datetime]:
    """기상청 단기예보를 호출한다. (그 날짜의 hourly, 조회한 발표 시각)을 돌려준다."""
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
    return kma_to_hourly(data, day), base


@functools.cache
def _cache_table():
    """캐시 테이블(boto3 Table). 처음 쓸 때 한 번 만든다 (speech/polly.py 와 같은 이유: 불러올 때 자격 증명을 찾지 않게)."""
    return boto3.resource(
        "dynamodb",
        region_name=config.BEDROCK_REGION,
        config=BotocoreConfig(
            connect_timeout=CACHE_TIMEOUT_SEC, read_timeout=CACHE_TIMEOUT_SEC, retries={"max_attempts": 0}
        ),
    ).Table(config.CACHE_TABLE)


def _weather_cache_key(day: dt.date) -> dict:
    return {"pk": f"WEATHER#{day.isoformat()}", "sk": "KMA"}


def _weather_cache_get(day: dt.date) -> tuple[list[dict], dt.datetime] | None:
    """캐시의 (hourly, 받은 시각). 없으면 None. DynamoDB 실패나 이상한 항목도 None 으로 본다 (예외를 올리지 않는다)."""
    try:
        item = _cache_table().get_item(Key=_weather_cache_key(day)).get("Item")
        if item is None:
            return None
        fetched_at = dt.datetime.fromisoformat(item["fetched_at"])
        if fetched_at.tzinfo is None:
            raise ValueError("fetched_at 에 시간대가 없다")
        # boto3 는 숫자를 Decimal 로 돌려준다. JSON 으로 나갈 수 있게 int 로 바꾼다
        hourly = [{"time": str(h["time"]), "pop": int(h["pop"]), "pty": int(h["pty"])} for h in item["hourly"]]
        return hourly, fetched_at
    except Exception as e:  # 캐시는 없어도 된다. 어떤 실패든 날씨 조회를 막지 않는다
        logger.warning("날씨 캐시를 읽지 못했습니다 (%s). 캐시 없이 진행합니다.", type(e).__name__)
        return None


def _weather_cache_put(day: dt.date, hourly: list[dict], base: dt.datetime, fetched_at: dt.datetime) -> None:
    try:
        _cache_table().put_item(Item={
            **_weather_cache_key(day),
            "hourly": hourly,
            "fetched_at": fetched_at.isoformat(),
            "base_time": base.isoformat(),
            "ttl": int((fetched_at + WEATHER_CACHE_TTL).timestamp()),
        })
    except Exception as e:
        logger.warning("날씨 캐시에 저장하지 못했습니다 (%s). 캐시 없이 진행합니다.", type(e).__name__)


def _cached_kma_weather(day: dt.date) -> tuple[list[dict], dict]:
    """USE_MOCK=0 의 날씨: (hourly, cache 정보 {"hit", "stale", "fetched_at"}).

    60분 이내 캐시 → 그대로. 아니면 기상청 호출 → 성공하면 저장. 기상청이 실패하면 오래된 캐시라도 돌려주고(stale),
    그것도 없으면 실패를 그대로 올린다. 예보 범위 밖 날짜는 기상청도 캐시도 부르지 않고 빈 목록이다.
    """
    now = _now()
    if not 0 <= (day - now.date()).days <= KMA_MAX_DAYS_AHEAD:
        return [], {"hit": False, "stale": False, "fetched_at": None}
    cached = _weather_cache_get(day)
    if cached and now - cached[1] <= WEATHER_CACHE_FRESH:
        return cached[0], {"hit": True, "stale": False, "fetched_at": cached[1].isoformat()}
    try:
        hourly, base = _kma_weather(day, now)
    except LookupFailure as e:
        if cached is None:
            raise
        logger.warning("기상청 호출 실패(%s). %s 에 받아 둔 캐시를 돌려줍니다.", e.code, cached[1].isoformat())
        return cached[0], {"hit": True, "stale": True, "fetched_at": cached[1].isoformat()}
    if hourly:  # 빈 응답(NO_DATA 등)으로 받아 둔 예보를 덮어쓰지 않는다
        _weather_cache_put(day, hourly, base, now)
    return hourly, {"hit": False, "stale": False, "fetched_at": now.isoformat()}


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
        ratio 가 null 이고 source 가 "weekday_rule" 이면 집중률 데이터가 없는 장소이거나, 받아 둔 기간(약 30일)
        밖의 날짜다. 이때는 숫자를 말하지 말고 요일로만 판단한다(평일 한산, 토요일 가장 붐빔, 일요일 붐빔).
        실패하면 {"error": {"code", "message"}} (invalid_date, place_not_found 등).
    """
    day = _parse_date(date)
    _require_place(place_id)
    ratio = _concentration(place_id, day)
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
        A live forecast also has "cache": {"hit": bool, "stale": bool, "fetched_at": ISO time or null}.
        If cache.stale is true the weather service could not be reached and this is an older forecast
        fetched at cache.fetched_at: say it may be out of date.
        실패하면 {"error": {"code", "message"}} (invalid_date, upstream_error 등).
    """
    day = _parse_date(date)
    if config.USE_MOCK:
        return {"date": day.isoformat(), "hourly": _sample_weather(day)}
    hourly, cache = _cached_kma_weather(day)
    return {"date": day.isoformat(), "hourly": hourly, "cache": cache}


@tool
@_safe
def get_hours(place_id: str) -> dict:
    """장소의 운영시간과 휴무일을 가져온다. 문을 여는 시간, 닫는 시간, 쉬는 날을 답하거나 일정 시각을 정할 때 쓴다.
    한국관광공사 소개정보(공공데이터)를 미리 받아 둔 값이다. opens·closes 는 원문이 단순한 한 구간일 때만 들어 있다.
    계절·요일별 시간, 입장 마감, "월요일이 공휴일이면 다음 날 휴관" 같은 예외는 raw_text(한국어 원문)에만 있으니
    raw_text 가 있으면 그 내용을 사용자의 언어로 옮겨 답한다.
    opens·closes 가 null 이고 raw_text 도 null 이면 모르는 것이다. 추측하지 말고 모른다고 답한다
    (현장 직원이나 1330 관광통역안내전화로 확인하도록 안내).

    Args:
        place_id: 장소 ID (search_places 결과의 place_id)

    Returns:
        {"place_id", "opens": "HH:MM" 또는 null, "closes": "HH:MM" 또는 null,
        "closed_weekdays": [0~6] (0=월 ... 6=일, 매주 쉬는 요일), "closed_dates": ["YYYY-MM-DD"],
        "raw_text": 이용시간·쉬는날 한국어 원문 또는 null}.
        실패하면 {"error": {"code", "message"}} (place_not_found 등).
    """
    _require_place(place_id)
    return _hours(place_id)


@tool
@_safe
def get_place_info(place_id: str) -> dict:
    """장소 한 곳의 기본 정보, 큐레이션, 운영시간을 한 번에 가져온다. 장소를 소개하거나, 붐비거나 비가 올 때
    대신 갈 곳을 고르거나, 운영시간을 답할 때 쓴다. search_places 와 get_hours 를 따로 부르지 않아도 된다.
    curation 은 규칙으로 만든 참고 값이다. crowd_alternatives·rain_alternatives 는 후보일 뿐이니
    그 장소의 실제 혼잡·날씨는 get_crowd·get_weather 로 확인한다.

    Args:
        place_id: 장소 ID (search_places 결과의 place_id)

    Returns:
        Place 필드(place_id, names, lat, lng, category, indoor, nearest_station)에 아래 둘을 더한 dict.
        "curation": {"tags": food, sea, history, culture, shopping, nature, night_view, kids, indoor 중 해당하는 것,
            "foreigner_friendly": 0~3 (한국관광공사 다국어 관광정보가 있는 언어 수: 영어·일본어·중국어.
                현장의 외국어 안내 수준을 뜻하지 않는다),
            "crowd_alternatives": 약 30분 이내이고 tags 가 겹치는 place_id 최대 3곳(가까운 순),
            "rain_alternatives": 약 30분 이내의 실내 place_id 최대 3곳(가까운 순),
            "source": "rule" | "manual"}. 큐레이션이 없는 장소는 null.
        "hours": get_hours 와 같은 값(opens, closes, closed_weekdays, closed_dates, raw_text). place_id 는 뺀다.
        실패하면 {"error": {"code", "message"}} (place_not_found 등).
    """
    place = next((p for p in _load_places() if p["place_id"] == place_id), None)
    if place is None:
        _require_place(place_id)  # place_not_found 오류를 같은 문구로 낸다
    hours = _hours(place_id)
    del hours["place_id"]
    return {**place, "curation": _load_json("curation.json").get(place_id), "hours": hours}


@tool
@_safe
def get_travel_time(from_place_id: str, to_place_id: str) -> dict:
    """두 장소 사이의 이동 시간(분)을 가져온다. 일정의 방문 시각을 정하거나, 다음 장소까지 얼마나 걸리는지 답할 때 쓴다.
    좌표로 계산한 추정값이다. 실제 경로 조회 결과가 아니므로 답변에서는 "약 N분"이라고 말하고 노선·환승은 말하지 않는다.
    추정 규칙: 경로 거리 = 직선거리 × 1.3. 1.2km 이하는 walk(시속 4.5km), 그보다 멀면 subway(평균 시속 25km +
    대기·환승 10분). 분은 올림. 방향을 바꿔도 값이 같다.

    Args:
        from_place_id: 출발 장소 ID (search_places 결과의 place_id)
        to_place_id: 도착 장소 ID (search_places 결과의 place_id)

    Returns:
        {"from_place_id", "to_place_id", "minutes": 정수(분), "mode": "walk" | "subway"}.
        같은 장소면 minutes 0, mode "walk".
        실패하면 {"error": {"code", "message"}}. 이동 시간 표에 없는 장소 ID 는 place_not_found.
    """
    known, table = _travel_table(DATA_DIR / "travel_times.json")
    for place_id in (from_place_id, to_place_id):
        if place_id not in known:
            raise LookupFailure(
                "place_not_found",
                f"place_id {place_id!r} is not in the travel time table. Use a place_id from a search_places result.",
            )
    if from_place_id == to_place_id:
        minutes, mode = 0, "walk"
    else:
        row = table.get(frozenset((from_place_id, to_place_id)))
        if row is None:
            raise LookupFailure("no_route", "No travel time for this pair of places.")
        minutes, mode = row["minutes"], row["mode"]
    return {"from_place_id": from_place_id, "to_place_id": to_place_id, "minutes": minutes, "mode": mode}


@tool
@_safe
def get_events(date: str) -> dict:
    """해당 날짜에 부산에서 열리는 축제·행사를 가져온다. 그날 갈 만한 행사를 찾거나, 행사 때문에 붐빌 장소를 확인할 때 쓴다.
    한국관광공사 행사정보(공공데이터)를 미리 받아 둔 목록이다. 목록에 없는 행사는 있다고 말하지 않는다.
    행사 이름은 한국어 원문이다.
    붐비는 날만 돌려준다: 기간이 7일 이하인 행사는 기간 내내, 7일보다 긴 행사는 개막일에만 나온다.
    그래서 결과에 없다고 해서 긴 행사가 그날 열리지 않는다는 뜻은 아니다.

    Args:
        date: 날짜 (YYYY-MM-DD)

    Returns:
        {"date": "YYYY-MM-DD", "events": [{"name": 행사 이름, "start": ISO 시각, "end": ISO 시각,
        "period_start": ISO 시각, "period_end": ISO 시각,
        "place_ids": [행사 장소 1km 이내의 장소 ID], "main_place_id": 장소 ID 또는 null,
        "kind": "short" | "opening_day"}]}.
        main_place_id is the event's main place: the place in place_ids closest to the event location,
        or null when place_ids is empty.
        kind 가 "short" 면 7일 이하 행사의 기간 중 하루, "opening_day" 면 7일보다 긴 행사의 개막일이다.
        start·end 는 요청한 날짜의 행사 시간대다(+09:00). 진행 시간을 아는 행사는 그 시간(예: 18:00~23:00),
        모르는 행사는 그날 00:00~23:59 로 나온다. 00:00~23:59 이면 진행 시간을 말하지 않는다.
        period_start·period_end 는 행사 전체 기간의 첫날과 마지막 날이다. 행사가 언제까지인지는 period_end 로 답한다.
        해당하는 행사가 없으면 events 가 빈 목록.
        실패하면 {"error": {"code", "message"}} (invalid_date, data_unavailable 등).
    """
    day = _parse_date(date)
    events = []
    for event in _load_json("events.json")["events"]:
        kind = _event_kind_on(event, day)
        if kind:
            # 파일의 start·end 는 기간 첫날·마지막 날이고, 시각 부분([10:])이 하루 중 시작·종료 시각이다
            # (모르면 00:00:00·23:59:59). 요청한 날짜에 그 시각을 붙여 그날의 시간대로 돌려준다.
            events.append({
                "name": event["name"],
                "start": day.isoformat() + event["start"][10:],
                "end": day.isoformat() + event["end"][10:],
                "period_start": event["start"],
                "period_end": event["end"],
                "place_ids": event["place_ids"],
                "main_place_id": event.get("main_place_id"),
                "kind": kind,
            })
    return {"date": day.isoformat(), "events": events}
