"""places.json 의 비어 있는 외국어 이름(en, ja, zh-Hans, zh-Hant)을 부산 전체 목록으로 채운다. backend/ 에서 실행한다.

    uv run --env-file .env python -m scripts.backfill_names                # 전체 실행 (실제 호출, 1회)
    uv run --env-file .env python -m scripts.backfill_names --reuse-raw    # 재실행: 저장된 쪽은 다시 부르지 않는다
    uv run python -m scripts.backfill_names --offline                      # 호출 0회, raw 만 사용

방식
  외국어 4개 서비스의 areaBasedList2(lDongRegnCd=26)를 관광 타입별로 모두 받아 raw/name_backfill/ 에 저장하고,
  빠진 언어만 fetch_places 의 일치 규칙(pick_foreign)으로 채운다. 일치 규칙은 다시 구현하지 않고 import 해서 쓴다.
  기존 이름·좌표·category·indoor·nearest_station·place_id 는 바꾸지 않고, 이름은 외국어 title 에서
  strip_korean 으로 얻은 값만 쓴다(번역하거나 만들지 않는다).

이 파일의 구성
  위쪽 「순수 함수」 구역은 파일·네트워크·환경 변수·현재 시각을 쓰지 않는다. 테스트는 이 구역을 직접 부른다.
  뒤쪽 입출력 구역에 수집, 복원, 파일 쓰기, 보고, main 이 있다.

종료 코드: 0 정상 / 1 일부 언어 실패·연결 스크립트 실패·검증 실패·쓰기 실패·curation_overrides 변경·Target_Types 불일치
          / 2 --offline 인데 raw 누락 / 3 호출 상한(MAX_CALLS) 중단.  2, 3, Target_Types 불일치는 데이터 파일을 쓰지 않는다.
"""
import argparse
import csv
import io
import json
import os
import sys
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from math import ceil, isfinite
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError

from app import config  # 키 값을 보고서에서 가리는 데만 쓴다
from app.models.plan import Place  # 공용 모델은 읽기만 한다 (fetch_places 와 같은 import 경로)
from scripts import fetch_places as fp
from scripts.fetch_events import festival_items as raw_items  # 응답의 원본 항목 목록 (0건·1건 형식 처리)
from scripts.fetch_places import (  # noqa: F401  일치 규칙은 fetch_places 것을 그대로 쓴다 (뒤 작업에서 사용)
    haversine_m,
    match_kind,
    normalize_korean,
    pick_foreign,
    strip_korean,
)

REGION_CODE = "26"  # 법정동 시도 코드: 부산광역시
AREA_ROWS = 100  # 한 쪽에 받는 건수 (fetch_restaurants 의 ROWS 와 같다)
MAX_PAGES = 50  # 무한 반복 방지. 넘으면 totalCount 경고(1.7)
EXPECTED_CALLS = 30  # 사전 추정 호출 수 (설계 「API 호출 수 추정과 상한」 표). 보고서에 같이 적는다
MAX_CALLS = 60  # 한 번의 실행에서 보낼 HTTP 요청 상한 (재시도 포함). EXPECTED_CALLS × 1.5
SEEDS_PATH = fp.SCRIPTS_DIR / "place_seeds.json"  # biff-square query 변경과 jeonpo-cafe-street 시드 추가를 저장
TARGET_TYPES = ("76", "78", "79", "75")  # 외국어 관광타입: 관광지, 문화시설, 쇼핑, 레포츠. 실행 중 1쪽 응답으로 검증한다
NAME_LANGS = fp.NAME_LANGS  # ["en", "ja", "zh-Hans", "zh-Hant"]
LANG_ORDER = ("ja", "en", "zh-Hans", "zh-Hant")  # 수집 순서. 데모에 가장 급한 ja 를 먼저 받아 상한으로 멈춰도 ja raw 는 남긴다
RAW_DIR = fp.RAW_DIR / "name_backfill"
# 읽고 쓰는 파일 경로. main 은 호출 시점에 이 모듈 상수를 읽으므로 테스트가 monkeypatch 로 임시 폴더로 돌릴 수 있다
PLACES_PATH = fp.PLACES_PATH
SOURCES_PATH = fp.SOURCES_PATH
REVIEW_PATH = fp.REVIEW_PATH
OVERRIDES_PATH = fp.DATA_DIR / "curation_overrides.json"  # 읽기만 한다 (7.6: 실행 전후로 같아야 한다)
STATIONS_CSV_PATH = fp.STATIONS_PATH  # 새 장소의 nearest_station 계산용 역 좌표
STATIONS_JSON_PATH = fp.DATA_DIR / "stations.json"  # 7.5 경고 확인용 (build_stations 가 만든다)
CONGESTION_PATH = fp.DATA_DIR / "congestion.json"  # 7.4 경고 확인용 (build_congestion 이 만든다)
RESTORE_SEEDS = {  # 복원 대상 시드 보정 (메모리에서 적용, 성공하면 seeds 파일에 저장)
    "biff-square": {"query": "BIFF 광장"},
    "jeonpo-cafe-street": {
        "place_id": "jeonpo-cafe-street",
        "name_ko": "전포카페거리",
        "query": "전포카페거리",
        "keywords": {"en": "Jeonpo Cafe Street"},
        "category": "street",
        "indoor": False,
    },
}


# ---------- 순수 함수 (네트워크·파일·환경 변수·현재 시각을 쓰지 않는다) ----------

@dataclass(frozen=True)
class FilledName:
    """이번에 채운 이름 한 건."""
    name: str  # strip_korean 결과
    contentid: str
    match: str  # "exact" | "contains"
    radius_m: int  # 300 | 1000
    dist_m: int


@dataclass(frozen=True)
class FillResult:
    """fill_names 의 결과."""
    names: dict[str, str]  # 기존 names + 이번에 채운 이름 (언어 순서는 NAME_LANGS)
    filled: dict[str, FilledName]  # 이번에 채운 언어만
    reviews: list[dict]  # 새 review 행 {place_id, name_ko, lang, reason, candidates}


def _has_text(value: object) -> bool:
    """None 이 아닌 문자열이고 공백만이 아니면 True."""
    return isinstance(value, str) and bool(value.strip())


def missing_langs(names: dict) -> list[str]:
    """names 에 없거나 값이 비어 있는(공백뿐인) 언어를 NAME_LANGS 순서로 돌려준다."""
    return [lang for lang in NAME_LANGS if not _has_text(names.get(lang))]


def _is_usable_candidate(cand: object) -> bool:
    """contentid·lat·lng 가 있고 title 이 공백뿐이 아닌 dict 후보인지."""
    if not isinstance(cand, dict):
        return False
    if cand.get("contentid") in (None, "") or not _has_text(cand.get("title")):
        return False
    for key in ("lat", "lng"):
        value = cand.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not isfinite(value):  # NaN, 무한대는 거리 계산에서 예외가 나므로 건너뛴다
            return False
    return True


def sanitize_candidates(cands: list) -> tuple[list[dict], list]:
    """후보 목록을 (쓸 수 있는 후보, 건너뛴 후보)로 나눈다. 각각 입력 순서를 유지한다.

    dict 가 아니거나, contentid·lat·lng 가 없거나, title 이 None·빈 문자열·공백뿐인 후보는 건너뛴다.
    입력이 목록이 아니거나 None 이면 둘 다 빈 목록이다. 예외를 올리지 않는다.
    """
    usable: list[dict] = []
    skipped: list = []
    if not isinstance(cands, (list, tuple)):
        return usable, skipped
    for cand in cands:
        (usable if _is_usable_candidate(cand) else skipped).append(cand)
    return usable, skipped


def plan_pages(total: int, rows: int) -> list[int]:
    """totalCount 와 쪽 크기로 받을 쪽 번호 목록을 만든다. 1부터 1씩 올라가며 최소 1쪽이다."""
    if rows <= 0:
        raise ValueError(f"쪽 크기는 1 이상이어야 합니다: {rows}")
    return list(range(1, max(1, ceil(max(total, 0) / rows)) + 1))


def check_budget(used: int, pending_calls: int, max_calls: int) -> str | None:
    """None 이면 진행, 문자열이면 중단 사유. 네트워크·파일을 쓰지 않는다."""
    if used + 2 > max_calls:  # 다음 호출 1회가 재시도까지 가도 상한 이내여야 한다
        return f"호출 상한 도달: {used}회 사용, 상한 {max_calls}회"
    if used + pending_calls > max_calls:  # 앞으로 반드시 필요한 호출만 더해도 상한을 넘는다
        return f"호출 상한 초과 예상: {used}회 사용 + 필요 {pending_calls}회 > 상한 {max_calls}회"
    return None


def count_names(places: list[dict]) -> dict[str, int]:
    """언어별로 이름이 있는(공백뿐이 아닌) 장소 수."""
    counts = {lang: 0 for lang in NAME_LANGS}
    for place in places:
        names = place.get("names") or {}
        for lang in NAME_LANGS:
            counts[lang] += _has_text(names.get(lang))
    return counts


def remaining_gaps(places: list[dict]) -> list[tuple[str, str]]:
    """이름이 비어 있는 (place_id, 언어) 쌍. 장소 순서, 언어는 NAME_LANGS 순서이고 중복은 없다."""
    gaps: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for place in places:
        for lang in missing_langs(place.get("names") or {}):
            pair = (place["place_id"], lang)
            if pair not in seen:
                seen.add(pair)
                gaps.append(pair)
    return gaps


def _contentid_key(cand: dict) -> tuple[int, int, str]:
    """contentid 오름차순 정렬 키. 숫자면 숫자 순서, 아니면 문자열 순서로 숫자 뒤에 둔다."""
    text = str(cand["contentid"])
    return (0, int(text), text) if text.isdigit() else (1, 0, text)


def _pick_two_stage(kor: dict, usable: list[dict]) -> tuple[dict | None, str, list[dict], int]:
    """반경 300m, 없으면 1000m 순서로 pick_foreign 을 부른다. (선택, 사유, 마지막 반경의 후보, 사용 반경)."""
    reason, near, radius = "no_korean_match", [], fp.MATCH_RADIUS_M
    for radius in (fp.MATCH_RADIUS_M, fp.FALLBACK_RADIUS_M):
        item, reason, near = pick_foreign(kor, usable, radius)
        if item:
            return item, "", near, radius
    return None, reason, near, radius


def _has_untitled_nearby(kor: dict, skipped: list, radius: int) -> bool:
    """건너뛴 후보 중 title 이 없고 좌표가 유효하며 반경 안에 있는 것이 있는지."""
    for cand in skipped:
        if not isinstance(cand, dict) or _has_text(cand.get("title")):
            continue
        lat, lng = cand.get("lat"), cand.get("lng")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (lat, lng)):
            continue
        if haversine_m(kor["lat"], kor["lng"], lat, lng) <= radius:
            return True
    return False


def _fail_reason(kor: dict, pick_reason: str, skipped: list) -> str:
    """못 채웠을 때의 review 사유. 이름을 얻을 수 없는 경우는 모두 empty_name 하나로 적는다."""
    if pick_reason in ("title_without_korean", "empty_name"):
        return "empty_name"
    if _has_untitled_nearby(kor, skipped, fp.FALLBACK_RADIUS_M):
        return "empty_name"
    return "no_korean_match"


