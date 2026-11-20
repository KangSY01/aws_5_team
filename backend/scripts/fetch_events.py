"""부산 행사 목록(events.json)을 한국관광공사 TourAPI 로 만든다. backend/ 에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_events
        # 국문과 외국어 4개 서비스의 searchFestival2를 언어별 1회 호출한다
    uv run python -m scripts.fetch_events --offline          # 호출 없이 저장된 raw 로 다시 만든다 (places.json 이 바뀌었을 때)
    uv run --env-file .env python -m scripts.fetch_events --reuse-raw   # 저장된 응답은 다시 부르지 않고 없는 요청만 호출한다

조회 조건: 법정동 시도 코드 26(부산), 기간이 2026-11-01 ~ 2026-11-30 과 겹치는 행사.
외국어 이름은 Eng·Jpn·Chs·ChtService2/searchFestival2 전체 응답에서 fetch_places와 같은 한국어 제목·거리 규칙으로 찾는다.
PLAYTIME_CONTENT_IDS 의 행사는 KorService2/detailIntro2(contentTypeId=15)를 행사당 1회 더 호출해 행사 시간(playtime)을 확인한다.
출력
  app/data/events.json                             get_events와 GET /events가 읽는 목록
  app/data/raw/_events/searchFestival2*.json       언어별 API 원본 응답 (serviceKey 는 저장하지 않는다)
  app/data/raw/_events/detailIntro2_<contentid>.json  행사 시간 원본 응답
events.json 의 행사 한 건
  name      API 의 title (한국어 원문)
  names     ko와 TourAPI에서 일치한 외국어 이름만. 못 찾은 언어는 생략
  type      TourAPI 원본 분류를 festival/performance/exhibition/event 중 하나로 변환
  start·end 행사 기간 첫날 00:00:00, 마지막 날 23:59:59 (+09:00). 행사 목록 API 는 날짜만 준다.
            행사 시간 원문이 "18:00~23:00" 같은 단순한 한 구간이면 첫날 18:00:00, 마지막 날 23:00:00 으로 쓴다
  playtime_raw  행사 시간 원문 (확인한 행사만)
  place_ids 행사 좌표에서 직선거리 1km 이내인 places.json 장소. 좌표가 없으면 빈 목록
  main_place_id  place_ids 중 행사 좌표와 직선거리가 가장 가까운 장소 (같은 거리면 place_id 사전순). place_ids 가 비면 null
  contentid, addr1, lat, lng  출처 확인용
API 에 없는 행사는 넣지 않는다. 값을 지어내지 않는다.
"""
import argparse
import datetime as dt
import json
import sys

from app import config
from scripts import fetch_hours as fh
from scripts import fetch_places as fp

REGION_CODE = "26"  # 법정동 시도 코드: 부산광역시
PERIOD = ("20261101", "20261130")
EVENT_RADIUS_M = 1000  # 행사 좌표에서 이 거리 안의 장소를 place_ids 에 넣는다
ROWS = 300
# 행사 시간(playtime)을 소개정보(detailIntro2)로 확인할 행사의 국문 contentid. 행사당 1회 호출한다.
PLAYTIME_CONTENT_IDS = ("2048902",)  # 해운대 빛축제 (데모일 2026-11-28 개막)
FESTIVAL_TYPE_ID = "15"  # 국문 관광타입: 축제공연행사
RAW_PATH = fp.RAW_DIR / "_events" / "searchFestival2.json"
OUT_PATH = fp.DATA_DIR / "events.json"
# TourAPI 신분류. EV01=축제, EV02=공연, EV03=행사이며 EV0302는 전시·박람회다.
# 신분류가 없는 예전 응답은 cat2·cat3의 축제공연행사 분류를 쓴다.
EXHIBITION_OLD_CODES = {"A02080500", "A02080600"}
PERFORMANCE_OLD_CODES = {
    "A02080100", "A02080200", "A02080300", "A02080400", "A02080800", "A02080900", "A02081000",
}


def classify_event(item: dict) -> str:
    """TourAPI 원본 분류만으로 지도 레이어의 네 가지 행사 유형을 정한다."""
    lcls2 = str(item.get("lclsSystm2") or "").upper()
    lcls3 = str(item.get("lclsSystm3") or "").upper()
    if lcls2.startswith("EV01"):
        return "festival"
    if lcls2.startswith("EV02"):
        return "performance"
    if lcls3.startswith("EV0302"):
        return "exhibition"
    if lcls2.startswith("EV03"):
        return "event"

    cat2 = str(item.get("cat2") or "").upper()
    cat3 = str(item.get("cat3") or "").upper()
    if cat2 == "A0207":
        return "festival"
    if cat3 in EXHIBITION_OLD_CODES:
        return "exhibition"
    if cat3 in PERFORMANCE_OLD_CODES:
        return "performance"
    return "event"


