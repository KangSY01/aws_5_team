"""공공데이터(한국관광공사 TourAPI)로 places.json 을 다시 만든다. backend/ 에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_places
    uv run --env-file .env python -m scripts.fetch_places --stations scripts/busan_stations.csv
    uv run --env-file .env python -m scripts.fetch_places --baseline <예전 places.json>
    uv run python -m scripts.fetch_places --offline      (API 호출 없이 raw 응답으로 다시 만든다)
    uv run --env-file .env python -m scripts.fetch_places --reuse-raw --baseline <예전 places.json>
        (raw 에 같은 요청의 응답이 있으면 다시 부르지 않고, 없는 요청만 호출한다.
         시드에 장소·검색어를 더했을 때 쓴다. 끝에 실제 호출 수를 출력한다)

조회 방식
  국문   KorService2/searchKeyword2 로 좌표·contentid 를 얻는다.
  외국어 EngService2·JpnService2·ChsService2·ChtService2 의 locationBasedList2 에
         국문 좌표(mapX, mapY)와 radius=300 을 넣어 호출한다. 외국어 title 에는 한국어 원문이
         붙어 있다("海云台海水浴场(해운대해수욕장)"). title 에서 한글·숫자만 뽑아 이어 붙이고
         앞의 "부산" 을 뺀 값(normalize_korean)을 국문 title 도 같은 방식으로 만들어 비교한다.
           exact    : 값이 같음 (300m·1000m 모두)
           contains : 한쪽이 다른 쪽을 포함. 300m 이내이고 짧은 쪽이 3글자 이상일 때만
         일치 항목 중 exact 우선, 같은 종류끼리는 가까운 쪽을 고른다.
         names 에는 한국어를 모두 뺀 이름("海云台海水浴场")을 쓴다(strip_korean).
         300m 에 일치 항목이 없으면 radius=1000 으로 한 번 더 찾고, 그래도 없으면 그 언어만
         review 에 남긴다. contenttypeid 는 국문과 번호 체계가 달라서(쇼핑 국문 38, 영문 79) 거르지 않는다.
         키워드 보충: 위 방식이 no_korean_match 이고 기존 값이 없으며 시드 keywords.<언어> 가 있으면 그 언어 서비스의
         searchKeyword2 를 1회 호출해 국문 좌표 300m 이내에서 가장 가까운 title 을 쓴다(match_kind=keyword_en, keyword_ja).
  기존 장소 보호: --baseline 파일(기본 places.json)에 이미 값이 있는 언어는 exact 일치일 때만 덮어쓴다.
         contains·keyword_* 이면 기존 값을 유지하고, 값이 다르면 review 에 kept_existing 으로 남긴다.
         장소를 추가할 때는 기본값(places.json 자신)과 --reuse-raw 로 돌린다. 기존 이름이 그대로 유지된다.
         주의: 이때 keyword_* 와 backfill_names.py(areaBasedList2)로 찾은 이름의 출처가 places_sources.json 에서
         빠지므로, places_sources.json 은 기존 장소 항목을 실행 전 값으로 되돌리고 새 장소 항목만 더한다.
         수집 전 10곳짜리 파일(git show 83e285c^:backend/app/data/places.json)은 이름 보충(690f60a) 뒤로는 기준으로
         쓰지 않는다. 그 파일로 돌리면 보충한 이름이 빠지고 이름이 없어진 장소는 제외된다.
         place_id 는 시드 값을 그대로 쓴다(바꾸지 않는다).
  새 장소는 좌표 + 외국어 이름 1개 이상이면 places.json 에 넣는다. 빠진 언어는 review 에 남는다.
  review 사유  no_korean_match      반경 1000m 안에 일치하는 항목이 없음 (0건 포함)
               title_without_korean 후보는 있지만 한글이 하나도 없어 비교할 수 없음
               empty_name           일치했지만 한국어를 빼면 이름이 비어 있음
               kept_existing        exact 가 아닌 일치라서 기존 값을 유지함 (candidates 가 쓰지 않은 API 값)
               no_names             쓸 수 있는 외국어 이름이 하나도 없음
               api_error: ...       그 언어 호출이 실패함

입력
  scripts/place_seeds.json   [{place_id, name_ko, query, category, indoor, keywords{en, ja}, (선택) contentid, names}]
  scripts/busan_stations.csv 부산교통공사 역 좌표. 열 이름은 아래 _STATION_COLUMNS 의 별칭 중 하나.
출력
  app/data/places.json          Place 모델로 검증한 결과
  app/data/places_sources.json  장소별 출처(contentid, 국문 관광타입·분류 kor_class, API, 수집일)
  app/data/raw/<place_id>/      API 원본 응답 (serviceKey 는 저장하지 않는다)
  app/data/places_review.csv    사람이 골라야 하는 항목

사람이 고르는 방법: places_review.csv 의 후보를 보고 place_seeds.json 에
  "contentid": "<한국어 contentid>"  (한국어 후보 확정)
  "names": {"en": "...", "ja": "..."}  (언어별 이름 직접 지정)
를 적고 다시 실행한다.
"""
import argparse
import csv
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app import config
from app.models.plan import Place