def _ambiguity_reason(kor: dict, item: dict, near: list[dict]) -> str | None:
    """선택한 후보와 같은 일치 종류이면서 이름이 다른 후보가 있으면 사유를 돌려준다.

    거리(반올림 m)까지 같은 경쟁 후보가 있으면 distance_tie, 아니면 ambiguous_match, 경쟁 후보가 없으면 None.
    """
    target = normalize_korean(kor["title"])
    rivals = []
    for cand in near:
        name = strip_korean(cand["title"])
        kind = match_kind(target, normalize_korean(cand["title"]), cand["dist_m"])
        if kind == item["match"] and name and name != item["name"]:
            rivals.append(cand)
    if not rivals:
        return None
    return "distance_tie" if any(c["dist_m"] == item["dist_m"] for c in rivals) else "ambiguous_match"


def _review_row(place_id: str, name_ko: str, lang: str, reason: str, cands: list[dict]) -> dict:
    """review 행. candidates 는 fetch_places 와 같은 형식의 문자열이다."""
    return {"place_id": place_id, "name_ko": name_ko, "lang": lang,
            "reason": reason, "candidates": fp._fmt_candidates(cands)}


def _ordered_names(names: dict, added: dict[str, str]) -> dict[str, str]:
    """NAME_LANGS 순서로 정렬한 names. NAME_LANGS 밖의 기존 키는 원래 순서로 뒤에 둔다."""
    merged = {**names, **added}
    ordered = {lang: merged[lang] for lang in NAME_LANGS if lang in merged}
    ordered.update({key: value for key, value in names.items() if key not in ordered})
    return ordered


def fill_names(place_id: str, name_ko: str, kor: dict, names: dict[str, str],
               candidates: dict[str, list[dict]],
               known_reviews: frozenset[tuple[str, str]] = frozenset()) -> FillResult:
    """빠진 언어만 Area_List 후보에서 채운다. 기존 값은 그대로 둔다.

    kor: {"title", "lat", "lng"} 국문 기준. candidates: 언어 → parse_items 형식의 후보 목록
    (언어 키가 없으면 그 언어는 수집 실패라 건드리지 않는다).
    known_reviews 에 있는 (place_id, lang) 쌍에는 새 review 행을 만들지 않는다.
    """
    added: dict[str, str] = {}
    filled: dict[str, FilledName] = {}
    reviews: list[dict] = []

    def add_review(lang: str, reason: str, cands: list[dict]) -> None:
        if (place_id, lang) not in known_reviews:
            reviews.append(_review_row(place_id, name_ko, lang, reason, cands))

    for lang in missing_langs(names):
        if lang not in candidates:  # 수집 실패 언어는 건드리지 않는다
            continue
        usable, skipped = sanitize_candidates(candidates[lang])
        usable.sort(key=_contentid_key)  # 동률일 때 contentid 가 작은 쪽이 앞서도록 (pick_foreign 은 안정 정렬)
        item, reason, near, radius = _pick_two_stage(kor, usable)
        if item is None:
            add_review(lang, _fail_reason(kor, reason, skipped), near)
            continue
        added[lang] = item["name"]  # strip_korean 결과만 쓴다
        filled[lang] = FilledName(name=item["name"], contentid=str(item["contentid"]),
                                  match=item["match"], radius_m=radius, dist_m=item["dist_m"])
        ambiguity = _ambiguity_reason(kor, item, near)
        if ambiguity:  # 선택한 후보를 맨 앞에 두고 나머지를 거리순으로 붙인다
            rest = [c for c in near if c is not item and c["contentid"] != item["contentid"]]
            add_review(lang, ambiguity, [item, *rest])
    return FillResult(names=_ordered_names(names, added), filled=filled, reviews=reviews)


def apply_fill(place: dict, result: FillResult) -> dict:
    """장소 dict 에 채운 names 만 반영한 새 dict. names 외 필드는 그대로 둔다(입력은 바꾸지 않는다)."""
    return {**place, "names": dict(result.names)}


LINKED_STEPS_NEW_PLACE = ("build_travel_times", "build_curation", "build_congestion", "build_stations")  # 새 장소가 있을 때의 실행 순서
LINKED_STEPS_NAMES_ONLY = ("build_curation",)  # 이름만 채웠을 때: foreigner_friendly 가 names 언어 수에서 나온다


def plan_linked_steps(baseline_ids: Iterable[str], new_ids: Iterable[str], filled_count: int) -> list[str]:
    """실행할 연결 스크립트 이름 목록을 정한다. 네트워크·파일을 쓰지 않는다.

    baseline_ids: 실행 시작 시점의 place_id. new_ids: 병합 후 places.json 의 place_id.
    baseline 에 없던 ID 가 하나라도 있으면 4개를 정해진 순서로, 없고 채운 이름이 1개 이상이면 build_curation 하나,
    둘 다 없으면 빈 목록이다.
    """
    if set(new_ids) - set(baseline_ids):
        return list(LINKED_STEPS_NEW_PLACE)
    if filled_count > 0:
        return list(LINKED_STEPS_NAMES_ONLY)
    return []


def _step_failed(runner: Callable[[], object]) -> bool:
    """러너를 한 번 실행해 실패 여부를 돌려준다. 0이 아닌 반환값, 예외, 0이 아닌 SystemExit 은 실패다."""
    try:
        code = runner()
    except SystemExit as exc:  # 스크립트가 sys.exit 로 끝나는 경우도 실패 코드로 판단한다
        return exc.code not in (None, 0)
    except Exception:  # noqa: BLE001  어떤 예외든 실패로 처리하고 다음 단계는 실행하지 않는다
        return True
    return code not in (None, 0)  # main() 이 int 를 돌려준다. None 은 정상 종료로 본다


def run_chain(steps: list[str], runners: dict[str, Callable[[], object]]) -> tuple[list[str], str | None]:
    """steps 를 순서대로 실행하고 (실행한 목록, 실패한 이름 또는 None)을 돌려준다. 첫 실패에서 멈춘다.

    실행한 목록에는 실패한 단계도 들어간다. runners 에 없는 이름은 실패로 본다.
    """
    ran: list[str] = []
    for name in steps:
        ran.append(name)
        runner = runners.get(name)
        if runner is None or _step_failed(runner):
            return ran, name
    return ran, None


def _crlf(text: str) -> str:
    """줄바꿈을 CRLF로 통일한다. 이미 CRLF인 부분이 겹치지 않게 먼저 LF로 맞춘다."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def merge_sources(old: dict, updates: dict[str, dict[str, FilledName]]) -> dict:
    """기존 sources 에 이번에 채운 (place_id, 언어) 항목만 반영한 새 dict. 입력은 바꾸지 않는다.

    updates: place_id → {언어: FilledName}. 채운 쌍의 apis·contentids·match_kind·match_radius_m 만 쓰고
    그 밖의 모든 키와 값(다른 언어 항목, provider, kor_class 등)은 그대로 둔다.
    apis 값은 "JpnService2/areaBasedList2" 형식이라 locationBasedList2 로 찾은 항목(서비스 이름만 있음)과 구분된다.
    old 에 없는 place_id 는 위 4개 키만 가진 항목을 새로 만든다.
    """
    merged = deepcopy(old)
    for place_id, filled in updates.items():
        if not filled:
            continue
        entry = merged.setdefault(place_id, {})
        for lang, item in filled.items():
            entry.setdefault("apis", {})[lang] = f"{fp.SERVICES[lang]}/areaBasedList2"
            entry.setdefault("contentids", {})[lang] = item.contentid
            entry.setdefault("match_kind", {})[lang] = item.match
            entry.setdefault("match_radius_m", {})[lang] = item.radius_m
    return merged


def _is_api_error_row(row: dict) -> bool:
    """언어 전체 호출 실패 행(place_id="*", reason 이 api_error 로 시작)인지."""
    return row.get("place_id") == "*" and str(row.get("reason", "")).startswith("api_error")


def merge_review(old_rows: list[dict], filled_pairs: set[tuple[str, str]] | frozenset[tuple[str, str]],
                 new_rows: list[dict], api_ok_langs: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """기존 review 행에서 채운 쌍의 행과 낡은 api_error 행만 지우고, 새 행을 뒤에 붙인 목록.

    - filled_pairs 에 있는 (place_id, lang) 의 기존 행만 삭제한다.
    - api_ok_langs(이번에 수집에 성공한 언어)의 api_error 행(place_id="*")도 삭제한다.
    - 나머지 기존 행(kept_existing 등)은 내용과 상대 순서를 그대로 둔다. 새 행은 맨 뒤에 입력 순서로 붙인다.
    입력은 바꾸지 않는다.
    """
    kept = [dict(row) for row in old_rows
            if (row.get("place_id"), row.get("lang")) not in filled_pairs
            and not (_is_api_error_row(row) and row.get("lang") in api_ok_langs)]
    return kept + [dict(row) for row in new_rows]


def dump_sources(sources: dict) -> bytes:
    """places_sources.json 바이트. BOM 없는 UTF-8, 줄바꿈은 기존 파일처럼 CRLF."""
    return _crlf(json.dumps(sources, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def dump_review(rows: list[dict]) -> bytes:
    """places_review.csv 바이트. 엑셀 호환을 위해 BOM 이 있는 UTF-8(utf-8-sig), 줄바꿈은 CRLF."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fp.REVIEW_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def dump_places(places: list[dict]) -> bytes:
    """places.json 바이트. fp.dump_places 형식(names 한 줄)을 그대로 쓰고 BOM 없는 UTF-8, 줄바꿈만 CRLF로 바꾼다."""
    return _crlf(fp.dump_places(places)).encode("utf-8")


# ---------- 입출력: 수집과 호출 수 관리 (네트워크·파일을 쓴다) ----------

