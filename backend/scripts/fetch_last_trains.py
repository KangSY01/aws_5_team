"""부산교통공사 열차시각표에서 지정 역·방향의 막차만 저장한다. backend/에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_last_trains
    uv run --env-file .env python -m scripts.fetch_last_trains --reuse-raw
    uv run python -m scripts.fetch_last_trains --offline
    uv run --env-file .env python -m scripts.fetch_last_trains --probe   # 1회만 호출해 응답 구조를 출력 (저장 없음)

공공데이터포털 「부산교통공사_부산도시철도 열차시각표 조회 서비스_GW」(apis.data.go.kr/B551542/trainTime)를 쓴다.
Haeundae·Dongbaek·Jung-dong에서는 Seomyeon 방향, Seomyeon에서는 Haeundae 방향의 막차를 평일·토요일·
일요일/공휴일별로 고른다. 역 코드는 scripts/busan_stations.csv의 2호선 행에서 읽는다.

응답에는 day·updown 요청 변수와 관계없이 모든 요일·방향이 섞여 오므로 역마다 시간 구간 두 개(22:00~23:59,
00:00~01:30)만 호출하고 코드에서 거른다. 호출 수는 역 4개 × 구간 2개 = 8회(페이지가 넘치면 추가)다.
목적지 전에 끝나는 열차(종착역 endcode 가 목적지에 못 미침)는 막차로 보지 않는다.
원본 응답은 app/data/raw/_last_trains/에 두고, app/data/last_trains.json에는 막차 시각만 저장한다.
"""

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from app import config

API_URL = "https://apis.data.go.kr/B551542/trainTime/getTrainTime"
SERVICE_NAME = "부산교통공사_부산도시철도 열차시각표 조회 서비스_GW"
NUM_OF_ROWS = 100
# 막차를 찾을 시간 구간 (stime, etime: 시분 4자리). 둘째 구간은 자정 뒤 열차 확인용이라 비어도 된다.
WINDOWS = (("2200", "2359"), ("0000", "0130"))
LINE = "2"
NO_DATA_CODES = {"03"}  # 공공데이터포털 NODATA. 빈 구간으로 본다
RESULT_MESSAGES = {
    "10": "잘못된 요청 파라미터입니다. scode·day·updown·stime·etime·enum 값을 확인하세요.",
    "20": "PERMISSION_DENIED: 활용 승인이 아직 반영되지 않았거나 서비스 키가 이 API의 키와 다릅니다.",
    "22": "호출 한도를 초과했습니다. 일일 트래픽이 초기화된 뒤 다시 실행하세요.",
}
APPROVAL_CODES = {"12", "20", "401", "403"}
TIMEOUT_SEC = 5
RETRIES = 1
DAY_CODES = {"1": "평일", "2": "토요일", "3": "일요일·공휴일"}
# 2호선 역번호가 작아지는 쪽이 상행(0, 장산 201 종착), 커지는 쪽이 하행(1, 양산 243 종착)이다.
ROUTES = (
    {"station": "Haeundae", "toward": "Seomyeon", "updown": "1"},
    {"station": "Dongbaek", "toward": "Seomyeon", "updown": "1"},
    {"station": "Jung-dong", "toward": "Seomyeon", "updown": "1"},
    {"station": "Seomyeon", "toward": "Haeundae", "updown": "0"},
)

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent / "app" / "data"
CSV_PATH = SCRIPTS_DIR / "busan_stations.csv"
RAW_DIR = DATA_DIR / "raw" / "_last_trains"
OUT_PATH = DATA_DIR / "last_trains.json"
API_CALLS = 0
OFFLINE = False
REUSE_RAW = False


class FetchError(Exception):
    """열차시각표를 받거나 해석하지 못했다."""


class ApprovalError(FetchError):
    """공공데이터포털 활용 승인이 없거나 서비스 키가 이 API에 등록되지 않았다."""