BASE_URL = "https://apis.data.go.kr/B551011"
SERVICES = {
    "ko": "KorService2",
    "en": "EngService2",
    "ja": "JpnService2",
    "zh-Hans": "ChsService2",
    "zh-Hant": "ChtService2",
}
NAME_LANGS = ["en", "ja", "zh-Hans", "zh-Hant"]
MATCH_RADIUS_M = 300  # 한국어 좌표와 외국어 항목 좌표의 허용 거리
FALLBACK_RADIUS_M = 1000  # 300m 에 일치 항목이 없을 때 한 번 더 찾는 반경
MAX_STATION_M = 3000  # 이보다 멀면 nearest_station = None (기존 태종대처럼)
KEYWORD_ROWS = 300  # searchKeyword2 는 제목순이라 입점 매장이 많은 곳(아울렛 205건)도 한 번에 받는다
TIMEOUT_SEC = 5
RETRIES = 1  # 첫 시도 외 재시도 횟수
OFFLINE = False  # --offline: API 를 부르지 않고 raw 에 저장된 응답으로 다시 만든다
REUSE_RAW = False  # --reuse-raw: raw 에 같은 요청의 응답이 있으면 그것을 쓰고, 없는 요청만 호출한다
API_CALLS = 0  # 이번 실행에서 실제로 보낸 요청 수 (재시도 포함)

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent / "app" / "data"
RAW_DIR = DATA_DIR / "raw"
PLACES_PATH = DATA_DIR / "places.json"
SOURCES_PATH = DATA_DIR / "places_sources.json"
REVIEW_PATH = DATA_DIR / "places_review.csv"
SEEDS_PATH = SCRIPTS_DIR / "place_seeds.json"
STATIONS_PATH = SCRIPTS_DIR / "busan_stations.csv"

# 역 CSV 열 이름 별칭 (소문자 비교)
_STATION_COLUMNS = {
    "name": ["name_en", "역명(영문)", "영문역명", "station_en", "name", "역명", "station"],
    "lat": ["lat", "latitude", "위도"],
    "lng": ["lng", "lon", "longitude", "경도"],
}
REVIEW_FIELDS = ["place_id", "name_ko", "lang", "reason", "candidates"]
KOR_CLASS_KEYS = ("contenttypeid", "lclsSystm1", "lclsSystm2", "lclsSystm3")  # places_sources.json 의 kor_class


class FetchError(Exception):
    """API 호출 실패 (타임아웃, HTTP 오류, 응답 형식 오류)."""


