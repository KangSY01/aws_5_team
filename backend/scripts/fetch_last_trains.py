"""부산교통공사 열차시각표에서 지정 역·방향의 막차만 저장한다. backend/에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_last_trains
    uv run --env-file .env python -m scripts.fetch_last_trains --reuse-raw
    uv run python -m scripts.fetch_last_trains --offline

Haeundae·Dongbaek·Jung-dong에서는 Seomyeon 방향, Seomyeon에서는 Haeundae 방향을 평일·토요일·
일요일/공휴일별로 한 번씩 조회한다. 역 코드는 scripts/busan_stations.csv의 2호선 행에서 읽는다.
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

API_URL = "https://data.humetro.busan.kr/voc/api/open_api_process.tnn"
DATA_GO_KR_ID = "15000522"
TIMEOUT_SEC = 5
RETRIES = 1
DAY_CODES = {"1": "평일", "2": "토요일", "3": "일요일·공휴일"}
# 2호선 역번호가 작아지는 쪽이 상행(0, 장산 방향), 커지는 쪽이 하행(1, 양산 방향)이다.
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
    wanted = {route["station"] for route in ROUTES}
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


def _header(data: dict) -> dict:
    response = data.get("response")
    return response.get("header", {}) if isinstance(response, dict) else {}


def _check_response(data: dict) -> None:
    header = _header(data)
    code = str(header.get("resultCode", ""))
    message = str(header.get("resultMsg", ""))
    if code in {"00", "0000", "0"}:
        return
    upper = message.upper()
    if code in {"12", "401", "403"} or "NO OPENAPI SERVICE" in upper or "ACCESS DENIED" in upper:
        raise ApprovalError(f"열차시각표 API 활용 승인이 필요합니다 (resultCode={code or 'unknown'}).")
    raise FetchError(f"열차시각표 API 오류 (resultCode={code or 'unknown'}).")


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


def timetable_rows(data: Any) -> list[dict]:
    """응답 중 hour·time·scode·updown을 가진 시간표 행을 재귀적으로 찾는다."""
    found: list[dict] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if {"hour", "time", "scode", "updown"} <= value.keys():
                found.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return found


def _minutes(row: dict) -> int:
    try:
        hour = int(str(row["hour"]).strip())
        minute = int(str(row["time"]).strip())
    except (KeyError, TypeError, ValueError):
        raise FetchError("열차시각표 응답의 시·분 형식이 올바르지 않습니다.") from None
    if not 0 <= hour <= 47 or not 0 <= minute < 60:
        raise FetchError("열차시각표 응답의 시·분 범위가 올바르지 않습니다.")
    # 원본이 자정 뒤 막차를 00~03시로 주는 경우에도 같은 운행일의 24~27시로 비교한다.
    if hour < 4:
        hour += 24
    return hour * 60 + minute


def last_train_time(data: dict, params: dict[str, str]) -> str:
    """요청한 역·요일·방향 행 중 가장 늦은 시각을 HH:MM으로 돌려준다. 자정 뒤는 24시 이상을 유지한다."""
    _check_response(data)
    rows = [
        row for row in timetable_rows(data)
        if str(row.get("scode")) == params["scode"]
        and str(row.get("day")) == params["day"]
        and str(row.get("updown")) == params["updown"]
    ]
    if not rows:
        raise FetchError(
            f"시간표 행이 없습니다 (scode={params['scode']}, day={params['day']}, updown={params['updown']})."
        )
    total = max(_minutes(row) for row in rows)
    return f"{total // 60:02d}:{total % 60:02d}"


def collect(codes: dict[str, str]) -> dict:
    """대상 네 역의 세 요일 구분을 조회해 저장 형식을 만든다."""
    stations: dict[str, dict] = {}
    for route in ROUTES:
        station = route["station"]
        last_train: dict[str, str] = {}
        for day in DAY_CODES:
            params = {"scode": codes[station], "day": day, "updown": route["updown"], "act": "json"}
            raw_path = RAW_DIR / f"{codes[station]}_day{day}_updown{route['updown']}.json"
            last_train[day] = last_train_time(call_and_save(params, raw_path), params)
        stations[station] = {
            "scode": codes[station],
            "toward": route["toward"],
            "updown": int(route["updown"]),
            "last_train": last_train,
        }
    today = dt.datetime.fromisoformat(config.DEMO_NOW).date() if config.DEMO_NOW else dt.date.today()
    return {
        "source": {
            "provider": "부산교통공사",
            "api": API_URL,
            "data_go_kr_id": DATA_GO_KR_ID,
            "fetched_at": today.isoformat(),
            "day_codes": DAY_CODES,
            "note": "표준 열차 도착시각이며 실제 도착시각과 다를 수 있습니다.",
        },
        "stations": stations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부산 도시철도 지정 방향 막차 수집")
    parser.add_argument("--offline", action="store_true", help="API 없이 저장된 raw로 다시 만든다")
    parser.add_argument("--reuse-raw", action="store_true", help="같은 요청의 raw는 재사용하고 없는 요청만 호출한다")
    args = parser.parse_args(argv)
    global OFFLINE, REUSE_RAW
    OFFLINE, REUSE_RAW = args.offline, args.reuse_raw
    if not OFFLINE and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING이 비어 있습니다. backend/.env를 확인하세요.", file=sys.stderr)
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
    print(f"막차 {len(data['stations'])}역 × {len(DAY_CODES)}요일 구분 저장 ({OUT_PATH.name}), API 호출 {API_CALLS}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