def load_station_codes(path: Path = CSV_PATH) -> dict[str, str]:
    """CSV의 2호선 행에서 대상 영문 역 이름별 역번호를 읽는다."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    wanted = {name for route in ROUTES for name in (route["station"], route["toward"])}  # 목적지 코드도 필요하다
    codes = {
        row["name_en"].strip(): row["역번호"].strip()
        for row in rows
        if row.get("name_en", "").strip() in wanted and row.get("노선번호", "").strip() == "S2602"
    }
    missing = sorted(wanted - set(codes))
    if missing:
        raise FetchError(f"busan_stations.csv의 2호선 행에 역이 없습니다: {', '.join(missing)}")
    if any(not code.isdigit() or len(code) != 3 for code in codes.values()):
        raise FetchError("busan_stations.csv의 대상 역번호가 세 자리 숫자가 아닙니다.")
    return codes


def request_params(scode: str, stime: str, etime: str, page: int = 1) -> dict[str, str]:
    """역·시간 구간·페이지 하나의 요청 변수 (serviceKey 제외). day·updown 은 응답에 영향이 없어 고정한다."""
    return {
        "pageNo": str(page), "numOfRows": str(NUM_OF_ROWS), "day": "1", "updown": "0",
        "stime": stime, "etime": etime, "enum": str(NUM_OF_ROWS), "act": "json", "scode": scode,
    }


def _header(data: Any) -> dict:
    """response.header 또는 최상위 header. 없으면 빈 dict."""
    if not isinstance(data, dict):
        return {}
    response = data.get("response")
    header = response.get("header") if isinstance(response, dict) else data.get("header")
    return header if isinstance(header, dict) else {}


def _check_response(data: dict) -> None:
    header = _header(data)
    code = str(header.get("resultCode", ""))
    message = str(header.get("resultMsg", ""))
    if code in {"00", "0000", "0"} or code in NO_DATA_CODES:
        return
    upper = message.upper()
    detail = RESULT_MESSAGES.get(code, "")
    if code in APPROVAL_CODES or "NO OPENAPI SERVICE" in upper or "ACCESS DENIED" in upper or "PERMISSION" in upper:
        raise ApprovalError(
            f"열차시각표 API 활용 승인이 필요합니다 (resultCode={code or 'unknown'}). {detail}".strip()
        )
    raise FetchError(f"열차시각표 API 오류 (resultCode={code or 'unknown'}). {detail}".strip())


def request_json(params: dict[str, str]) -> dict:
    """API를 호출한다. 401·403과 미승인 응답은 재시도하지 않고 ApprovalError로 구분한다."""
    query = {"serviceKey": config.DATA_GO_KR_KEY, **params}
    url = f"{API_URL}?{urllib.parse.urlencode(query)}"
    global API_CALLS
    reason = ""
    for _ in range(RETRIES + 1):
        API_CALLS += 1
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as response:
                data = json.loads(response.read().decode("utf-8"))
            _check_response(data)
            return data
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ApprovalError(f"열차시각표 API 활용 승인이 필요합니다 (HTTP {error.code}).") from None
            reason = f"HTTP {error.code}"
            if error.code < 500:
                break
        except ApprovalError:
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
            reason = type(error).__name__
    # URL에는 키가 있으므로 원래 예외와 URL을 메시지에 넣지 않는다.
    raise FetchError(f"열차시각표 API 호출 실패 ({reason or 'unexpected response'})")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FetchError(f"저장된 원본을 읽지 못했습니다: {path.name}") from error


def call_and_save(params: dict[str, str], raw_path: Path) -> dict:
    """같은 요청의 raw를 재사용하거나 한 번 호출해 키를 제외한 응답을 저장한다."""
    if OFFLINE or REUSE_RAW:
        saved = _load_json(raw_path) if raw_path.exists() else {}
        if saved.get("params") == params and isinstance(saved.get("response"), dict):
            _check_response(saved["response"])
            return saved["response"]
        if OFFLINE:
            raise FetchError(f"--offline: 같은 요청의 원본이 없습니다: {raw_path.name}")
    data = request_json(params)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps({"params": params, "response": data}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return data


def _body(data: Any) -> dict:
    """response.body 또는 최상위 body. 없으면 빈 dict."""
    if not isinstance(data, dict):
        return {}
    response = data.get("response")
    body = response.get("body") if isinstance(response, dict) else data.get("body")
    return body if isinstance(body, dict) else {}


def timetable_rows(data: Any) -> list[dict]:
    """body.items.item 의 시간표 행. item 이 dict 하나면 한 행으로, 결과가 없으면 빈 목록으로 돌려준다."""
    items = _body(data).get("items")
    item = items.get("item") if isinstance(items, dict) else None
    if isinstance(item, dict):
        item = [item]
    return [row for row in item if isinstance(row, dict)] if isinstance(item, list) else []


def total_count(data: Any) -> int:
    """body.totalCount. 없거나 숫자가 아니면 0."""
    try:
        return int(_body(data).get("totalCount") or 0)
    except (TypeError, ValueError):
        return 0


def _minutes(row: dict) -> int:
    """arrtime "HH:MM:SS" 를 분으로 바꾼다. 초는 버린다."""
    try:
        hour_text, minute_text = str(row["arrtime"]).strip().split(":")[:2]
        hour, minute = int(hour_text), int(minute_text)
    except (KeyError, TypeError, ValueError):
        raise FetchError("열차시각표 응답의 arrtime 형식이 올바르지 않습니다.") from None
    if not 0 <= hour <= 47 or not 0 <= minute < 60:
        raise FetchError("열차시각표 응답의 시·분 범위가 올바르지 않습니다.")
    # 원본이 자정 뒤 막차를 00~03시로 주는 경우에도 같은 운행일의 24~27시로 비교한다.
    if hour < 4:
        hour += 24
    return hour * 60 + minute


def _reaches(row: dict, updown: str, dest_code: str) -> bool:
    """종착역(endcode)이 목적지이거나 그 너머인 열차인지. 하행(1)은 역번호가 커지고 상행(0)은 작아진다."""
    try:
        end = int(str(row.get("endcode")).strip())
    except (TypeError, ValueError):
        return False
    return end >= int(dest_code) if updown == "1" else end <= int(dest_code)


def last_train_time(rows: list[dict], scode: str, day: str, updown: str, dest_code: str) -> str | None:
    """출발역·2호선·요일·방향이 맞고 목적지까지 가는 행 중 가장 늦은 시각(HH:MM). 없으면 None.

    자정 뒤는 24시 이상을 유지한다.
    """
    matched = [
        row for row in rows
        if str(row.get("scode", "")).strip() == scode
        and str(row.get("line", "")).strip() == LINE
        and str(row.get("dayType", "")).strip() == day
        and str(row.get("updown", "")).strip() == updown
        and _reaches(row, updown, dest_code)
    ]
    if not matched:
        return None
    total = max(_minutes(row) for row in matched)
    return f"{total // 60:02d}:{total % 60:02d}"


def fetch_station_rows(scode: str) -> list[dict]:
    """역 하나의 두 시간 구간을 페이지 끝까지 받아 행을 모은다. 요청 단위(역·구간·페이지)마다 raw 를 둔다."""
    rows: list[dict] = []
    for stime, etime in WINDOWS:
        page = 1
        while True:
            params = request_params(scode, stime, etime, page)
            data = call_and_save(params, RAW_DIR / f"{scode}_{stime}_{etime}_p{page}.json")
            page_rows = timetable_rows(data)
            rows += page_rows
            if not page_rows or page * NUM_OF_ROWS >= total_count(data):
                break
            page += 1
    return rows


def collect(codes: dict[str, str]) -> dict:
    """대상 네 역의 막차를 요일 구분별로 골라 저장 형식을 만든다. 조건에 맞는 행이 없는 요일은 넣지 않는다."""
    stations: dict[str, dict] = {}
    for route in ROUTES:
        station, toward, updown = route["station"], route["toward"], route["updown"]
        rows = fetch_station_rows(codes[station])
        last_train: dict[str, str] = {}
        for day in DAY_CODES:
            found = last_train_time(rows, codes[station], day, updown, codes[toward])
            if found is None:
                print(f"[경고] {station} → {toward} {DAY_CODES[day]}: 조건에 맞는 열차가 없어 값을 넣지 않습니다.",
                      file=sys.stderr)
            else:
                last_train[day] = found
        stations[station] = {
            "scode": codes[station],
            "toward": toward,
            "updown": int(updown),
            "last_train": last_train,
        }
    if not any(row["last_train"] for row in stations.values()):
        raise FetchError("막차를 하나도 찾지 못했습니다. --probe 로 응답 구조를 확인하세요.")
    today = dt.datetime.fromisoformat(config.DEMO_NOW).date() if config.DEMO_NOW else dt.date.today()
    return {
        "source": {
            "provider": "부산교통공사",
            "api": API_URL,
            "service": SERVICE_NAME,
            "fetched_at": today.isoformat(),
            "day_codes": DAY_CODES,
            "note": "표준 열차 도착시각이며 실제 도착시각과 다를 수 있습니다. 목적지 전에 끝나는 열차는 뺐습니다.",
        },
        "stations": stations,
    }


def _mask(text: str) -> str:
    """출력할 글에서 서비스 키(원문·URL 인코딩)를 가린다."""
    key = config.DATA_GO_KR_KEY
    for secret in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key), config.DATA_GO_KR_KEY_ENCODING}:
        if secret:
            text = text.replace(secret, "***")
    return text


def describe_structure(value: Any, name: str = "(root)", depth: int = 0) -> list[str]:
    """JSON 값의 키 이름·타입·리스트 길이를 들여쓰기한 줄 목록으로 만든다. 값 자체는 넣지 않는다."""
    pad = "  " * depth
    if isinstance(value, dict):
        lines = [f"{pad}{name}: dict ({len(value)} keys)"]
        for key, child in value.items():
            lines += describe_structure(child, str(key), depth + 1)
        return lines
    if isinstance(value, list):
        lines = [f"{pad}{name}: list (len {len(value)})"]
        if value:
            lines += describe_structure(value[0], "[0]", depth + 1)
        return lines
    return [f"{pad}{name}: {type(value).__name__}"]


def likely_rows(value: Any) -> list[dict]:
    """시간표 행으로 보이는 항목: 응답 안에서 dict 로만 이뤄진 가장 긴 리스트."""
    best: list[dict] = []
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            best = value
        children: list = value
    elif isinstance(value, dict):
        children = list(value.values())
    else:
        return best
    for child in children:
        found = likely_rows(child)
        if len(found) > len(best):
            best = found
    return best


def probe() -> int:
    """Haeundae 의 첫 시간 구간을 1회만 호출해 응답 구조를 출력한다. raw 와 last_trains.json 을 쓰지 않는다."""
    params = request_params(load_station_codes()["Haeundae"], *WINDOWS[0])
    print(f"요청: {API_URL}")
    print(f"요청 변수(serviceKey 제외): {json.dumps(params, ensure_ascii=False)}")
    url = f"{API_URL}?{urllib.parse.urlencode({'serviceKey': config.DATA_GO_KR_KEY, **params})}"
    global API_CALLS
    API_CALLS += 1
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read() if error.fp else b""
    except (urllib.error.URLError, TimeoutError) as error:
        # 예외 메시지에는 URL(키)이 들어갈 수 있어 종류만 출력한다.
        print(f"호출 실패: {type(error).__name__}")
        return 1
    text = body.decode("utf-8", errors="replace")
    print(f"HTTP {status}, {len(body)} bytes, API 호출 {API_CALLS}회")
    try:
        data = json.loads(text)
    except ValueError:
        print("JSON이 아닌 응답입니다. 앞 500자:")
        print(_mask(text[:500]))
        return 1

    header = _header(data)
    code = str(header.get("resultCode", ""))
    print(f"resultCode: {_mask(code) or '(없음)'}")
    print(f"resultMsg: {_mask(str(header.get('resultMsg', ''))) or '(없음)'}")
    if code in RESULT_MESSAGES:
        print(f"  → {RESULT_MESSAGES[code]}")
    print("키 구조:")
    for line in describe_structure(data):
        print(line)
    rows = likely_rows(data)
    print(f"시간표 행으로 보이는 항목: {len(rows)}개")
    shown = [("처음", rows[:3]), ("마지막", rows[-3:] if len(rows) > 3 else [])]
    for label, part in shown:
        for item in part:
            print(f"  [{label}] {_mask(json.dumps(item, ensure_ascii=False))}")
    if code in APPROVAL_CODES:
        return 3
    return 0 if code in {"00", "0000", "0"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부산 도시철도 지정 방향 막차 수집")
    parser.add_argument("--offline", action="store_true", help="API 없이 저장된 raw로 다시 만든다")
    parser.add_argument("--reuse-raw", action="store_true", help="같은 요청의 raw는 재사용하고 없는 요청만 호출한다")
    parser.add_argument("--probe", action="store_true", help="1회만 호출해 응답 구조를 출력한다 (저장하지 않는다)")
    args = parser.parse_args(argv)
    global OFFLINE, REUSE_RAW
    OFFLINE, REUSE_RAW = args.offline, args.reuse_raw
    if not OFFLINE and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING이 비어 있습니다. backend/.env를 확인하세요.", file=sys.stderr)
        return 1
    if args.probe:
        try:
            return probe()
        except FetchError as error:
            print(f"probe 실패: {error}", file=sys.stderr)
            return 1
    try:
        data = collect(load_station_codes())
    except ApprovalError as error:
        print(f"[중단] {error}", file=sys.stderr)
        print(f"API 호출 {API_CALLS}회", file=sys.stderr)
        return 3
    except FetchError as error:
        print(f"막차 수집 실패: {error}", file=sys.stderr)
        print(f"API 호출 {API_CALLS}회", file=sys.stderr)
        return 1

    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for station, row in data["stations"].items():
        values = ", ".join(f"{DAY_CODES[day]} {time}" for day, time in row["last_train"].items())
        print(f"{station} → {row['toward']}: {values}")
    saved = sum(len(row["last_train"]) for row in data["stations"].values())
    print(f"막차 {len(data['stations'])}역, 값 {saved}/{len(data['stations']) * len(DAY_CODES)}개 저장 ({OUT_PATH.name}), "
          f"API 호출 {API_CALLS}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