class CollectAborted(Exception):
    """수집을 그 자리에서 멈추고 아무것도 쓰지 않아야 하는 오류의 부모.

    area: 멈추기 전까지 모은 그 언어의 결과, collection: 지금까지 모은 전체 결과 (collect_area_lists 가 채운다).
    보고서에 확인 근거와 경고를 남기는 데 쓴다.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.area: "AreaList | None" = None
        self.collection: "Collection | None" = None


class BudgetExceeded(CollectAborted):
    """호출 상한(MAX_CALLS)에 닿았거나 닿을 것으로 예상되어 멈춘다. 종료 코드 3."""

    def __init__(self, reason: str, lang: str, type_id: str, page: int):
        self.reason, self.lang, self.type_id, self.page = reason, lang, type_id, page
        super().__init__(f"{reason} (멈춘 위치: {lang}, 타입 {type_id}, 쪽 {page})")


class TargetTypeMismatch(CollectAborted):
    """1쪽 응답의 contenttypeid 가 요청한 타입 번호와 다르다. 이후 호출을 시작하지 않고 종료 코드 1."""

    def __init__(self, check: "TypeCheck"):
        self.check = check
        super().__init__(f"{check.lang} 타입 {check.type_id}: 응답의 contenttypeid {list(check.observed_types)} 가 요청한 번호와 다릅니다")


@dataclass(frozen=True)
class TypeCheck:
    """Target_Types 번호를 1쪽 응답의 contenttypeid 로 확인한 결과 (Fill_Report 의 확인 근거)."""
    lang: str
    type_id: str
    observed_types: tuple[str, ...]  # 응답 항목에서 본 contenttypeid (중복 없음, 정렬)
    ok: bool | None  # True 일치, False 불일치, None 확인 불가(0건이거나 항목에 contenttypeid 가 없음)
    item_count: int  # 1쪽 응답의 원본 항목 수
    source: str  # 확인에 쓴 raw 파일 이름


@dataclass
class AreaList:
    """한 언어의 Area_List 수집 결과. fetch_area_list 가 채운다. 도중에 오류가 나도 그때까지의 값이 남는다."""
    lang: str
    candidates: list[dict] = field(default_factory=list)  # parse_items 형식, 모든 타입·쪽을 이어 붙인 것
    type_checks: list[TypeCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # --offline 에서 raw 가 없어 못 읽은 요청 (서비스·작업·쪽·파일 경로)


@dataclass
class Collection:
    """collect_area_lists 의 결과."""
    areas: dict[str, AreaList] = field(default_factory=dict)  # 끝까지 받은 언어만 (LANG_ORDER 순서)
    failed: dict[str, str] = field(default_factory=dict)  # 호출이 실패한 언어 → 사유 (api_error 행의 재료, 키 값 없음)
    type_checks: list[TypeCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_raw: list[str] = field(default_factory=list)  # --offline 에서 모은 누락 요청

    @property
    def candidates(self) -> dict[str, list[dict]]:
        """fill_names 에 넘길 언어 → 후보 목록. 수집에 실패했거나 누락이 있는 언어는 키가 없다."""
        return {lang: area.candidates for lang, area in self.areas.items()}

    def _absorb(self, area: AreaList) -> None:
        self.type_checks += area.type_checks
        self.warnings += area.warnings


class CallLog:
    """이번 실행의 API 호출 수. fp.API_CALLS 의 증가량을 (서비스, 작업)별로 합산한다.

    _call_and_save 호출 전후의 차이로 세므로 저장된 raw 를 읽기만 한 호출은 0이고, 실패한 호출과 재시도는 센다.
    budget 은 같은 로그를 기준으로 상한을 점검한다.
    """

    def __init__(self, max_calls: int | None = None, extra_pending: int = 0):
        self.start = fp.API_CALLS  # 이번 실행을 시작한 시점의 누적 호출 수
        self.counts: dict[tuple[str, str], int] = {}
        self.budget = CallBudget(self, MAX_CALLS if max_calls is None else max_calls, extra_pending)

    @property
    def total(self) -> int:
        """(서비스, 작업)별 호출 수의 합계."""
        return sum(self.counts.values())

    def call(self, service: str, operation: str, extra: dict, raw_path: Path) -> list[dict]:
        """fp._call_and_save 를 부르고 보낸 요청 수를 센다. FetchError 가 나도 센 뒤에 그대로 올린다."""
        before = fp.API_CALLS
        try:
            return fp._call_and_save(service, operation, extra, raw_path)
        except ValueError as exc:  # 저장된 raw 가 JSON 이 아니다 (FetchError 는 ValueError 가 아니다)
            raise fp.FetchError(f"{raw_path.name} 을 읽을 수 없습니다 ({type(exc).__name__})") from exc
        finally:
            sent = fp.API_CALLS - before
            if sent:
                self.counts[(service, operation)] = self.counts.get((service, operation), 0) + sent


class CallBudget:
    """호출 상한 점검. 순수 함수 check_budget 에 이번 실행에서 보낸 요청 수를 넣어 부른다."""

    def __init__(self, log: CallLog, max_calls: int, extra_pending: int = 0):
        self.log = log
        self.max_calls = max_calls
        self.extra_pending = extra_pending  # 수집 밖에서 반드시 보낼 호출 수 (아직 보내지 않은 국문 조회 등). 보낼 때마다 호출자가 줄인다

    @property
    def used(self) -> int:
        """실행 시작 이후 실제로 보낸 HTTP 요청 수 (재시도 포함)."""
        return fp.API_CALLS - self.log.start

    def check(self, pending_calls: int) -> str | None:
        """None 이면 진행, 문자열이면 중단 사유."""
        return check_budget(self.used, pending_calls, self.max_calls)

    def require(self, pending_calls: int, lang: str, type_id: str, page: int) -> None:
        """상한을 넘으면 BudgetExceeded 를 올린다. (lang, type_id, page) 는 멈춘 위치다."""
        reason = self.check(pending_calls)
        if reason:
            raise BudgetExceeded(reason, lang, type_id, page)


class _Request(NamedTuple):
    service: str
    operation: str
    extra: dict
    raw_path: Path


def _area_request(lang: str, type_id: str, page: int) -> _Request:
    """Area_List 한 쪽의 요청과 raw 저장 위치 (raw/name_backfill/<lang>_t<type>_p<page>.json)."""
    extra = {"contentTypeId": type_id, "lDongRegnCd": REGION_CODE, "arrange": "C", "numOfRows": AREA_ROWS, "pageNo": page}
    return _Request(fp.SERVICES[lang], "areaBasedList2", extra, RAW_DIR / f"{lang}_t{type_id}_p{page}.json")


def _is_saved(req: _Request) -> bool:
    """raw 에 같은 요청(서비스, 작업, 파라미터)의 응답이 있는지. fp._call_and_save 의 재사용 조건과 같다."""
    try:
        saved = fp.load_json(req.raw_path, {})
    except (ValueError, OSError):
        return False
    return isinstance(saved, dict) and (saved.get("service"), saved.get("operation"), saved.get("params")) == (
        req.service, req.operation, req.extra)


def _load_response(raw_path: Path) -> dict:
    """저장된 raw 의 API 응답 본문."""
    try:
        saved = fp.load_json(raw_path, {})
    except (ValueError, OSError) as exc:
        raise fp.FetchError(f"{raw_path.name} 을 읽을 수 없습니다 ({type(exc).__name__})") from exc
    response = saved.get("response") if isinstance(saved, dict) else None
    if not isinstance(response, dict):
        raise fp.FetchError(f"{raw_path.name} 에 응답이 없습니다")
    return response


def _total_count(response: dict) -> int:
    """응답의 totalCount. 없거나 숫자가 아니면 0."""
    try:
        return max(int(response.get("response", {}).get("body", {}).get("totalCount") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _verify_type(lang: str, type_id: str, originals: list[dict], source: str) -> TypeCheck:
    """1쪽 응답 항목의 contenttypeid 가 모두 요청한 번호인지 확인한다. 0건이거나 값이 없으면 확인 불가."""
    seen = {str(it["contenttypeid"]) for it in originals
            if isinstance(it, dict) and it.get("contenttypeid") not in (None, "")}
    observed = tuple(sorted(seen))
    ok = None if not observed else (observed == (type_id,))
    return TypeCheck(lang=lang, type_id=type_id, observed_types=observed, ok=ok, item_count=len(originals), source=source)


def _required_calls(lang: str, type_id: str, pages_left: list[int], extra_pending: int = 0) -> int:
    """앞으로 반드시 보내야 하는 최소 호출 수. 저장된 쪽은 뺀다.

    현재 타입의 남은 쪽 + 같은 언어의 뒤 타입 1쪽씩 + 뒤 언어의 모든 타입 1쪽씩 + 수집 밖의 필수 호출.
    아직 모르는 타입의 쪽 수는 최소값 1로 센다.
    """
    types = tuple(TARGET_TYPES)
    pending = sum(not _is_saved(_area_request(lang, type_id, page)) for page in pages_left)
    pending += sum(not _is_saved(_area_request(lang, later, 1)) for later in types[types.index(type_id) + 1:])
    for later_lang in LANG_ORDER[LANG_ORDER.index(lang) + 1:]:
        pending += sum(not _is_saved(_area_request(later_lang, t, 1)) for t in types)
    return pending + extra_pending


def _warn(area: AreaList, message: str) -> None:
    """경고를 결과에 담고 출력한다."""
    area.warnings.append(message)
    print(f"[경고] {message}")


def _missing_text(req: _Request, page: int) -> str:
    return f"{req.service}/{req.operation} 쪽 {page}: {req.raw_path}"


def fetch_area_list(lang: str, log: CallLog, area: AreaList | None = None) -> AreaList:
    """한 언어의 부산 전체 목록(areaBasedList2, lDongRegnCd=26)을 Target_Types 별로 모두 받는다.

    타입마다 1쪽을 받아 totalCount 를 알고, plan_pages 가 정한 쪽까지 이어 받는다. 원본 응답은
    raw/name_backfill/<lang>_t<type>_p<page>.json 에 남는다(serviceKey 없음). 저장된 쪽은 HTTP 요청 없이 읽고
    상한 점검과 호출 수에서 뺀다. 1쪽 응답으로 contenttypeid 를 확인한다(별도 확인 호출 없음).

    area 를 넘기면 그 객체에 결과를 채운다(도중에 예외가 나도 그때까지의 확인 근거·경고가 남는다).
    FetchError 는 그대로 올린다(이미 저장한 raw 는 유지). TargetTypeMismatch·BudgetExceeded 는 이후 호출을 시작하지 않는다.
    --offline(fp.OFFLINE)에서 raw 가 없으면 호출하지 않고 area.missing 에 모은다. 1쪽이 없는 타입은 쪽 수를 몰라 거기서 넘어간다.
    """
    if lang not in LANG_ORDER:
        raise ValueError(f"지원하지 않는 언어입니다: {lang}")
    fp.REUSE_RAW = True  # 저장된 쪽은 다시 부르지 않는다(1.5, 8.7). 상한 계산이 이 동작을 전제로 한다
    area = area if area is not None else AreaList(lang)
    try:
        for type_id in tuple(TARGET_TYPES):
            _fetch_type(lang, type_id, log, area)
    except CollectAborted as exc:
        exc.area = area
        raise
    return area


def _fetch_type(lang: str, type_id: str, log: CallLog, area: AreaList) -> None:
    """한 타입의 모든 쪽을 받아 area 에 이어 붙인다."""
    pages, index, total, received, incomplete = [1], 0, 0, 0, False
    while index < len(pages):
        page = pages[index]
        req = _area_request(lang, type_id, page)
        if not _is_saved(req):
            if fp.OFFLINE:  # 호출하지 않고 누락만 모은다
                area.missing.append(_missing_text(req, page))
                incomplete = True
                if page == 1:
                    return  # 쪽 수를 알 수 없다
                index += 1
                continue
            pending = _required_calls(lang, type_id, pages[index:], log.budget.extra_pending)  # 이번 호출 포함
            log.budget.require(pending, lang, type_id, page)
        items = log.call(req.service, req.operation, req.extra, req.raw_path)
        response = _load_response(req.raw_path)
        originals = raw_items(response) or []
        received += len(originals)
        if page == 1:
            total = _total_count(response)
            check = _verify_type(lang, type_id, originals, req.raw_path.name)
            area.type_checks.append(check)
            if check.ok is False:
                raise TargetTypeMismatch(check)
            if check.ok is None:
                _warn(area, f"{lang} 타입 {type_id}: 1쪽 응답에서 contenttypeid 를 확인할 수 없습니다 (확인 불가, 항목 {len(originals)}건)")
            pages = plan_pages(total, AREA_ROWS)
            if len(pages) > MAX_PAGES:
                _warn(area, f"{lang} 타입 {type_id}: totalCount {total}건이 {MAX_PAGES}쪽({MAX_PAGES * AREA_ROWS}건)을 넘어 앞 {MAX_PAGES}쪽만 받습니다")
                pages = pages[:MAX_PAGES]
                incomplete = True
            if not fp.OFFLINE:  # 1쪽 응답 직후, 남은 필수 호출 수로 상한을 다시 점검한다
                pending = _required_calls(lang, type_id, pages[1:], log.budget.extra_pending)
                if pending:
                    log.budget.require(pending, lang, type_id, 2)
        area.candidates += items
        index += 1
    if not incomplete and received < total:
        _warn(area, f"{lang} 타입 {type_id}: totalCount {total}건보다 적게 받았습니다 (받은 건수 {received}건)")


def collect_area_lists(log: CallLog) -> Collection:
    """4개 언어를 LANG_ORDER(ja, en, zh-Hans, zh-Hant) 순으로 받는다.

    한 언어가 FetchError 면 그 언어만 failed 에 사유를 적고 다음 언어로 간다(받은 raw 는 그대로 둔다).
    일부 쪽만 받은 언어의 후보는 쓰지 않는다. --offline 에서 raw 가 없으면 missing_raw 에 모으고 그 언어도 후보에서 뺀다.
    TargetTypeMismatch·BudgetExceeded 는 그대로 올리되, exc.collection 에 그때까지의 결과를 담는다.
    """
    fp.REUSE_RAW = True
    collection = Collection()
    for lang in LANG_ORDER:
        area = AreaList(lang)
        failure: str | None = None
        try:
            fetch_area_list(lang, log, area)
        except fp.FetchError as exc:  # 키는 메시지에 없다 (request_json 이 상태 코드나 종류만 남긴다)
            failure = str(exc)
            collection.failed[lang] = failure
            print(f"[실패] {lang}: {failure}")
        except CollectAborted as exc:
            collection._absorb(area)
            exc.collection = collection
            raise
        collection._absorb(area)
        if failure is None:
            if area.missing:
                collection.missing_raw += area.missing
            else:
                collection.areas[lang] = area
    return collection


# ---------- 입출력: 국문 기준 읽기와 복원 대상 처리 ----------

BUSAN_ADDR_PREFIX = "부산"  # fetch_places.build_place 와 같은 주소 필터
RESTORE_ALWAYS_SEARCH = frozenset({"biff-square"})  # query 를 바꿔 반드시 국문 조회를 1회 하는 시드. 그 밖의 복원 대상은 ko.json 이 없을 때만 조회한다
RESTORE_REASONS = {"no_match": "no_candidate"}  # pick_kor 사유 → review 사유 (multiple_candidates 는 그대로 쓴다)


class SeedFixResult(NamedTuple):
    """apply_seed_fixes 의 결과."""
    seeds: list[dict]  # 보정한 새 시드 목록 (입력은 바꾸지 않는다)
    added: list[str]  # 새로 추가한 시드의 place_id
    changed: list[str]  # 값을 바꾼 기존 시드에 대한 설명 (보고서용)


class RestoreResolution(NamedTuple):
    """resolve_restore 의 결과."""
    kor: dict | None  # 정한 국문 후보 {contentid, title, addr1, lat, lng}. 정하지 못하면 None
    reviews: list[dict]  # 새 review 행 (정하지 못한 사유)
    error: str | None  # 호출 실패 사유 (종료 코드 1 대상). 실패가 아니면 None
    called: bool  # 이번에 국문 조회를 실제로 시도했는지 (저장된 ko.json 을 읽기만 했으면 False)


class NewPlace(NamedTuple):
    """build_new_place 의 결과."""
    place: dict | None  # Place 검증을 통과한 장소. 만들지 못하면 None
    source: dict | None  # places_sources.json 항목
    reviews: list[dict]  # 만들지 못한 사유


def _kor_raw_path(place_id: str, raw_root: Path | None) -> Path:
    """raw/<place_id>/ko.json 경로. 테스트에서 임시 폴더를 넘길 수 있다."""
    return (fp.RAW_DIR if raw_root is None else raw_root) / place_id / "ko.json"


def _read_saved_items(path: Path) -> list[dict] | None:
    """저장된 국문 응답(ko.json)의 후보 목록. 파일이 없거나 읽을 수 없으면 None. 국문 API는 부르지 않는다."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return fp.parse_items(saved["response"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, fp.FetchError):
        return None  # 없음, JSON 오류, 응답 형식 오류 모두 같게 다룬다