# ---------- 순수 함수 ----------

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def parse_items(data: dict) -> list[dict]:
    """TourAPI 응답에서 후보 목록을 꺼낸다. 좌표가 없는 항목은 버린다.

    결과가 0건이면 items 가 빈 문자열, 1건이면 item 이 dict 로 오는 점을 처리한다.
    """
    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") not in ("0000", None):
        raise FetchError(f"resultCode={header.get('resultCode')} {header.get('resultMsg')}")
    items = data.get("response", {}).get("body", {}).get("items")
    if not items:
        return []
    raw = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(raw, dict):
        raw = [raw]
    result = []
    for it in raw:
        try:
            result.append({
                "contentid": str(it["contentid"]),
                "title": str(it.get("title", "")),
                "addr1": str(it.get("addr1", "")),
                "lat": float(it["mapy"]),
                "lng": float(it["mapx"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return result


def pick_kor(seed: dict, candidates: list[dict]) -> tuple[dict | None, str, list[dict]]:
    """한국어 후보 중 하나를 고른다. (선택, 실패 사유, 후보) 를 돌려준다.

    우선순위: 시드의 contentid 고정 > 후보 1개 > 제목이 시드 이름(name_ko) 또는 검색어(query)와 정확히 같은 후보 1개.
    """
    pinned = seed.get("contentid")
    if pinned:
        found = [c for c in candidates if c["contentid"] == str(pinned)]
        return (found[0], "", candidates) if found else (None, "pinned_contentid_not_in_results", candidates)
    if len(candidates) == 1:
        return candidates[0], "", candidates
    if not candidates:
        return None, "no_match", candidates
    keys = {_squash(seed["name_ko"]), _squash(seed.get("query") or seed["name_ko"])}
    exact = [c for c in candidates if _squash(c["title"]) in keys]
    if len(exact) == 1:
        return exact[0], "", candidates
    return None, "multiple_candidates", candidates


MIN_CONTAINS_LEN = 3  # 포함 일치를 인정하는 짧은 쪽의 최소 글자 수
_HANGUL_RE = re.compile(r"[가-힣]")
_KEEP_RE = re.compile(r"[가-힣0-9]+")
# 한글이 들어 있고 안에 다른 괄호가 없는 괄호 묶음. 반각·전각 모두. 앞 공백까지 함께 지운다.
_KOREAN_GROUP_RE = re.compile(r"\s*[(（][^()（）]*[가-힣][^()（）]*[)）]")
_EMPTY_GROUP_RE = re.compile(r"\s*[(（]\s*[)）]")


def normalize_korean(title: str) -> str:
    """비교용 한국어. title 에서 한글·숫자만 뽑아 이어 붙이고 앞의 "부산" 을 뺀다.

    공백과 괄호는 한글·숫자가 아니라서 저절로 빠진다. 국문·외국어 title 에 같은 방식으로 쓴다.
    """
    # ponytail: 로마자도 빠지므로 "LAP 롯데프리미엄아울렛 동부산점" 같은 로마자 브랜드 입점 매장이
    # 본점과 exact 로 보인다. 그런 오매칭이 나오면 괄호 안 한국어만 비교하도록 바꾼다.
    text = "".join(_KEEP_RE.findall(title))
    return text[2:] if text.startswith("부산") else text


def strip_korean(title: str) -> str:
    """외국어 title 에서 한국어 부분을 모두 뺀 이름. 한글이 든 괄호(반각·전각, 중첩 포함)와 괄호 밖 한글을 지운다."""
    text = title
    while True:  # 안쪽 괄호부터 바깥쪽으로
        replaced = _KOREAN_GROUP_RE.sub("", text)
        if replaced == text:
            break
        text = replaced
    text = _HANGUL_RE.sub("", text)
    text = _EMPTY_GROUP_RE.sub("", text)
    return " ".join(text.split())


def match_kind(kor_norm: str, foreign_norm: str, dist_m: float) -> str | None:
    """"exact"(정규화 값이 같음), "contains"(한쪽이 다른 쪽을 포함), 아니면 None.

    exact 는 거리와 상관없이 인정한다. contains 는 거리 MATCH_RADIUS_M 이내이고
    짧은 쪽이 MIN_CONTAINS_LEN 글자 이상일 때만 인정한다. 빈 값은 비교하지 않는다.
    """
    if not kor_norm or not foreign_norm:
        return None
    if kor_norm == foreign_norm:
        return "exact"
    short, long_ = sorted((kor_norm, foreign_norm), key=len)
    if dist_m <= MATCH_RADIUS_M and len(short) >= MIN_CONTAINS_LEN and short in long_:
        return "contains"
    return None


def pick_foreign(kor: dict, candidates: list[dict], radius: int = MATCH_RADIUS_M) -> tuple[dict | None, str, list[dict]]:
    """반경 안의 외국어 항목 중 국문 title 과 한국어가 일치하는 1곳을 고른다.

    (선택 항목, 실패 사유, 반경 안 후보) 를 돌려준다. 선택 항목에는 한국어를 뺀 "name" 과
    "match"("exact"/"contains") 가 들어 있다. 같은 일치 종류끼리는 가까운 쪽, exact 가 contains 보다 우선한다.
    타입(contenttypeid)으로는 거르지 않는다.
    실패 사유: title_without_korean(후보에 한글이 하나도 없어 비교 불가),
    empty_name(일치했지만 한국어를 빼면 이름이 비어 있음), no_korean_match(그 밖의 불일치·0건).
    """
    near = []
    for c in candidates:
        dist = haversine_m(kor["lat"], kor["lng"], c["lat"], c["lng"])
        if dist <= radius:
            near.append({**c, "dist_m": round(dist)})
    near.sort(key=lambda c: c["dist_m"])
    target = normalize_korean(kor["title"])
    matched, comparable = [], 0
    for c in near:
        norm = normalize_korean(c["title"])
        comparable += bool(norm)
        kind = match_kind(target, norm, c["dist_m"])
        if kind:
            matched.append({**c, "match": kind, "name": strip_korean(c["title"])})
    matched.sort(key=lambda c: (c["match"] != "exact", c["dist_m"]))
    named = [c for c in matched if c["name"]]
    if named:
        return named[0], "", near
    if matched:
        return None, "empty_name", near
    return None, ("title_without_korean" if near and not comparable else "no_korean_match"), near


def find_foreign_name(lang: str, kor: dict, raw_dir: Path) -> tuple[dict | None, str, list[dict], int]:
    """300m → (일치 없으면) 1000m 순으로 찾는다. (선택, 사유, 마지막 반경의 후보, 사용 반경)."""
    reason, near = "no_korean_match", []
    for radius in (MATCH_RADIUS_M, FALLBACK_RADIUS_M):
        suffix = "" if radius == MATCH_RADIUS_M else f"_r{radius}"
        cands = search_nearby(SERVICES[lang], kor["lat"], kor["lng"], raw_dir / f"{lang}{suffix}.json", radius)
        item, reason, near = pick_foreign(kor, cands, radius)
        if item:
            return item, "", near, radius
    return None, reason, near, FALLBACK_RADIUS_M


def pick_keyword(kor: dict, candidates: list[dict], lang: str = "en") -> dict | None:
    """외국어 키워드 검색 결과 중 국문 좌표 MATCH_RADIUS_M 이내에서 가장 가까운 항목. 없으면 None.

    가장 가까운 거리에 이름이 다른 항목이 둘 이상이면(아울렛 입점 매장처럼 좌표가 같은 경우)
    어느 것이 그 장소인지 알 수 없으므로 고르지 않는다.
    """
    near = []
    for c in candidates:
        dist = round(haversine_m(kor["lat"], kor["lng"], c["lat"], c["lng"]))
        name = strip_korean(c["title"])
        if dist <= MATCH_RADIUS_M and name:
            near.append({**c, "dist_m": dist, "match": f"keyword_{lang}", "name": name})
    if not near:
        return None
    best = min(c["dist_m"] for c in near)
    top = [c for c in near if c["dist_m"] == best]
    return top[0] if len({c["name"] for c in top}) == 1 else None


def dump_places(places: list[dict]) -> str:
    """places.json 본문. 원래 파일처럼 names 만 한 줄로 쓴다."""
    def one_line(m: re.Match) -> str:
        pairs = ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}"
                          for k, v in json.loads(m.group(1)).items())
        return f'"names": {{ {pairs} }}'

    text = json.dumps(places, ensure_ascii=False, indent=2)
    return re.sub(r'"names": (\{\n.*?\n    \})', one_line, text, flags=re.S) + "\n"


def nearest_station(lat: float, lng: float, stations: list[dict]) -> str | None:
    """가장 가까운 역 이름. MAX_STATION_M 보다 멀면 None."""
    best_name, best = None, float("inf")
    for s in stations:
        d = haversine_m(lat, lng, s["lat"], s["lng"])
        if d < best:
            best_name, best = s["name"], d
    return best_name if best <= MAX_STATION_M else None


def _squash(text: str) -> str:
    return "".join(text.split()).lower()


def _fmt_candidates(cands: list[dict]) -> str:
    return "; ".join(
        f"{c['contentid']}|{c['title']}|{c.get('dist_m', '')}m|{c.get('addr1', '')}" for c in cands
    )


def _today() -> str:
    """수집일. DEMO_NOW 가 있으면 그 날짜를 쓴다."""
    if config.DEMO_NOW:
        return datetime.fromisoformat(config.DEMO_NOW).date().isoformat()
    return date.today().isoformat()


# ---------- 입출력 ----------

def request_json(service: str, operation: str, extra: dict) -> dict:
    """TourAPI 호출. 타임아웃 5초. 5xx·타임아웃·네트워크·형식 오류는 1회 재시도한다.

    4xx(키 오류 등)는 재시도해도 같으므로 바로 실패시킨다. 키는 쿼리 파라미터로 넘긴다.
    """
    params = {
        "serviceKey": config.DATA_GO_KR_KEY,
        "MobileOS": "ETC",
        "MobileApp": "busan-guide",
        "_type": "json",
        "numOfRows": 20,
        "pageNo": 1,
        **extra,
    }
    url = f"{BASE_URL}/{service}/{operation}?{urllib.parse.urlencode(params)}"
    global API_CALLS
    reason = ""
    for _ in range(RETRIES + 1):
        API_CALLS += 1
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            reason = type(e).__name__
    # URL 에 키가 들어 있으므로 예외 메시지 대신 상태 코드나 종류만 남긴다
    raise FetchError(f"{service}/{operation} 호출 실패 ({reason})")


def _call_and_save(service: str, operation: str, extra: dict, raw_path: Path) -> list[dict]:
    """호출 후 원본 응답을 raw_path 에 저장하고 후보 목록을 돌려준다. serviceKey 는 저장하지 않는다.

    OFFLINE·REUSE_RAW 이면 raw_path 에 저장된 같은 요청의 응답을 다시 읽는다.
    같은 요청이 없으면 OFFLINE 은 실패하고, REUSE_RAW 는 호출한다.
    """
    if OFFLINE or REUSE_RAW:
        saved = load_json(raw_path, {})
        if (saved.get("service"), saved.get("operation"), saved.get("params")) == (service, operation, extra):
            return parse_items(saved["response"])
        if OFFLINE:
            raise FetchError(f"--offline: {raw_path.parent.name}/{raw_path.name} 에 같은 요청의 응답이 없습니다")
    data = request_json(service, operation, extra)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    saved = {"service": service, "operation": operation, "params": extra, "response": data}
    raw_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return parse_items(data)


def search_keyword(keyword: str, raw_path: Path, service: str = SERVICES["ko"]) -> list[dict]:
    """searchKeyword2. 기본은 국문 KorService2."""
    return _call_and_save(service, "searchKeyword2", {"keyword": keyword, "numOfRows": KEYWORD_ROWS}, raw_path)


def search_nearby(service: str, lat: float, lng: float, raw_path: Path, radius: int = MATCH_RADIUS_M) -> list[dict]:
    """외국어 서비스 locationBasedList2. 거리순(arrange=E)."""
    extra = {"mapX": lng, "mapY": lat, "radius": radius, "arrange": "E"}
    return _call_and_save(service, "locationBasedList2", extra, raw_path)


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_kor_item(place_id: str, contentid: str) -> dict:
    """raw/<place_id>/ko.json 에 저장된 국문 검색 응답에서 그 contentid 의 원본 항목. 없으면 빈 dict.

    parse_items 가 버리는 필드(contenttypeid, lclsSystm1~3)를 places_sources.json 의 kor_class 에 남길 때 쓴다.
    """
    saved = load_json(RAW_DIR / place_id / "ko.json", {})
    items = (saved.get("response", {}).get("response", {}).get("body", {}).get("items") or {}).get("item", [])
    items = [items] if isinstance(items, dict) else items
    return next((it for it in items if str(it.get("contentid")) == str(contentid)), {})


def load_stations(path: Path) -> list[dict]:
    """역 좌표 CSV 를 읽는다. UTF-8 이 아니면 CP949 로 다시 시도한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path} 인코딩을 읽을 수 없습니다")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ValueError(f"{path} 에 데이터가 없습니다")
    header = {h.strip().lower(): h for h in rows[0].keys()}
    cols = {}
    for field, aliases in _STATION_COLUMNS.items():
        hit = next((header[a.lower()] for a in aliases if a.lower() in header), None)
        if hit is None:
            raise ValueError(f"{path} 에 {field} 열이 없습니다 (가능한 이름: {aliases})")
        cols[field] = hit
    stations = []
    for r in rows:
        try:
            stations.append({
                "name": r[cols["name"]].strip(),
                "lat": float(r[cols["lat"]]),
                "lng": float(r[cols["lng"]]),
            })
        except (ValueError, TypeError):
            continue
    return stations


# ---------- 장소 한 곳 처리 ----------

def build_place(seed: dict, existing: dict | None, stations: list[dict], reviews: list[dict]) -> tuple[dict | None, dict | None]:
    """시드 한 곳을 처리해 (place dict, source dict) 를 돌려준다. 실패하면 기존 값을 유지한다."""
    pid = seed["place_id"]

    def review(lang: str, reason: str, cands: list[dict]) -> None:
        reviews.append({"place_id": pid, "name_ko": seed["name_ko"], "lang": lang,
                        "reason": reason, "candidates": _fmt_candidates(cands)})

    def keep_existing(reason: str) -> tuple[dict | None, dict | None]:
        review("ko", f"{reason} (기존 값 유지)" if existing else reason, [])
        return (existing, None) if existing else (None, None)

    category = seed.get("category") or (existing or {}).get("category")
    indoor = seed.get("indoor", (existing or {}).get("indoor"))
    if category is None or indoor is None:
        return keep_existing("missing_category_or_indoor")

    raw_dir = RAW_DIR / pid
    try:
        kor_cands = search_keyword(seed["query"], raw_dir / "ko.json")
    except FetchError as e:
        return keep_existing(f"api_error: {e}")
    kor_cands = [c for c in kor_cands if c["addr1"].startswith("부산")]
    kor, reason, cands = pick_kor(seed, kor_cands)
    if kor is None:
        review("ko", reason, cands)
        return (existing, None) if existing else (None, None)

    names: dict[str, str] = {}
    content_ids = {"ko": kor["contentid"]}
    radii: dict[str, int] = {}
    kinds: dict[str, str] = {}
    overrides = seed.get("names", {})
    old_names = (existing or {}).get("names", {})
    keywords = seed.get("keywords", {})
    for lang in NAME_LANGS:
        if lang in overrides:
            names[lang] = overrides[lang]
            continue
        old = old_names.get(lang)
        try:
            item, reason, near, radius = find_foreign_name(lang, kor, raw_dir)
            # 기존 값이 있으면 keyword_* 로는 덮어쓰지 않으므로 호출하지 않는다
            if item is None and reason == "no_korean_match" and keywords.get(lang) and old is None:
                found = search_keyword(keywords[lang], raw_dir / f"{lang}_keyword.json", SERVICES[lang])
                item = pick_keyword(kor, found, lang)
                radius = MATCH_RADIUS_M
        except FetchError as e:
            review(lang, f"api_error: {e}", [])
            continue
        if item is None:
            review(lang, reason, near)
            continue
        if old is not None and item["match"] != "exact":  # 기존 값 보호: exact 일 때만 덮어쓴다
            if item["name"] != old:
                review(lang, "kept_existing", [item])
            continue
        names[lang] = item["name"]
        content_ids[lang] = item["contentid"]
        radii[lang] = radius
        kinds[lang] = item["match"]

    # 못 찾은 언어는 기존 이름으로 채운다. 기존 값이 없으면 비워 둔다(review 에 이미 남아 있다).
    for lang in NAME_LANGS:
        if lang not in names and old_names.get(lang) is not None:
            names[lang] = old_names[lang]
    names = {lang: names[lang] for lang in NAME_LANGS if lang in names}  # 언어 순서 고정
    if not names:  # 최소 조건: 좌표 + 외국어 이름 1개 이상
        review("all", "no_names", [])
        return (existing, None) if existing else (None, None)

    candidate = {
        "place_id": pid,
        "names": names,
        "lat": kor["lat"],
        "lng": kor["lng"],
        "category": category,
        "indoor": indoor,
        # 기존 역 이름이 있으면 유지한다. 직선거리 계산은 실제 이용 역과 다를 수 있고(범어사 → Nopo),
        # 역 CSV(부산교통공사)에 없는 노선(동해선 OSIRIA)도 있다. 새로 계산하려면 --baseline 을 예전 파일로 준다.
        "nearest_station": (existing or {}).get("nearest_station") or nearest_station(kor["lat"], kor["lng"], stations),
    }
    try:
        place = Place.model_validate(candidate).model_dump()
    except ValidationError as e:
        review("all", f"validation_error: {e.error_count()}건", [])
        return (existing, None) if existing else (None, None)

    source = {
        "provider": "한국관광공사 TourAPI (공공데이터포털)",
        "apis": {lang: SERVICES[lang] for lang in content_ids},
        "contentids": content_ids,
        # 국문 항목의 관광타입·분류. raw 는 git 에 올리지 않으므로 fetch_hours·build_curation 은 이 값을 읽는다
        "kor_class": {key: load_kor_item(pid, kor["contentid"]).get(key) for key in KOR_CLASS_KEYS},
        "foreign_lookup": (f"locationBasedList2 radius={MATCH_RADIUS_M}m, 없으면 {FALLBACK_RADIUS_M}m. "
                           "title 의 한글·숫자 정규화 값이 국문과 같거나(exact), "
                           f"{MATCH_RADIUS_M}m 이내에서 {MIN_CONTAINS_LEN}글자 이상 포함(contains). "
                           f"그래도 없으면 searchKeyword2(시드 keywords.<언어>) {MATCH_RADIUS_M}m 이내 최근접(keyword_<언어>)"),
        "match_radius_m": radii,
        "match_kind": kinds,
        "names_overridden": sorted(overrides),
        "station_source": STATIONS_PATH.name,
        "fetched_at": _today(),
    }
    return place, source


# ---------- 실행 ----------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TourAPI 로 places.json 재생성")
    ap.add_argument("--seeds", type=Path, default=SEEDS_PATH)
    ap.add_argument("--stations", type=Path, default=STATIONS_PATH)
    ap.add_argument("--baseline", type=Path, default=PLACES_PATH,
                    help="기존 값 기준 파일. 여기 있는 이름은 exact 일치일 때만 덮어쓴다 (기본: places.json)")
    ap.add_argument("--offline", action="store_true",
                    help="API 를 부르지 않고 app/data/raw 에 저장된 응답으로 다시 만든다 (규칙만 바꿨을 때)")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="raw 에 같은 요청의 응답이 있으면 다시 부르지 않고, 없는 요청만 호출한다")
    args = ap.parse_args(argv)
    global OFFLINE, REUSE_RAW
    OFFLINE, REUSE_RAW = args.offline, args.reuse_raw

    if not OFFLINE and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING 이 비어 있습니다. backend/.env 를 확인하세요.", file=sys.stderr)
        return 1
    if not args.stations.exists():
        print(f"역 좌표 파일이 없습니다: {args.stations}", file=sys.stderr)
        return 1
    seeds = load_json(args.seeds, None)
    if not seeds:
        print(f"시드 파일이 없거나 비어 있습니다: {args.seeds}", file=sys.stderr)
        return 1
    stations = load_stations(args.stations)
    if args.baseline != PLACES_PATH and not args.baseline.exists():
        print(f"기준 파일이 없습니다: {args.baseline}", file=sys.stderr)
        return 1

    existing_list = load_json(args.baseline, [])
    existing = {p["place_id"]: p for p in existing_list}
    old_sources = load_json(SOURCES_PATH, {})
    reviews: list[dict] = []
    places: list[dict] = []
    sources: dict[str, dict] = {}

    for seed in seeds:
        calls_before = API_CALLS
        place, source = build_place(seed, existing.get(seed["place_id"]), stations, reviews)
        calls = API_CALLS - calls_before
        if source and not calls and seed["place_id"] in old_sources:  # 새로 받은 것이 없으면 수집일을 바꾸지 않는다
            source["fetched_at"] = old_sources[seed["place_id"]]["fetched_at"]
        status = "ok" if source else ("기존 유지" if place else "제외")
        print(f"[{status}] {seed['place_id']}" + (f" (API {calls}회)" if calls else ""))
        if place:
            places.append(place)
        if source:
            sources[seed["place_id"]] = source
        elif seed["place_id"] in old_sources:
            sources[seed["place_id"]] = old_sources[seed["place_id"]]

    seed_ids = {s["place_id"] for s in seeds}
    for pid, old in existing.items():  # 시드에 없는 기존 장소는 지우지 않는다
        if pid not in seed_ids:
            print(f"[경고] 시드에 없는 기존 장소를 유지합니다: {pid}")
            places.append(old)
            if pid in old_sources:
                sources[pid] = old_sources[pid]

    PLACES_PATH.write_text(dump_places(places), encoding="utf-8")
    SOURCES_PATH.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with REVIEW_PATH.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: 엑셀에서 한글이 깨지지 않게
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(reviews)

    print(f"places {len(places)}곳 저장, 검토 필요 {len(reviews)}건 ({REVIEW_PATH.name}), API 호출 {API_CALLS}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