def _event_candidate(item: dict) -> dict | None:
    """외국어 이름 일치에 쓸 fetch_places 후보 형식. 좌표가 없으면 일치시키지 않는다."""
    try:
        return {
            "contentid": str(item["contentid"]),
            "title": str(item["title"]).strip(),
            "addr1": str(item.get("addr1", "")),
            "lat": float(item["mapy"]),
            "lng": float(item["mapx"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def match_event_names(items: list[dict], foreign: dict[str, list[dict]]) -> dict[str, dict[str, str]]:
    """국문 행사별 외국어 이름. fetch_places의 한국어 제목·거리 일치 규칙을 그대로 쓴다."""
    matched: dict[str, dict[str, str]] = {}
    for raw in items:
        kor = _event_candidate(raw)
        if kor is None:
            continue
        names: dict[str, str] = {}
        for lang in fp.NAME_LANGS:
            if lang not in foreign:
                continue
            item, _, _ = fp.pick_foreign(kor, foreign[lang], fp.MATCH_RADIUS_M)
            if item is None:
                item, _, _ = fp.pick_foreign(kor, foreign[lang], fp.FALLBACK_RADIUS_M)
            if item is not None:
                names[lang] = item["name"]
        matched[kor["contentid"]] = names
    return matched


def fetch_foreign_candidates(params: dict) -> dict[str, list[dict]]:
    """외국어 searchFestival2를 언어별 한 번씩 호출한다. 실패한 언어는 결과에서 뺀다."""
    foreign: dict[str, list[dict]] = {}
    for lang in fp.NAME_LANGS:
        raw_path = RAW_PATH.parent / f"searchFestival2_{lang}.json"
        try:
            foreign[lang] = fp._call_and_save(fp.SERVICES[lang], "searchFestival2", params, raw_path)
        except fp.FetchError as e:
            # 못 받은 언어는 비운다. 다른 언어와 국문 행사 데이터는 계속 만든다.
            print(f"[경고] 행사 외국어 이름 조회 실패 ({lang}): {e}")
    return foreign


def festival_items(data: dict) -> list[dict]:
    """searchFestival2 응답의 항목 목록. 0건이면 items 가 빈 문자열, 1건이면 item 이 dict 로 온다."""
    items = data.get("response", {}).get("body", {}).get("items")
    raw = items.get("item", []) if isinstance(items, dict) else []
    return [raw] if isinstance(raw, dict) else raw


def build_events(items: list[dict], places: list[dict], playtimes: dict[str, str] | None = None,
                 foreign_names: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """API 항목 → events.json의 행사 목록(시작일, 이름 순). 날짜를 읽을 수 없는 항목은 뺀다."""
    events = []
    for item in items:
        try:
            start = dt.datetime.strptime(str(item["eventstartdate"]), "%Y%m%d").date()
            end = dt.datetime.strptime(str(item["eventenddate"]), "%Y%m%d").date()
            name = str(item["title"]).strip()
        except (KeyError, ValueError):
            continue
        if not name or end < start:
            continue
        try:
            lat, lng = float(item["mapy"]), float(item["mapx"])
        except (KeyError, TypeError, ValueError):
            lat = lng = None
        dist = {} if lat is None else {p["place_id"]: fp.haversine_m(lat, lng, p["lat"], p["lng"]) for p in places}
        near = [pid for pid, d in dist.items() if d <= EVENT_RADIUS_M]
        contentid = str(item.get("contentid", ""))
        playtime = (playtimes or {}).get(contentid, "")
        names = {"ko": name, **(foreign_names or {}).get(contentid, {})}
        # 행사 시간 원문이 단순한 한 구간("18:00~23:00")일 때만 시각을 넣는다. 애매하면 날짜만 쓴다
        opens, closes = fh.parse_open_close(playtime)
        events.append({
            "name": name,
            "names": names,
            "type": classify_event(item),
            "start": f"{start.isoformat()}T{opens or '00:00'}:00+09:00",
            "end": f"{end.isoformat()}T{closes + ':00' if closes else '23:59:59'}+09:00",
            "place_ids": near,
            # 행사 대표 장소: place_ids 중 행사 좌표와 가장 가까운 곳 (같은 거리면 place_id 사전순, 없으면 null)
            "main_place_id": min(near, key=lambda pid: (dist[pid], pid), default=None),
            "contentid": contentid,
            "addr1": str(item.get("addr1", "")),
            "lat": lat,
            "lng": lng,
            **({"playtime_raw": playtime} if playtime else {}),
        })
    return sorted(events, key=lambda e: (e["start"][:10], e["name"]))  # 시각을 넣어도 순서는 날짜 기준 그대로


def dump_events(source: dict, events: list[dict]) -> str:
    """events.json 본문. 행사 하나를 한 줄로 쓴다."""
    rows = ",\n".join("    " + json.dumps(e, ensure_ascii=False) for e in events)
    body = f'  "events": [\n{rows}\n  ]\n' if events else '  "events": []\n'
    return json.dumps({"source": source}, ensure_ascii=False, indent=2)[:-2] + ",\n" + body + "}\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TourAPI searchFestival2 로 events.json 생성")
    ap.add_argument("--offline", action="store_true", help="API 를 부르지 않고 저장된 raw 응답으로 다시 만든다")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="raw 에 같은 요청의 응답이 있으면 다시 부르지 않고, 없는 요청만 호출한다")
    args = ap.parse_args(argv)
    fp.OFFLINE, fp.REUSE_RAW = args.offline, args.reuse_raw
    if not args.offline and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING 이 비어 있습니다. backend/.env 를 확인하세요.", file=sys.stderr)
        return 1

    params = {"eventStartDate": PERIOD[0], "eventEndDate": PERIOD[1], "lDongRegnCd": REGION_CODE, "numOfRows": ROWS}
    try:
        fp._call_and_save(fp.SERVICES["ko"], "searchFestival2", params, RAW_PATH)
    except fp.FetchError as e:
        print(f"행사 조회 실패: {e}", file=sys.stderr)
        return 1
    data = json.loads(RAW_PATH.read_text(encoding="utf-8"))["response"]
    items = festival_items(data)
    total = data.get("response", {}).get("body", {}).get("totalCount")

    foreign = fetch_foreign_candidates(params)
    foreign_names = match_event_names(items, foreign)

    playtimes = {}
    for contentid in PLAYTIME_CONTENT_IDS:
        raw_path = RAW_PATH.parent / f"detailIntro2_{contentid}.json"
        try:
            fp._call_and_save(fp.SERVICES["ko"], "detailIntro2",
                              {"contentId": contentid, "contentTypeId": FESTIVAL_TYPE_ID}, raw_path)
        except fp.FetchError as e:
            print(f"[경고] 행사 시간 조회 실패 (contentid {contentid}): {e}")
            continue
        playtimes[contentid] = fh.clean_text(fh.intro_item(fp.load_json(raw_path, {})).get("playtime"))
    events = build_events(items, fp.load_json(fp.PLACES_PATH, []), playtimes, foreign_names)

    fetched_at = fp.load_json(OUT_PATH, {}).get("source", {}).get("fetched_at") if args.offline else None
    source = {
        "provider": "한국관광공사 TourAPI (공공데이터포털)",
        "api": f"{fp.SERVICES['ko']}/searchFestival2",
        "foreign_apis": {lang: f"{fp.SERVICES[lang]}/searchFestival2" for lang in fp.NAME_LANGS},
        "params": params,
        "place_radius_m": EVENT_RADIUS_M,
        "name_match": (
            f"fetch_places 규칙: 제목의 한국어·숫자 일치, {fp.MATCH_RADIUS_M}m 우선·{fp.FALLBACK_RADIUS_M}m 보충"
        ),
        "fetched_at": fetched_at or fp._today(),
    }
    OUT_PATH.write_text(dump_events(source, events), encoding="utf-8", newline="\n")

    print(f"응답 {len(items)}건(totalCount={total}) → 행사 {len(events)}건 저장 ({OUT_PATH.name})")
    if total is not None and int(total) > len(items):
        print(f"[경고] totalCount 가 받은 건수보다 많습니다. ROWS({ROWS})를 늘려 다시 받으세요.")
    for e in events:
        print(f"  {e['start'][:10]} ~ {e['end'][:10]}  {e['name']}  {e['place_ids']}  대표 {e['main_place_id']}")
        if "playtime_raw" in e:
            print(f"    행사 시간 원문: {e['playtime_raw']!r} → start {e['start']}, end {e['end']}")
    names_count = {lang: sum(lang in e["names"] for e in events) for lang in fp.NAME_LANGS}
    print(f"외국어 이름 {names_count}")
    print(f"API 호출 {fp.API_CALLS}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