def load_kor(place_id: str, sources: dict, name_ko: str = "", reviews: list[dict] | None = None,
             raw_root: Path | None = None) -> dict | None:
    """저장된 국문 응답에서 장소의 국문 기준 {title, lat, lng} 를 읽는다. 국문 API는 부르지 않는다.

    sources(places_sources.json)의 contentids.ko 와 같은 contentid 의 항목을 raw/<place_id>/ko.json 에서 찾는다.
    파일 없음, JSON 오류, 항목 없음, title·좌표 없음이면 None 을 돌려주고 reviews 에 kor_raw_missing 행을 더한다.
    """
    kor = _find_kor(place_id, sources, raw_root)
    if kor is None and reviews is not None:
        reviews.append(_review_row(place_id, name_ko, "ko", "kor_raw_missing", []))
    return kor


def _find_kor(place_id: str, sources: dict, raw_root: Path | None) -> dict | None:
    try:
        contentid = sources[place_id]["contentids"]["ko"]
    except (KeyError, TypeError):
        return None
    if contentid in (None, ""):
        return None
    items = _read_saved_items(_kor_raw_path(place_id, raw_root))
    for item in items or []:
        if item["contentid"] == str(contentid):
            if not _is_usable_candidate(item):  # title 이 비었거나 좌표가 유한하지 않다
                return None
            return {"title": item["title"], "lat": item["lat"], "lng": item["lng"]}
    return None


def apply_seed_fixes(seeds: list[dict]) -> SeedFixResult:
    """메모리의 시드 목록에 복원용 보정을 적용한다. 파일은 읽거나 쓰지 않는다.

    - biff-square 의 query 를 RESTORE_SEEDS 값("BIFF 광장")으로 바꾼다. 시드가 없으면 만들지 않는다.
    - jeonpo-cafe-street 시드가 없으면 RESTORE_SEEDS 값(category="street", indoor=false)으로 끝에 추가한다.
    다른 시드는 그대로 두고 입력 목록도 바꾸지 않는다. 저장은 commit_files 가 맡는다.
    """
    fixed = deepcopy(seeds)
    added: list[str] = []
    changed: list[str] = []
    for seed in fixed:
        if seed.get("place_id") != "biff-square":
            continue
        new_query = RESTORE_SEEDS["biff-square"]["query"]
        if seed.get("query") != new_query:
            changed.append(f"biff-square: query {seed.get('query')!r} → {new_query!r}")
            seed["query"] = new_query
    if not any(seed.get("place_id") == "jeonpo-cafe-street" for seed in fixed):
        fixed.append(deepcopy(RESTORE_SEEDS["jeonpo-cafe-street"]))
        added.append("jeonpo-cafe-street")
    return SeedFixResult(fixed, added, changed)


def _fmt_restore_candidates(cands: list[dict]) -> str:
    """복원 대상 국문 후보를 review 에 적을 문자열로. 제목, 주소, 좌표를 담는다."""
    return "; ".join(f"{c['contentid']}|{c['title']}|{c['addr1']}|{c['lat']},{c['lng']}" for c in cands)


def _restore_review(seed: dict, reason: str, cands: list[dict]) -> dict:
    return {"place_id": seed["place_id"], "name_ko": seed["name_ko"], "lang": "ko",
            "reason": reason, "candidates": _fmt_restore_candidates(cands)}


def resolve_restore(seed: dict, log: CallLog | None = None, raw_root: Path | None = None) -> RestoreResolution:
    """복원 대상 시드의 국문 후보를 정한다.

    fp.search_keyword 와 같은 요청(searchKeyword2, 키워드는 시드 query)을 1회 보낸다. 재시도 1회와 타임아웃 5초는
    fp.request_json 이 지킨다. 결과에서 주소가 "부산"으로 시작하는 후보만 남겨 fp.pick_kor 로 하나를 정한다.
    - 0건은 no_candidate, 정할 수 없는 다수는 multiple_candidates, 호출 실패는 search_failed 로 review 에 남긴다.
    - RESTORE_ALWAYS_SEARCH 가 아닌 시드(jeonpo-cafe-street)는 raw/<place_id>/ko.json 이 있으면 조회하지 않고 그 파일을 읽는다.
    log 를 넘기면 호출 수와 상한을 같은 로그로 관리한다. BudgetExceeded 는 그대로 올린다.
    """
    place_id = seed["place_id"]
    raw_path = _kor_raw_path(place_id, raw_root)
    fp.REUSE_RAW = True  # 같은 요청이 저장돼 있으면 다시 부르지 않는다 (fetch_area_list 와 같다)
    if place_id not in RESTORE_ALWAYS_SEARCH and raw_path.exists():
        cands = _read_saved_items(raw_path)
        if cands is None:  # 파일은 있으나 읽을 수 없다. 이미 있는 raw 라 조회하지 않는다
            return RestoreResolution(None, [_review_row(place_id, seed["name_ko"], "ko", "kor_raw_missing", [])], None, False)
        called = False
    else:
        extra = {"keyword": seed["query"], "numOfRows": fp.KEYWORD_ROWS}
        request = _Request(fp.SERVICES["ko"], "searchKeyword2", extra, raw_path)
        try:
            if log is not None:
                if not fp.OFFLINE and not _is_saved(request):
                    log.budget.require(0, "ko", place_id, 1)  # 보내기 전에 상한을 점검한다
                cands = log.call(*request)
            else:
                cands = fp.search_keyword(seed["query"], raw_path)
        except (fp.FetchError, OSError) as exc:  # 재시도 후에도 실패. 키는 메시지에 없다
            reason = f"search_failed: {exc}"
            print(f"[실패] {place_id} 국문 조회: {reason}")
            return RestoreResolution(None, [_restore_review(seed, reason, [])], reason, True)
        called = True
    busan = [c for c in cands if c["addr1"].startswith(BUSAN_ADDR_PREFIX)]
    kor, reason, shown = fp.pick_kor(seed, busan)
    if kor is None:
        return RestoreResolution(None, [_restore_review(seed, RESTORE_REASONS.get(reason, reason), shown)], None, called)
    return RestoreResolution(kor, [], None, called)


def _load_kor_item(place_id: str, contentid: str, raw_root: Path | None) -> dict:
    """저장된 국문 응답에서 그 contentid 의 원본 항목. 없거나 읽을 수 없으면 빈 dict (fp.load_kor_item 과 같은 동작)."""
    try:
        saved = json.loads(_kor_raw_path(place_id, raw_root).read_text(encoding="utf-8"))
        items = (saved["response"]["response"]["body"].get("items") or {}).get("item", [])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}
    items = [items] if isinstance(items, dict) else items
    return next((it for it in items if isinstance(it, dict) and str(it.get("contentid")) == str(contentid)), {})


