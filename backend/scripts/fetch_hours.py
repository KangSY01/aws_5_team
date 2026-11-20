"""장소별 운영시간(hours.json)을 한국관광공사 TourAPI 소개정보로 만든다. backend/ 에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_hours            # 장소당 KorService2/detailIntro2 1회
    uv run python -m scripts.fetch_hours --offline                  # 호출 없이 저장된 raw 로 다시 만든다 (규칙만 바꿨을 때)
    uv run --env-file .env python -m scripts.fetch_hours --refresh  # 저장된 응답이 있어도 전부 다시 받는다

기본 동작은 raw 에 같은 요청의 응답이 있으면 다시 부르지 않는다(장소당 1회). 새로 추가된 장소만 호출된다.
입력
  app/data/places.json, app/data/places_sources.json (국문 contentid, kor_class.contenttypeid)
출력
  app/data/hours.json                    get_hours 가 읽는다
  app/data/raw/<place_id>/ko_intro.json  API 원본 응답 (serviceKey 는 저장하지 않는다. raw 는 git 에 올리지 않는다)

소개정보의 필드 이름은 관광타입마다 다르다(INTRO_FIELDS). 값은 사람이 쓴 한국어 문장이다.
  opens·closes     이용시간 문장에 "HH:MM~HH:MM" 이 정확히 하나 있고, 다른 숫자나 요일·계절 조건이 없을 때만 넣는다.
                   뒤에 붙은 "(입장 마감 17:30)" 은 무시한다. 끝이 24:00 이면 넣지 않는다(시각으로 쓸 수 없다).
  closed_weekdays  쉬는날 문장의 "매주 ○요일" 만 넣는다 (0=월 ... 6=일). "공휴일이면 다음 날" 같은 예외는 반영하지 않는다.
                   "점포 별로 상이"·"일부" 같은 단서가 붙은 휴무는 넣지 않는다 (국제시장: "매주 일요일※ 점포 별로 상이함").
  closed_dates     넣지 않는다 ("1월 1일", "설날 당일" 같은 값은 연도·음력 계산이 필요하다).
  raw_text         API 원문(태그만 정리). 위 값으로 바꾸지 못한 내용(계절별 시간, 입장 마감, 공휴일 예외)은 여기에만 있다.
애매하면 null·빈 목록으로 둔다. 값을 지어내지 않는다.
"""
import argparse
import html
import json
import re
import sys

from app import config
from scripts import fetch_places as fp

OUT_PATH = fp.DATA_DIR / "hours.json"
# 국문 관광타입(contenttypeid) → (이용시간 필드, 쉬는날 필드). raw 응답에서 확인한 타입만 둔다.
INTRO_FIELDS = {
    "12": ("usetime", "restdate"),  # 관광지
    "14": ("usetimeculture", "restdateculture"),  # 문화시설
    "38": ("opentime", "restdateshopping"),  # 쇼핑
}
WEEKDAYS = "월화수목금토일"  # datetime.weekday() 순서
# 국문 항목이 그 장소 전체가 아니라서 소개정보를 쓰지 않는 곳. 호출하지 않고 모르는 값으로 둔다.
NOT_THE_PLACE = {
    "busan-cinema-center": "국문 항목이 '영화의전당 라이브러리 자료실'(자료실)이라 영화의전당 전체의 시간이 아니다",
}
UNKNOWN = {"opens": None, "closes": None, "closed_weekdays": [], "closed_dates": [], "raw_text": None}

_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[~\-–∼]\s*(\d{1,2}):(\d{2})")
# 시간이 날짜·계절에 따라 달라진다는 표시. 하나라도 있으면 opens·closes 를 넣지 않는다.
_CONDITION_RE = re.compile(r"요일|주말|평일|공휴일|계절|절기|성수기|비수기|[월화수목금토일]\s*[~\-–∼]\s*[월화수목금토일]")
_WEEKLY_RE = re.compile(rf"매주\s*([{WEEKDAYS}])요일")
# 휴무가 장소 전체에 해당하지 않는다는 단서 ("점포 별로 상이함", "일부 매장 휴무", "매장마다 다름")
_PARTIAL_RE = re.compile(r"상이|일부|(?:점포|매장|상점|업소|가게)\s*(?:별|마다)")
_LAST_ENTRY_RE =re.compile(r"\(\s*(?:입장|발권|매표|주문)\s*마감\s*\d{1,2}:\d{2}\s*\)")