def _new_place_review(seed: dict, lang: str, reason: str) -> dict:
    return {"place_id": seed["place_id"], "name_ko": seed["name_ko"], "lang": lang, "reason": reason, "candidates": ""}


def build_new_place(seed: dict, kor: dict, result: FillResult, stations: list[dict],
                    raw_root: Path | None = None) -> NewPlace:
    """복원 대상의 새 장소와 sources 항목을 만든다. 조건이 안 되면 장소를 만들지 않고 review 행만 돌려준다.

    kor: resolve_restore 가 정한 국문 후보 {contentid, title, lat, lng, ...}. result: fill_names(…, names={}) 의 결과.
    - category 또는 indoor 가 시드에 없으면 missing_category_or_indoor.
    - 국문 좌표가 없으면 kor_raw_missing, 외국어 이름이 0개면 no_name_found. 좌표가 있고 이름이 1개 이상일 때만 만든다.
    - Place.model_validate 로 검증하고 실패하면 validation_error 행. nearest_station 은 fp.nearest_station 으로 계산한다.
    place_id 는 시드 값 그대로다. places.json 끝에 붙이는 일은 append_new_places 가 한다.
    """
    place_id = seed["place_id"]
    category, indoor = seed.get("category"), seed.get("indoor")
    if category is None or indoor is None:
        return NewPlace(None, None, [_new_place_review(seed, "ko", "missing_category_or_indoor")])
    lat, lng = kor.get("lat"), kor.get("lng")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (lat, lng)):
        return NewPlace(None, None, [_new_place_review(seed, "ko", "kor_raw_missing")])
    names = {lang: name for lang, name in result.names.items() if lang in NAME_LANGS and _has_text(name)}
    if not names:
        return NewPlace(None, None, [_new_place_review(seed, "all", "no_name_found")])
    candidate = {
        "place_id": place_id,
        "names": {lang: names[lang] for lang in NAME_LANGS if lang in names},  # 언어 순서 고정
        "lat": lat,
        "lng": lng,
        "category": category,
        "indoor": indoor,
        "nearest_station": fp.nearest_station(lat, lng, stations),
    }
    try:
        place = Place.model_validate(candidate).model_dump()
    except ValidationError as exc:
        return NewPlace(None, None, [_new_place_review(seed, "all", f"validation_error: {exc.error_count()}건")])
    contentid = str(kor["contentid"])
    base = {  # fetch_places.build_place 가 만드는 항목과 같은 키 순서. 외국어 항목은 merge_sources 가 채운다
        "provider": "한국관광공사 TourAPI (공공데이터포털)",
        "apis": {"ko": fp.SERVICES["ko"]},
        "contentids": {"ko": contentid},
        "kor_class": {key: _load_kor_item(place_id, contentid, raw_root).get(key) for key in fp.KOR_CLASS_KEYS},
        "foreign_lookup": (f"areaBasedList2 lDongRegnCd={REGION_CODE} 부산 전체 목록, 반경 {fp.MATCH_RADIUS_M}m, 없으면 {fp.FALLBACK_RADIUS_M}m. "
                           "title 의 한글·숫자 정규화 값이 국문과 같거나(exact), "
                           f"{fp.MATCH_RADIUS_M}m 이내에서 {fp.MIN_CONTAINS_LEN}글자 이상 포함(contains)"),
        "match_radius_m": {},
        "match_kind": {},
        "names_overridden": [],
        "station_source": fp.STATIONS_PATH.name,
        "fetched_at": fp._today(),
    }
    filled = {lang: item for lang, item in result.filled.items() if lang in names}
    source = merge_sources({place_id: base}, {place_id: filled})[place_id]
    return NewPlace(place, source, [])


def append_new_places(places: list[dict], new_places: list[dict]) -> list[dict]:
    """기존 장소 순서를 그대로 두고 새 장소를 끝에 붙인 새 목록. 이미 있는 place_id 는 붙이지 않는다."""
    existing = {place["place_id"] for place in places}
    return [*places, *(place for place in new_places if place["place_id"] not in existing)]


# ---------- 입출력: 파일 쓰기 (D8) ----------

class CommitError(OSError):
    """commit_files 가 파일을 쓰다 실패했다. 이미 교체한 파일은 원본 바이트로 되돌린 뒤에 올린다. 종료 코드 1."""

    def __init__(self, message: str, restore_failed: list[Path] | None = None):
        super().__init__(message)
        self.restore_failed = restore_failed or []  # 되돌리기까지 실패한 경로 (정상이면 빈 목록)


def _temp_path(path: Path) -> Path:
    """같은 폴더의 임시 파일 경로. 같은 볼륨이라 os.replace 가 원자적으로 동작한다."""
    return path.with_name(f".{path.name}.tmp")


def _remove_quietly(path: Path) -> None:
    """임시 파일 정리. 이미 없거나 지울 수 없어도 원래 오류를 가리지 않는다."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _restore_original(path: Path, original: bytes | None) -> bool:
    """교체한 파일을 메모리에 둔 원본 바이트로 되돌린다. 원래 없던 파일이면 지운다. 성공하면 True.

    os.replace 가 실패한 상황이므로 되돌리기는 같은 방법에 기대지 않고 직접 쓴다.
    """
    try:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(original)
        return True
    except OSError as exc:
        print(f"[오류] 원본 복구 실패: {path.name} ({type(exc).__name__})")
        return False


def commit_files(writes: dict[Path, bytes]) -> None:
    """{경로: 바이트}를 한 번에 반영한다. 도중에 실패해도 파일들이 서로 어긋난 채 남지 않는다.

    1. 교체 전에 모든 대상의 원본 바이트를 메모리에 읽어 둔다 (없는 파일은 None).
    2. 모든 새 바이트를 같은 폴더의 임시 파일에 먼저 쓴다. 여기서 실패하면 원본은 하나도 건드리지 않는다.
    3. 임시 파일을 os.replace 로 하나씩 교체한다. 실패하면 이미 교체한 파일을 원본 바이트로 되돌리고,
       남은 임시 파일을 지운 뒤 CommitError 를 올린다.
    writes 에는 places.json·places_sources.json·places_review.csv 와 함께 place_seeds.json 의 새 바이트도 넣는다.
    쓰기 없이 끝나는 경로(offline 누락, 검증 실패, MAX_CALLS 중단)에서는 이 함수를 부르지 않으므로 시드 파일도 바뀌지 않는다.
    """
    if not writes:
        return
    originals: dict[Path, bytes | None] = {}
    for path in writes:
        try:
            originals[path] = path.read_bytes() if path.exists() else None
        except OSError as exc:  # 원본을 못 읽으면 되돌릴 수 없으므로 아무것도 쓰지 않는다
            raise CommitError(f"원본을 읽을 수 없어 쓰지 않았습니다: {path.name} ({type(exc).__name__})") from exc

    temps: dict[Path, Path] = {}
    try:
        for path, data in writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = _temp_path(path)
            temps[path] = temp
            temp.write_bytes(data)
    except OSError as exc:
        for temp in temps.values():
            _remove_quietly(temp)
        print(f"[오류] 임시 파일 쓰기 실패, 원본은 그대로입니다: {type(exc).__name__}")
        raise CommitError(f"임시 파일 쓰기 실패 ({type(exc).__name__})") from exc

    replaced: list[Path] = []
    try:
        for path, temp in temps.items():
            os.replace(temp, path)
            replaced.append(path)
    except OSError as exc:
        print(f"[오류] 파일 교체 실패 ({type(exc).__name__}). 이미 교체한 {len(replaced)}개를 원본으로 되돌립니다")
        restore_failed = [path for path in reversed(replaced) if not _restore_original(path, originals[path])]
        for temp in temps.values():
            _remove_quietly(temp)
        raise CommitError(f"파일 교체 실패 ({type(exc).__name__})", restore_failed) from exc


# ---------- 입출력: 결과 보고 (Fill_Report) ----------

REPORT_NAME = "fill_report.md"  # raw/name_backfill/ 아래에 저장한다
HAEUNDAE_THREE = ("the-bay-101", "busan-x-the-sky", "sea-life-busan")  # 해운대 3곳. ja 결과를 따로 보여 준다
RESTORE_IDS = ("biff-square", "jeonpo-cafe-street")  # 복원 대상. 추가 여부를 따로 보여 준다
NOT_MEASURED = "측정 안 됨"  # 작업 전 수치를 쓰기 전에 측정하지 못했을 때


@dataclass
class FillReport:
    """결과 보고에 담을 값. render_report 가 문자열로 바꾼다."""
    before: dict[str, int] | None  # 언어별 이름 보유 수. 쓰기 전에 측정하지 못했으면 None → "측정 안 됨"
    after: dict[str, int]
    target_type_check: list[dict] = field(default_factory=list)  # {lang, type, observed_types, ok} (+ 선택: source)
    haeundae_ja: dict[str, dict] = field(default_factory=dict)  # place_id → {name, match, dist_m} 또는 {reason}
    restored: dict[str, dict] = field(default_factory=dict)  # place_id → {added, name | reason}
    seeds_added: list[str] = field(default_factory=list)  # 이번에 추가한 시드 place_id
    missing_inputs: list[str] = field(default_factory=list)  # 없던 시드·좌표·raw 종류 (6.4)
    gaps: list[tuple[str, str]] = field(default_factory=list)  # 작업 후에도 빈 (place_id, lang)
    review_counts: dict[str, int] = field(default_factory=dict)  # 사유별 남은 review 행 수
    api_calls: dict[tuple[str, str], int] = field(default_factory=dict)  # (서비스, 작업) → 호출 수
    expected_calls: int = EXPECTED_CALLS
    max_calls: int = MAX_CALLS
    stopped_by_budget: str | None = None  # 상한으로 멈춘 위치 문구. 멈추지 않았으면 None
    linked: dict[str, bool] = field(default_factory=dict)  # 연결 스크립트 → 실행함 여부
    failed_step: str | None = None  # 실패한 연결 스크립트 이름 (7.2)
    failed_langs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def measure_before(places: object) -> dict[str, int] | None:
    """쓰기 전에 읽은 places 로 언어별 이름 수를 잰다. 측정할 수 없으면 None (추정값을 쓰지 않는다, 9.7).

    places 가 목록이 아니거나, 항목이 dict 가 아니거나, names 가 dict 가 아니면 None 이다.
    """
    if not isinstance(places, list):
        return None
    try:
        for place in places:
            names = place.get("names") if isinstance(place, dict) else None
            if not isinstance(names, dict):
                return None
        return count_names(places)
    except (AttributeError, TypeError, KeyError):
        return None


def measure_before_from_path(path: Path) -> dict[str, int] | None:
    """places.json 을 읽어 measure_before 를 부른다. 파일이 없거나 JSON 이 아니면 None. 파일을 쓰지 않는다."""
    try:
        return measure_before(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def type_check_rows(checks: Iterable[TypeCheck]) -> list[dict]:
    """TypeCheck 를 보고서용 dict({lang, type, observed_types, ok, source})로 바꾼다."""
    return [{"lang": c.lang, "type": c.type_id, "observed_types": list(c.observed_types), "ok": c.ok,
             "item_count": c.item_count, "source": c.source} for c in checks]


def count_review_reasons(rows: Iterable[dict]) -> dict[str, int]:
    """review 행을 사유별로 센다. "api_error: ..." 처럼 ': ' 뒤에 세부 사유가 붙은 것은 앞부분으로 묶는다."""
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason", "")).split(": ", 1)[0] or "(사유 없음)"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _md(value: object) -> str:
    """표 칸에 넣을 문자열. 줄바꿈과 파이프는 표를 깨므로 바꾼다."""
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def _lang_table(before: dict[str, int] | None, after: dict[str, int]) -> list[str]:
    """언어별 작업 전 / 작업 후 / 증감 표. before 가 없으면 작업 전·증감을 "측정 안 됨"으로 쓴다."""
    lines = ["| 언어 | 작업 전 | 작업 후 | 증감 |", "|---|---|---|---|"]
    for lang in NAME_LANGS:
        now = after.get(lang, 0)
        if before is None or lang not in before:
            lines.append(f"| {lang} | {NOT_MEASURED} | {now}곳 | {NOT_MEASURED} |")
        else:
            lines.append(f"| {lang} | {before[lang]}곳 | {now}곳 | {now - before[lang]:+d} |")
    return lines


def _type_check_lines(rows: list[dict]) -> list[str]:
    if not rows:
        return ["확인한 응답 없음"]
    verdict = {True: "일치", False: "불일치", None: "확인 불가"}
    lines = ["| 언어 | 타입 | 응답의 contenttypeid | 결과 | 근거 파일 |", "|---|---|---|---|---|"]
    for row in rows:
        observed = ", ".join(str(t) for t in row.get("observed_types", [])) or "-"
        lines.append(f"| {_md(row.get('lang', ''))} | {_md(row.get('type', ''))} | {_md(observed)} | "
                     f"{verdict.get(row.get('ok'), '확인 불가')} | {_md(row.get('source') or '-')} |")
    return lines


def _haeundae_line(place_id: str, result: dict | None) -> str:
    """해운대 한 곳의 ja 결과 한 줄. 채웠으면 이름·일치 종류·거리(m), 못 채웠으면 사유."""
    if not result:
        return f"- {place_id}: 결과 없음 (처리되지 않음)"
    if result.get("reason"):
        return f"- {place_id}: 못 채움, 사유 {result['reason']}"
    dist = result.get("dist_m")
    return f"- {place_id}: {result.get('name', '')} / 일치 {result.get('match') or '-'} / 거리 {'-' if dist is None else f'{dist}m'}"


def _restored_line(place_id: str, result: dict | None) -> str:
    """복원 대상 한 곳의 추가 여부 한 줄. 추가했으면 이름, 아니면 사유."""
    if not result:
        return f"- {place_id}: 추가 안 됨, 사유 기록 없음 (처리되지 않음)"
    if result.get("added"):
        return f"- {place_id}: 추가됨, 이름 {result.get('name', '')}"
    return f"- {place_id}: 추가 안 됨, 사유 {result.get('reason') or '기록 없음'}"


def render_report(report: FillReport) -> str:
    """Fill_Report 를 마크다운 문자열로 만든다. 파일·네트워크를 쓰지 않는다. serviceKey 는 어디에도 넣지 않는다."""
    out: list[str] = ["# 이름 채우기 결과 (Fill_Report)", ""]

    out += ["## 언어별 이름 보유 장소 수", ""]
    if report.before is None:
        out += [f"작업 전 수치는 {NOT_MEASURED} (파일을 쓰기 전에 측정하지 못했습니다). 작업 후 수치만 보여 줍니다.", ""]
    out += _lang_table(report.before, report.after)

    out += ["", "## Target_Types 확인 근거", ""] + _type_check_lines(report.target_type_check)

    out += ["", "## 해운대 3곳 ja 결과", ""]
    out += [_haeundae_line(pid, report.haeundae_ja.get(pid)) for pid in HAEUNDAE_THREE]

    out += ["", "## 복원 대상 (biff-square, jeonpo-cafe-street)", ""]
    out += [_restored_line(pid, report.restored.get(pid)) for pid in RESTORE_IDS]
    out += [f"- 추가한 시드: {', '.join(report.seeds_added) if report.seeds_added else '없음'}"]
    if report.missing_inputs:
        out += ["- 없던 입력: " + "; ".join(report.missing_inputs)]

    out += ["", "## 작업 후에도 비어 있는 (장소, 언어)", ""]
    out += [f"- {pid}: {lang}" for pid, lang in report.gaps] if report.gaps else ["없음"]
    out += ["", "## review 사유별 남은 항목 수", ""]
    out += [f"- {reason}: {count}건" for reason, count in report.review_counts.items()] if report.review_counts else ["없음"]

    out += ["", "## API 호출 수", "", "| 서비스 | 작업 | 호출 수 |", "|---|---|---|"]
    for (service, operation), count in sorted(report.api_calls.items()):
        out.append(f"| {_md(service)} | {_md(operation)} | {int(count)} |")
    total = sum(int(c) for c in report.api_calls.values())
    out += [f"| 합계 | | {total} |", "",
            f"- 합계 {total}회 (예상 {report.expected_calls}회, 상한 {report.max_calls}회)"]
    if report.stopped_by_budget:
        out += [f"- 호출 상한으로 중단: {report.stopped_by_budget}"]
    if report.failed_langs:
        out += [f"- 호출이 실패한 언어 {len(report.failed_langs)}개: {', '.join(report.failed_langs)}"]

    out += ["", "## 연결 스크립트", ""]
    steps = [*LINKED_STEPS_NEW_PLACE, *(name for name in report.linked if name not in LINKED_STEPS_NEW_PLACE)]
    out += [f"- {name}: {'실행함' if report.linked.get(name) else '실행 안 함'}" for name in steps]
    if report.failed_step:
        out += [f"- 실패한 단계: {report.failed_step} (남은 단계는 실행하지 않았습니다)"]

    out += ["", "## 경고", ""]
    out += [f"- {warning}" for warning in report.warnings] if report.warnings else ["없음"]
    return "\n".join(out) + "\n"


def _redact_key(text: str) -> str:
    """보고서에 serviceKey 값이 섞여 들어가지 않게 마지막으로 가린다 (방어용. 정상 흐름에서는 키가 들어가지 않는다)."""
    key = config.DATA_GO_KR_KEY
    return text.replace(key, "***") if key and len(key) >= 8 else text


def write_report(report: FillReport, report_path: Path | None = None) -> str:
    """보고서를 표준 출력과 raw/name_backfill/fill_report.md 에 쓰고 본문을 돌려준다.

    report_path 를 생략하면 RAW_DIR / fill_report.md 다 (테스트는 RAW_DIR 를 임시 폴더로 바꾼다).
    보고서 파일은 raw 와 같은 폴더라 쓰기 금지 대상(places.json 등)이 아니다. 파일 쓰기가 실패해도 출력은 남긴다.
    """
    text = _redact_key(render_report(report))
    print(text)
    path = report_path if report_path is not None else RAW_DIR / REPORT_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"보고서를 저장했습니다: {path}")
    except OSError as exc:
        print(f"[경고] 보고서 파일을 저장하지 못했습니다 ({type(exc).__name__}): {path}")
    return text


# ---------- 입출력: 입력 읽기와 시드 직렬화 ----------

class InputError(Exception):
    """입력 파일을 읽을 수 없다. 아무것도 쓰지 않고 종료 코드 1."""


class Inputs(NamedTuple):
    """실행 시작 시점에 읽은 입력. 파일은 여기서만 읽고, 이후 단계는 이 값만 쓴다."""
    places: list[dict]
    sources: dict
    review_rows: list[dict]
    seeds: list[dict]
    originals: dict[Path, bytes | None]  # 쓰기 전 원본 바이트 (바뀌지 않은 파일은 다시 쓰지 않는 데 쓴다)
    overrides: bytes | None  # curation_overrides.json 스냅샷 (7.6)


def _read_bytes(path: Path) -> bytes | None:
    """파일 바이트. 없거나 읽을 수 없으면 None."""
    try:
        return path.read_bytes() if path.exists() else None
    except OSError:
        return None


def parse_review_rows(data: bytes | None) -> list[dict]:
    """places_review.csv 바이트를 행 목록으로. 없으면 빈 목록. 열은 REVIEW_FIELDS 로 맞춘다."""
    if not data:
        return []
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    return [{field_name: row.get(field_name) or "" for field_name in fp.REVIEW_FIELDS} for row in reader]


def dump_seeds(seeds: list[dict]) -> bytes:
    """place_seeds.json 바이트. 기존 파일처럼 시드 하나를 한 줄로 쓰고 BOM 없는 UTF-8, 줄바꿈은 CRLF."""
    rows = ",\r\n".join("  " + json.dumps(seed, ensure_ascii=False) for seed in seeds)
    return ("[\r\n" + rows + "\r\n]\r\n").encode("utf-8")


def read_inputs() -> Inputs:
    """places, sources, review, seeds 와 curation_overrides 스냅샷을 읽는다. 아무것도 쓰지 않는다.

    places.json 과 place_seeds.json 은 꼭 있어야 한다. sources·review 는 없으면 빈 값으로 본다.
    """
    originals = {path: _read_bytes(path) for path in (PLACES_PATH, SOURCES_PATH, REVIEW_PATH, SEEDS_PATH)}
    for path in (PLACES_PATH, SEEDS_PATH):
        if originals[path] is None:
            raise InputError(f"입력 파일이 없거나 읽을 수 없습니다: {path}")
    try:
        places = json.loads(originals[PLACES_PATH].decode("utf-8-sig"))
        seeds = json.loads(originals[SEEDS_PATH].decode("utf-8-sig"))
        sources = json.loads(originals[SOURCES_PATH].decode("utf-8-sig")) if originals[SOURCES_PATH] else {}
        review_rows = parse_review_rows(originals[REVIEW_PATH])
    except (ValueError, csv.Error) as exc:
        raise InputError(f"입력 파일을 해석할 수 없습니다 ({type(exc).__name__}: {exc})") from exc
    if not (isinstance(places, list) and all(isinstance(p, dict) and isinstance(p.get("place_id"), str) for p in places)):
        raise InputError(f"{PLACES_PATH.name} 은 place_id 가 있는 장소 목록이어야 합니다")
    if not (isinstance(seeds, list) and all(isinstance(s, dict) and isinstance(s.get("place_id"), str) for s in seeds)):
        raise InputError(f"{SEEDS_PATH.name} 은 place_id 가 있는 시드 목록이어야 합니다")
    if not isinstance(sources, dict):
        raise InputError(f"{SOURCES_PATH.name} 은 객체여야 합니다")
    return Inputs(places, sources, review_rows, seeds, originals, _read_bytes(OVERRIDES_PATH))


# ---------- 입출력: 기존 장소 채우기와 복원 대상 처리 ----------

class FillOutcome(NamedTuple):
    """fill_existing 의 결과."""
    places: list[dict]  # 입력과 같은 순서의 장소 (채운 곳만 names 가 바뀜)
    updates: dict[str, dict[str, FilledName]]  # place_id → 이번에 채운 언어 (merge_sources 입력)
    rows: list[dict]  # 새 review 행 (중복 제거 전)
    filled_pairs: set[tuple[str, str]]  # 이번에 채운 (place_id, lang)


def fill_existing(places: list[dict], sources: dict, ko_names: dict[str, str], collection: Collection,
                  raw_root: Path | None = None) -> FillOutcome:
    """기존 장소의 빠진 언어를 수집한 Area_List 로 채운다. 국문 기준은 저장된 raw 에서만 읽는다(3.4).

    수집에 성공한 언어 중 빠진 언어가 없는 장소는 건드리지 않는다. 국문 raw 가 없거나 읽을 수 없으면
    그 장소는 건너뛰고 kor_raw_missing 행만 남긴다(3.5, 3.6).
    """
    out: list[dict] = []
    updates: dict[str, dict[str, FilledName]] = {}
    rows: list[dict] = []
    pairs: set[tuple[str, str]] = set()
    for place in places:
        pid = place["place_id"]
        names = place.get("names")
        if not isinstance(names, dict) or not any(lang in collection.areas for lang in missing_langs(names)):
            out.append(place)
            continue
        name_ko = ko_names.get(pid, "")
        kor = load_kor(pid, sources, name_ko, rows, raw_root)
        if kor is None:
            out.append(place)
            continue
        result = fill_names(pid, name_ko or kor["title"], kor, names, collection.candidates)
        rows += result.reviews
        out.append(apply_fill(place, result))
        if result.filled:
            updates[pid] = dict(result.filled)
            pairs |= {(pid, lang) for lang in result.filled}
    return FillOutcome(out, updates, rows, pairs)


def _restore_request(seed: dict, raw_root: Path | None) -> _Request:
    """복원 대상의 국문 조회 요청 (resolve_restore 가 보내는 것과 같다)."""
    extra = {"keyword": seed["query"], "numOfRows": fp.KEYWORD_ROWS}
    return _Request(fp.SERVICES["ko"], "searchKeyword2", extra, _kor_raw_path(seed["place_id"], raw_root))


def restore_needs_call(seed: dict, raw_root: Path | None = None) -> bool:
    """resolve_restore 가 국문 조회를 실제로 보내야 하는지. 저장된 응답을 읽기만 하면 False."""
    request = _restore_request(seed, raw_root)
    if seed["place_id"] in RESTORE_ALWAYS_SEARCH:
        return not _is_saved(request)
    return not request.raw_path.exists()


def restore_missing_raw(targets: list[dict], raw_root: Path | None = None) -> list[str]:
    """--offline 에서 필요한데 raw 에 없는 복원 대상의 국문 조회 (서비스·작업·파일 경로)."""
    return [f"{request.service}/{request.operation} ({seed['query']}): {request.raw_path}"
            for seed in targets if restore_needs_call(seed, raw_root)
            for request in [_restore_request(seed, raw_root)]]


class RestoreOutcome:
    """process_restore 의 결과."""

    def __init__(self) -> None:
        self.places: list[dict] = []  # 이번에 추가한 새 장소
        self.sources: dict[str, dict] = {}  # 새 장소의 places_sources 항목
        self.rows: list[dict] = []  # 새 review 행
        self.results: dict[str, dict] = {}  # place_id → {added, name | reason} (보고서용)
        self.errors: list[str] = []  # 국문 조회 실패 (종료 코드 1 대상)
        self.filled: dict[str, dict[str, FilledName]] = {}  # place_id → 채운 언어


def _joined_names(names: dict[str, str]) -> str:
    return ", ".join(f"{lang}={names[lang]}" for lang in NAME_LANGS if lang in names)


def process_restore(targets: list[dict], collection: Collection, log: CallLog, stations: list[dict],
                    raw_root: Path | None = None) -> RestoreOutcome:
    """복원 대상(biff-square, jeonpo-cafe-street)의 국문 후보를 정하고 빠진 언어를 채워 새 장소를 만든다.

    각 대상의 국문 조회를 보내기 전에 log.budget.extra_pending 에서 그 호출분을 뺀다. 수집 단계가 이 호출을
    미리 세어 두었으므로, 빼지 않으면 상한 점검이 같은 호출을 두 번 센다.
    좌표와 외국어 이름이 있을 때만 장소를 만들고(build_new_place), 못 만들면 사유를 review 에 남긴다.
    """
    out = RestoreOutcome()
    for seed in targets:
        pid = seed["place_id"]
        if restore_needs_call(seed, raw_root):
            log.budget.extra_pending = max(0, log.budget.extra_pending - 1)
        resolution = resolve_restore(seed, log, raw_root)
        out.rows += resolution.reviews
        if resolution.error:
            out.errors.append(f"{pid}: {resolution.error}")
            out.results[pid] = {"added": False, "reason": resolution.error}
            continue
        if resolution.kor is None:
            reason = resolution.reviews[0]["reason"] if resolution.reviews else "국문 후보 없음"
            out.results[pid] = {"added": False, "reason": reason}
            continue
        result = fill_names(pid, seed["name_ko"], resolution.kor, {}, collection.candidates)
        out.rows += result.reviews  # 못 채운 언어의 후보 목록도 남긴다
        new = build_new_place(seed, resolution.kor, result, stations, raw_root)
        out.rows += new.reviews
        if new.place is None or new.source is None:
            out.results[pid] = {"added": False, "reason": new.reviews[0]["reason"] if new.reviews else "장소를 만들지 못함"}
            continue
        out.places.append(new.place)
        out.sources[pid] = new.source
        out.filled[pid] = dict(result.filled)
        out.results[pid] = {"added": True, "name": _joined_names(new.place["names"])}
    return out


def invalid_place_ids(places: list[dict]) -> list[str]:
    """Place 모델 검증에 실패하는 장소의 place_id 목록 (2.12)."""
    bad: list[str] = []
    for place in places:
        try:
            Place.model_validate(place)
        except ValidationError:
            bad.append(str(place.get("place_id", "?")))
    return bad


def merge_review_rows(old_rows: list[dict], new_rows: list[dict], filled_pairs: set[tuple[str, str]],
                      failed_langs: Iterable[str], ok_langs: Iterable[str], restore_ids: Iterable[str]) -> list[dict]:
    """review 행을 병합한다. 이미 있는 (place_id, lang) 행은 새 행으로 중복해 만들지 않는다.

    지우는 기존 행: 이번에 채운 쌍, 이번에 다시 실패한 언어의 api_error 행(새 사유로 바꾼다),
    다시 처리한 복원 대상의 이전 행(마지막 시도 결과로 바꾼다). 그 밖의 기존 행(kept_existing 등)은 그대로 둔다.
    위 쌍에 해당하지 않는 기존 쌍에는 새 행을 더하지 않아 재실행해도 같은 행이 쌓이지 않는다.
    """
    restore_set = set(restore_ids)
    remove = set(filled_pairs) | {("*", lang) for lang in failed_langs}
    remove |= {(row["place_id"], row["lang"]) for row in old_rows if row["place_id"] in restore_set}
    known = {(row["place_id"], row["lang"]) for row in old_rows} - remove
    fresh: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in new_rows:
        key = (row["place_id"], row["lang"])
        if key in known or (*key, row["reason"]) in seen:
            continue
        seen.add((*key, row["reason"]))
        fresh.append(row)
    return merge_review(old_rows, remove, fresh, set(ok_langs))


# ---------- 입출력: 연결 스크립트와 사후 점검 ----------

def default_runners() -> dict[str, Callable[[], object]]:
    """연결 스크립트 4개의 main 을 같은 프로세스에서 부르는 실행 목록. 쓸 때만 import 한다."""
    from scripts import build_congestion, build_curation, build_stations, build_travel_times
    return {
        "build_travel_times": build_travel_times.main,
        "build_curation": build_curation.main,
        "build_congestion": build_congestion.main,
        "build_stations": build_stations.main,
    }


def _known_stations() -> set[str] | None:
    """stations.json 의 역 이름 집합. 읽을 수 없으면 None."""
    try:
        data = json.loads(STATIONS_JSON_PATH.read_text(encoding="utf-8"))
        return {str(station["station"]) for station in data["stations"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _congestion_places() -> set[str] | None:
    """congestion.json 에 값이 있는 place_id 집합. 읽을 수 없으면 None."""
    try:
        return set(json.loads(CONGESTION_PATH.read_text(encoding="utf-8"))["places"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def new_place_warnings(new_places: list[dict], congestion_built: bool) -> list[str]:
    """새 장소의 nearest_station(7.5)과 혼잡도 연결 표(7.4) 경고. 파일은 읽기만 한다.

    nearest_station 이 stations.json 에 없으면 place_id 와 값을 담은 경고를 낸다.
    PLACE_NAMES 에 없거나 (build_congestion 을 실행했는데) congestion.json 에 값이 없으면 "요일 규칙 대체 대상"으로 적는다.
    """
    if not new_places:
        return []
    from scripts import build_congestion  # 호출 때 읽어서 PLACE_NAMES 변경이 반영된다
    warnings: list[str] = []
    stations = _known_stations()
    if stations is None:
        warnings.append(f"{STATIONS_JSON_PATH.name} 을 읽을 수 없어 새 장소의 nearest_station 을 확인하지 못했습니다")
    congestion = _congestion_places() if congestion_built else None
    for place in new_places:
        pid, station = place["place_id"], place.get("nearest_station")
        if stations is not None and station not in stations:
            warnings.append(f"{pid} 의 nearest_station {station!r} 이 {STATIONS_JSON_PATH.name} 에 없습니다")
        if pid not in build_congestion.PLACE_NAMES:
            warnings.append(f"요일 규칙 대체 대상: {pid} (build_congestion.PLACE_NAMES 에 없어 혼잡도 연결 표를 만들지 않음)")
        elif congestion is not None and pid not in congestion:
            warnings.append(f"요일 규칙 대체 대상: {pid} ({CONGESTION_PATH.name} 에 값이 없음)")
    return warnings


# ---------- 입출력: 보고서 재료 ----------

def haeundae_ja_results(final_places: list[dict], filled: dict[str, dict[str, FilledName]],
                        rows: list[dict]) -> dict[str, dict]:
    """해운대 3곳의 ja 결과. 채웠으면 {name, match, dist_m}, 못 채웠으면 {reason}."""
    by_id = {place["place_id"]: place for place in final_places}
    out: dict[str, dict] = {}
    for pid in HAEUNDAE_THREE:
        place = by_id.get(pid)
        names = (place or {}).get("names") or {}
        item = filled.get(pid, {}).get("ja")
        if place is None:
            out[pid] = {"reason": "places.json 에 없음"}
        elif item is not None:
            out[pid] = {"name": item.name, "match": item.match, "dist_m": item.dist_m}
        elif _has_text(names.get("ja")):
            out[pid] = {"name": names["ja"], "match": "기존 이름 유지", "dist_m": None}
        else:
            reason = next((row["reason"] for row in rows
                           if (row["place_id"] == pid and row["lang"] in ("ja", "ko", "all"))
                           or (row["place_id"] == "*" and row["lang"] == "ja")), "사유 기록 없음 (처리되지 않음)")
            out[pid] = {"reason": reason}
    return out


def _count_saved_raw() -> int:
    """raw/name_backfill/ 에 저장된 쪽 파일 수 (중단 메시지용)."""
    try:
        return len(list(RAW_DIR.glob("*_t*_p*.json")))
    except OSError:
        return 0


def budget_message(exc: BudgetExceeded) -> str:
    """호출 상한 중단 메시지 (설계 「상한을 넘겼을 때」 형식). serviceKey 는 넣지 않는다."""
    return (f"[중단] API {exc}\n"
            f"이미 받은 raw {_count_saved_raw()}개는 그대로 있습니다. 쓰기는 하지 않았습니다.\n"
            "추정과 다르면 MAX_CALLS를 고친 뒤 --reuse-raw 로 다시 실행하세요. 저장된 쪽은 다시 부르지 않습니다.")


def _finish(report: FillReport, log: CallLog, code: int, save: bool = True) -> int:
    """보고서와 요약(실패 언어 수, 호출 수)을 출력하고 종료 코드를 돌려준다.

    save=False 면 보고서를 파일로 저장하지 않고 출력만 한다 (--offline 누락처럼 아무것도 쓰지 않는 종료).
    """
    report.api_calls = dict(log.counts)
    if save:
        write_report(report)
    else:
        print(_redact_key(render_report(report)))
    print(f"[요약] 종료 코드 {code}, 실패한 언어 {len(report.failed_langs)}개, API 호출 {log.total}회 "
          f"(예상 {EXPECTED_CALLS}회, 상한 {MAX_CALLS}회)")
    return code


# ---------- 실행 ----------

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="backfill_names", description="places.json 의 비어 있는 외국어 이름을 부산 전체 목록으로 채운다")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="raw 에 저장된 쪽은 다시 부르지 않고 없는 쪽만 호출한다 (항상 이렇게 동작하므로 지정하지 않아도 같다)")
    ap.add_argument("--offline", action="store_true", help="API 를 부르지 않고 raw 에 저장된 응답만 쓴다")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, runners: dict[str, Callable[[], object]] | None = None) -> int:
    """전체 흐름을 실행하고 종료 코드를 돌려준다. runners 로 연결 스크립트 실행 목록을 바꿀 수 있다(테스트용).

    흐름: 입력 읽기 → 작업 전 스냅샷 → 시드 보정 → 수집 → 기존 장소 채우기 → 복원 대상 처리 → Place 검증
         → 병합 → commit_files → 연결 스크립트 → 보고서. 파일은 commit_files 에서만 쓴다.
    """
    args = _parse_args(argv)
    fp.OFFLINE, fp.REUSE_RAW = args.offline, True  # 저장된 쪽은 항상 다시 부르지 않는다 (--reuse-raw 와 같은 동작)
    if not fp.OFFLINE and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING 이 비어 있습니다. backend/.env 를 확인하세요. (API 없이 raw 만 쓰려면 --offline)",
              file=sys.stderr)
        return 1
    try:
        data = read_inputs()
    except InputError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1

    # 작업 전 수치·Baseline_IDs·curation_overrides 는 어떤 파일도 쓰기 전에 잰다 (9.6, 7.1, 7.6)
    baseline_ids = {place["place_id"] for place in data.places}
    report = FillReport(before=measure_before(data.places), after=count_names(data.places))
    report.linked = {name: False for name in LINKED_STEPS_NEW_PLACE}

    fix = apply_seed_fixes(data.seeds)  # 메모리에서만 보정한다. 저장은 commit_files 에서 한다
    seeds_by_id = {seed["place_id"]: seed for seed in fix.seeds}
    raw_root = RAW_DIR.parent
    report.seeds_added = list(fix.added)
    report.warnings += [f"시드 변경(저장 전): {text}" for text in fix.changed]
    targets = [seeds_by_id[pid] for pid in RESTORE_IDS if pid not in baseline_ids and pid in seeds_by_id]
    report.missing_inputs += [f"{pid}: 시드 없음" for pid in RESTORE_IDS if pid not in baseline_ids and pid not in seeds_by_id]
    report.missing_inputs += [f"{pid}: 시드 없음 (place_seeds.json 에 이번에 추가)" for pid in fix.added if pid in RESTORE_IDS]
    report.missing_inputs += [f"{seed['place_id']}: 국문 raw 없음 ({_kor_raw_path(seed['place_id'], raw_root)})"
                              for seed in targets if not _kor_raw_path(seed["place_id"], raw_root).exists()]

    stations: list[dict] = []
    if targets:
        try:
            stations = fp.load_stations(STATIONS_CSV_PATH)
        except (OSError, ValueError) as exc:
            print(f"[오류] 역 좌표 파일을 읽을 수 없습니다: {STATIONS_CSV_PATH} ({type(exc).__name__})", file=sys.stderr)
            return 1

    # 수집 밖에서 반드시 보낼 국문 조회 수를 상한 계산에 넣는다 (offline 은 호출이 없다)
    pending = 0 if fp.OFFLINE else sum(restore_needs_call(seed, raw_root) for seed in targets)
    log = CallLog(extra_pending=pending)
    collection: Collection | None = None
    try:
        collection = collect_area_lists(log)
        report.target_type_check = type_check_rows(collection.type_checks)
        report.warnings += collection.warnings
        report.failed_langs = list(collection.failed)

        missing = collection.missing_raw + (restore_missing_raw(targets, raw_root) if fp.OFFLINE else [])
        if missing:  # --offline 인데 raw 가 없다. API 를 부르지 않고 아무것도 쓰지 않는다 (8.3)
            print(f"[오류] --offline: 필요한 응답이 raw 에 없습니다 ({len(missing)}건). 아래 파일을 받은 뒤 다시 실행하세요.", file=sys.stderr)
            for text in missing:
                print(f"  - {text}", file=sys.stderr)
            report.warnings += [f"offline 누락: {text}" for text in missing]
            return _finish(report, log, 2, save=False)

        ko_names = {seed["place_id"]: str(seed.get("name_ko", "")) for seed in fix.seeds}
        fill = fill_existing(data.places, data.sources, ko_names, collection, raw_root)
        restore = process_restore(targets, collection, log, stations, raw_root)
    except TargetTypeMismatch as exc:  # 1.9: 이후 호출을 시작하지 않고 아무것도 쓰지 않는다
        found = exc.collection.type_checks if exc.collection else [exc.check]
        report.target_type_check = type_check_rows(found)
        report.warnings.append(f"Target_Types 불일치: {exc}")
        report.failed_langs = list(exc.collection.failed) if exc.collection else []
        print(f"[오류] Target_Types 불일치로 목록 호출을 중단했습니다: {exc}", file=sys.stderr)
        return _finish(report, log, 1)
    except BudgetExceeded as exc:  # 8.1: 추가 호출 없이 멈추고 아무것도 쓰지 않는다
        partial = exc.collection or collection  # 수집 중이면 exc.collection, 복원 단계면 이미 끝난 collection
        report.target_type_check = type_check_rows(partial.type_checks if partial else [])
        report.stopped_by_budget = f"{exc.lang}, 타입 {exc.type_id}, 쪽 {exc.page} ({exc.reason})"
        report.failed_langs = list(partial.failed) if partial else []
        print(budget_message(exc), file=sys.stderr)
        return _finish(report, log, 3)

    # 병합과 Place 검증. 검증에 실패하면 어떤 파일도 쓰지 않는다 (2.12)
    final_places = append_new_places(fill.places, restore.places)
    bad = invalid_place_ids(final_places)
    if bad:
        print(f"[오류] Place 검증 실패, 쓰지 않고 종료합니다: {', '.join(bad)}", file=sys.stderr)
        report.warnings.append(f"Place 검증 실패: {', '.join(bad)}")
        return _finish(report, log, 1)
    sources = merge_sources(data.sources, fill.updates)
    sources.update(restore.sources)

    api_rows = [{"place_id": "*", "name_ko": "", "lang": lang, "reason": f"api_error: {reason}", "candidates": ""}
                for lang, reason in collection.failed.items()]
    review_rows = merge_review_rows(
        data.review_rows, [*fill.rows, *restore.rows, *api_rows], fill.filled_pairs,
        failed_langs=collection.failed, ok_langs=collection.areas, restore_ids={seed["place_id"] for seed in targets})

    new_bytes = {PLACES_PATH: dump_places(final_places), SOURCES_PATH: dump_sources(sources),
                 REVIEW_PATH: dump_review(review_rows)}
    if fix.added or fix.changed:  # 시드 저장은 다른 파일과 같은 commit_files 에서만 한다 (쓰기 없는 종료 경로에서는 저장하지 않는다)
        new_bytes[SEEDS_PATH] = dump_seeds(fix.seeds)
    writes = {path: blob for path, blob in new_bytes.items() if blob != data.originals.get(path)}
    try:
        commit_files(writes)
    except CommitError as exc:
        print(f"[오류] 파일 쓰기에 실패했습니다: {exc}", file=sys.stderr)
        if exc.restore_failed:
            print(f"[오류] 원본으로 되돌리지 못한 파일: {', '.join(path.name for path in exc.restore_failed)}", file=sys.stderr)
        report.warnings.append(f"파일 쓰기 실패: {exc}")
        return _finish(report, log, 1)

    code = 1 if (collection.failed or restore.errors) else 0
    for error in restore.errors:
        print(f"[오류] 복원 대상 국문 조회 실패: {error}", file=sys.stderr)

    # 연결 스크립트 (7.1, 7.3). 같은 프로세스에서 main 을 부르고, 첫 실패에서 멈춘다 (7.2)
    filled_count = sum(len(langs) for langs in fill.updates.values())
    steps = plan_linked_steps(baseline_ids, [place["place_id"] for place in final_places], filled_count)
    ran, failed_step = run_chain(steps, runners if runners is not None else (default_runners() if steps else {}))
    report.linked = {name: name in ran for name in LINKED_STEPS_NEW_PLACE}
    report.failed_step = failed_step
    if failed_step:
        code = 1
        print(f"[오류] 연결 스크립트 {failed_step} 가 실패했습니다. 남은 단계는 실행하지 않았습니다.", file=sys.stderr)
    report.warnings += new_place_warnings(restore.places, "build_congestion" in ran and failed_step != "build_congestion")
    if _read_bytes(OVERRIDES_PATH) != data.overrides:  # 7.6: 이 스크립트는 그 파일을 쓰지 않는다
        code = 1
        report.warnings.append(f"{OVERRIDES_PATH.name} 이 실행 전후로 다릅니다. 수동 항목이 바뀌었는지 확인하세요")
        print(f"[경고] {OVERRIDES_PATH.name} 이 실행 전후로 다릅니다", file=sys.stderr)

    # 보고서 재료
    filled_all = {**fill.updates, **restore.filled}
    report.after = count_names(final_places)
    report.gaps = remaining_gaps(final_places)
    report.review_counts = count_review_reasons(review_rows)
    report.haeundae_ja = haeundae_ja_results(final_places, filled_all, review_rows)
    report.restored = dict(restore.results)
    for pid in RESTORE_IDS:
        if pid in report.restored:
            continue
        reason = "이미 places.json 에 있어 이번에 추가하지 않음" if pid in baseline_ids else "시드 없음"
        report.restored[pid] = {"added": False, "reason": reason}
    return _finish(report, log, code)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