def clean_text(value) -> str:
    """소개정보 문장에서 태그와 HTML 엔티티를 정리한다. <br> 은 " / " 로 바꾼다."""
    text = re.sub(r"<br\s*/?>", " / ", str(value or ""), flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = " ".join(text.split())
    return re.sub(r"^(/ )+|( /)+$", "", text).strip()


def parse_open_close(text: str) -> tuple[str | None, str | None]:
    """이용시간 문장 → ("HH:MM", "HH:MM"). 단순한 한 구간이 아니면 (None, None).

    조건: 시각 표기(HH:MM)가 "시작~끝" 한 쌍뿐이고, 그 밖에 숫자가 없고, 요일·계절 조건이 없고, 시작 < 끝 ≤ 23:59.
    "(입장 마감 17:30)" 같은 마감 안내는 빼고 본다.
    """
    text = _LAST_ENTRY_RE.sub("", text)
    ranges = _RANGE_RE.findall(text)
    if len(ranges) != 1 or len(_TIME_RE.findall(text)) != 2:
        return None, None
    if re.search(r"\d", _RANGE_RE.sub("", text)) or _CONDITION_RE.search(text):
        return None, None
    h1, m1, h2, m2 = map(int, ranges[0])
    if not (h1 <= 23 and h2 <= 23 and m1 <= 59 and m2 <= 59 and (h1, m1) < (h2, m2)):
        return None, None
    return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"


def parse_closed_weekdays(text: str) -> list[int]:
    """쉬는날 문장의 "매주 ○요일" → 요일 번호 목록(0=월). 그 밖의 표현은 읽지 않는다.

    "점포 별로 상이", "일부" 같은 단서가 붙어 있으면 장소 전체가 쉬는 날이 아니므로 빈 목록(원문은 raw_text 에 남는다).
    """
    if _PARTIAL_RE.search(text):
        return []
    return sorted({WEEKDAYS.index(day) for day in _WEEKLY_RE.findall(text)})


def build_entry(type_id: str, intro: dict) -> dict:
    """소개정보 항목 하나 → hours.json 의 장소 한 곳. 모르는 타입이면 전부 모르는 값."""
    use_field, rest_field = INTRO_FIELDS.get(type_id, (None, None))
    use, rest = clean_text(intro.get(use_field)), clean_text(intro.get(rest_field))
    opens, closes = parse_open_close(use)
    raw_text = "\n".join(f"{label}: {text}" for label, text in (("이용시간", use), ("쉬는날", rest)) if text)
    return {
        "opens": opens,
        "closes": closes,
        "closed_weekdays": parse_closed_weekdays(rest),
        "closed_dates": [],
        "raw_text": raw_text or None,
    }


def intro_item(saved: dict) -> dict:
    """저장된 detailIntro2 응답의 항목(1건). 없으면 빈 dict."""
    items = saved.get("response", {}).get("response", {}).get("body", {}).get("items")
    item = items.get("item", {}) if isinstance(items, dict) else {}
    return (item[0] if item else {}) if isinstance(item, list) else item


def dump_hours(source: dict, hours: dict[str, dict]) -> str:
    """hours.json 본문. 장소 하나를 한 줄로 쓴다."""
    rows = ",\n".join(f"    {json.dumps(pid)}: {json.dumps(entry, ensure_ascii=False)}" for pid, entry in hours.items())
    return json.dumps({"source": source}, ensure_ascii=False, indent=2)[:-2] + f',\n  "hours": {{\n{rows}\n  }}\n}}\n'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TourAPI detailIntro2 로 hours.json 생성")
    ap.add_argument("--offline", action="store_true", help="API 를 부르지 않고 저장된 raw 응답으로 다시 만든다")
    ap.add_argument("--refresh", action="store_true", help="저장된 응답이 있어도 전부 다시 받는다")
    args = ap.parse_args(argv)
    fp.OFFLINE, fp.REUSE_RAW = args.offline, not args.refresh
    if not args.offline and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING 이 비어 있습니다. backend/.env 를 확인하세요.", file=sys.stderr)
        return 1

    sources = fp.load_json(fp.SOURCES_PATH, {})
    hours: dict[str, dict] = {}
    for place in fp.load_json(fp.PLACES_PATH, []):
        pid = place["place_id"]
        contentid = sources.get(pid, {}).get("contentids", {}).get("ko")
        type_id = str(sources.get(pid, {}).get("kor_class", {}).get("contenttypeid") or "")
        raw_path = fp.RAW_DIR / pid / "ko_intro.json"
        before = fp.API_CALLS
        if pid in NOT_THE_PLACE:
            print(f"[건너뜀] {pid}: {NOT_THE_PLACE[pid]}")
            hours[pid] = dict(UNKNOWN)
            continue
        try:
            if not contentid or not type_id:
                raise fp.FetchError("국문 contentid 또는 contenttypeid 를 모릅니다")
            fp._call_and_save(fp.SERVICES["ko"], "detailIntro2", {"contentId": contentid, "contentTypeId": type_id}, raw_path)
            entry = build_entry(type_id, intro_item(fp.load_json(raw_path, {})))
        except fp.FetchError as e:
            print(f"[실패] {pid}: {e}")
            continue  # hours.json 에 없는 장소는 get_hours 가 모르는 값으로 돌려준다
        if type_id not in INTRO_FIELDS:
            print(f"[경고] {pid}: 관광타입 {type_id} 의 필드 이름을 모릅니다 (INTRO_FIELDS 에 추가)")
        hours[pid] = entry
        called = f" (API {fp.API_CALLS - before}회)" if fp.API_CALLS > before else ""
        print(f"[{type_id}] {pid}: {entry['opens']}~{entry['closes']} 휴무 {entry['closed_weekdays']}{called}")

    old_source = fp.load_json(OUT_PATH, {}).get("source", {})
    source = {
        "provider": "한국관광공사 TourAPI (공공데이터포털)",
        "api": f"{fp.SERVICES['ko']}/detailIntro2",
        "fields": {type_id: list(fields) for type_id, fields in INTRO_FIELDS.items()},
        "fetched_at": fp._today() if fp.API_CALLS or "fetched_at" not in old_source else old_source["fetched_at"],
    }
    OUT_PATH.write_text(dump_hours(source, hours), encoding="utf-8", newline="\n")

    timed = sum(1 for e in hours.values() if e["opens"])
    weekly = sum(1 for e in hours.values() if e["closed_weekdays"])
    text_only = sum(1 for e in hours.values() if e["raw_text"] and not e["opens"] and not e["closed_weekdays"])
    print(f"hours {len(hours)}곳 저장: opens·closes {timed}, closed_weekdays {weekly}, raw_text 만 {text_only}, "
          f"API 호출 {fp.API_CALLS}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
