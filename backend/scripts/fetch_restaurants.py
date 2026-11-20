"""기준 장소·역 주변 음식점(restaurants.json)을 한국관광공사 TourAPI 로 만든다. backend/ 에서 실행한다.

    uv run --env-file .env python -m scripts.fetch_restaurants              # 전부 호출한다
    uv run --env-file .env python -m scripts.fetch_restaurants --reuse-raw  # 저장된 응답은 다시 부르지 않고 없는 요청만 호출한다
    uv run python -m scripts.fetch_restaurants --offline                    # 호출 없이 저장된 raw 로 다시 만든다

입력
  scripts/restaurant_seeds.json  {"radius_m": 수집 반경, "place_ids": [places.json 의 place_id], "stations": [stations.json 의 역 이름]}
                                 새 장소 ID·역 이름을 만들지 않는다. 파일에 없는 값이 있으면 시작 전에 끝낸다.
조회 (2026-11-20 실제 응답으로 확인한 방식)
  국문   KorService2/areaBasedList2 (contentTypeId=39 음식점, lDongRegnCd=26 부산 전체, 약 510건)를 받아 기준 좌표에서
         radius_m 이내인 곳만 고른다. locationBasedList2 는 쓰지 않는다: 해운대해수욕장 500m 에서 1건만 돌려주는데
         같은 범위에 areaBasedList2 로는 5건 이상 있었다(좌표 조회가 항목을 빠뜨린다).
  외국어 Eng·Jpn·Chs·ChtService2/areaBasedList2 (contentTypeId=82, lDongRegnCd=26). 외국어 음식점 타입은 82 다
         (국문 39 와 번호가 다르다. 타입 없이 받은 응답에서 확인했다). fetch_places 와 같은 규칙(pick_foreign: 300m 이내에서
         한글·숫자 정규화 값이 같으면 exact, 짧은 쪽이 3글자 이상 포함되면 contains)으로 국문 음식점마다 이름을 찾는다.
         외국어 음식점은 부산 전체에 언어별 수십 건뿐이라 대부분의 음식점은 외국어 이름이 없다.
  메뉴   기준마다 가장 가까운 MENU_TOP_N 곳만 KorService2/detailIntro2(contentTypeId=39)의 firstmenu·treatmenu 원문을 받는다.
  한 요청은 ROWS 건씩 최대 MAX_PAGES 쪽. 모든 호출은 fetch_places 의 것(타임아웃 5초, 재시도 1회)을 쓴다.
출력
  app/data/restaurants.json        get_restaurants 가 읽는다 (app/tools/restaurants.py 의 RestaurantTable)
  app/data/restaurants_review.csv  외국어 이름을 찾지 못한 항목과 호출 실패 (사람이 검토)
  app/data/raw/restaurants/        API 원본 응답 (serviceKey 는 저장하지 않는다. raw 는 git 에 올리지 않는다)
음식점 한 곳
  restaurant_id  "kto-<국문 contentid>". places.json 의 place_id 가 아니다
  names          찾은 언어만. 못 찾은 언어는 비우고 review 에 사유를 남긴다
  cuisine        국문 분류 코드(lclsSystm3)를 CUISINE_BY_CLASS 로 바꾼 값. 표에 없는 코드는 null
  kor_class      국문 분류 코드 원본
  menu_raw       대표 메뉴 원문(태그만 정리). 받지 않았거나 비어 있으면 null
식단(할랄·채식 등), 영업시간, 가격, 평점은 넣지 않는다. 값을 지어내지 않는다.
"""
import argparse
import csv
import re
import sys

from app import config
from app.tools.restaurants import RestaurantTable, dump_restaurants
from scripts import fetch_hours as fh
from scripts import fetch_places as fp
from scripts.fetch_events import festival_items as raw_items  # 응답의 원본 항목 목록 (0건·1건 형식 처리)

REGION_CODE = "26"  # 법정동 시도 코드: 부산광역시
TYPE_IDS = {"ko": "39", "en": "82", "ja": "82", "zh-Hans": "82", "zh-Hant": "82"}  # 서비스별 음식점 관광타입
ROWS = 100
MAX_PAGES = 10
MENU_TOP_N = 5  # 기준마다 메뉴(detailIntro2)를 받을 가까운 음식점 수
RAW_DIR = fp.RAW_DIR / "restaurants"
OUT_PATH = fp.DATA_DIR / "restaurants.json"
REVIEW_PATH = fp.DATA_DIR / "restaurants_review.csv"
SEEDS_PATH = fp.SCRIPTS_DIR / "restaurant_seeds.json"
STATIONS_PATH = fp.DATA_DIR / "stations.json"
REVIEW_FIELDS = ["anchor", "restaurant_id", "name_ko", "lang", "reason", "candidates"]
KOR_CLASS_KEYS = ("lclsSystm1", "lclsSystm2", "lclsSystm3")
NOTE = ("한국관광공사 TourAPI 음식점 정보를 scripts/fetch_restaurants.py 로 미리 받아 만든 파일이다. "
        "식단·영업시간·가격은 없다. restaurant_id 는 place_id 가 아니다.")
# 국문 분류 코드(lclsSystm3) → cuisine. 코드 이름은 KorService2/lclsSystmCode2(lclsSystm1=FD) 응답으로 확인했다 (2026-11-20).
# 표에 없는 코드는 null 이다.
CUISINE_BY_CLASS: dict[str, str] = {
    "FD010100": "korean",  # 한식 > 관광식당
    "FD010200": "korean",  # 한식 > 모범음식점
    "FD020100": "chinese",  # 외국식 > 중식
    "FD020200": "japanese",  # 외국식 > 일식
    "FD020300": "western",  # 외국식 > 서양식
    "FD020400": "other",  # 외국식 > 기타외국식
    "FD020500": "other",  # 외국식 > 퓨전음식
    "FD030100": "other",  # 간이음식 > 제과
    "FD030200": "other",  # 간이음식 > 피자, 햄버거, 샌드위치 및 유사음식
    "FD030300": "other",  # 간이음식 > 치킨
    "FD030400": "other",  # 간이음식 > 김밥 분식
    "FD030500": "other",  # 간이음식 > 이동음식
    "FD030600": "other",  # 간이음식 > 기타간이음식
    "FD040100": "other",  # 주점 > 바/펍
    "FD040200": "other",  # 주점 > 생맥주전문점
    "FD040300": "other",  # 주점 > 클럽
    "FD040400": "other",  # 주점 > 전통주/민속주점
    "FD040500": "other",  # 주점 > 기타주점
    "FD050100": "cafe",  # 카페/찻집 > 카페
    "FD050200": "cafe",  # 카페/찻집 > 찻집
    "FD050300": "cafe",  # 카페/찻집 > 기타음료점
}


def load_anchors(seeds: dict, places: list[dict], stations: list[dict]) -> list[dict]:
    """시드 → 기준 목록 [{"kind": "place" | "station", "name", "lat", "lng"}]. 파일에 없는 값이 있으면 ValueError."""
    by_place = {p["place_id"]: p for p in places}
    by_station = {s["station"]: s for s in stations}
    unknown = [n for n in seeds.get("place_ids", []) if n not in by_place] + \
              [n for n in seeds.get("stations", []) if n not in by_station]
    if unknown:
        raise ValueError(f"시드에 places.json·stations.json 에 없는 값이 있습니다: {', '.join(unknown)}")
    return [{"kind": "place", "name": n, "lat": by_place[n]["lat"], "lng": by_place[n]["lng"]}
            for n in seeds.get("place_ids", [])] + \
           [{"kind": "station", "name": n, "lat": by_station[n]["lat"], "lng": by_station[n]["lng"]}
            for n in seeds.get("stations", [])]


def anchor_key(anchor: dict) -> str:
    """review 의 anchor 열. 역은 "station-<이름>"."""
    return anchor["name"] if anchor["kind"] == "place" else f"station-{anchor['name']}"


def fetch_pages(lang: str) -> tuple[list[dict], list[dict]]:
    """그 언어 서비스의 부산 음식점 전체를 쪽마다 받아 (좌표가 있는 항목, 원본 항목)을 돌려준다. 원본 응답은 raw 에 남긴다."""
    items, originals, total = [], [], 0
    for page in range(1, MAX_PAGES + 1):
        extra = {"contentTypeId": TYPE_IDS[lang], "lDongRegnCd": REGION_CODE, "arrange": "C", "numOfRows": ROWS, "pageNo": page}
        raw_path = RAW_DIR / f"{lang}_p{page}.json"
        items += fp._call_and_save(fp.SERVICES[lang], "areaBasedList2", extra, raw_path)
        response = fp.load_json(raw_path, {})["response"]
        originals += raw_items(response)
        total = int(response.get("response", {}).get("body", {}).get("totalCount") or 0)
        if page * ROWS >= total:
            break
    else:
        print(f"[경고] {lang}: totalCount {total} 가 {MAX_PAGES}쪽({MAX_PAGES * ROWS}건)을 넘습니다. MAX_PAGES 를 늘리세요.")
    return items, originals


def fetch_menu(contentid: str) -> str | None:
    """detailIntro2 의 대표 메뉴(firstmenu)와 취급 메뉴(treatmenu) 원문. 둘 다 없으면 None."""
    raw_path = RAW_DIR / "_intro" / f"{contentid}.json"
    fp._call_and_save(fp.SERVICES["ko"], "detailIntro2", {"contentId": contentid, "contentTypeId": TYPE_IDS["ko"]}, raw_path)
    intro = fh.intro_item(fp.load_json(raw_path, {}))
    first, treat = (fh.clean_text(intro.get(key)) for key in ("firstmenu", "treatmenu"))
    if first in [part.strip() for part in re.split(r"[/,]", treat)]:  # 취급 메뉴의 한 항목이 대표 메뉴와 같으면 한 번만 적는다
        first = ""  # 글자가 포함되는지만 보면 안 된다: "삼계탕" 은 "전복삼계탕" 과 다른 메뉴다
    return " / ".join(text for text in (first, treat) if text) or None


def build_record(kor: dict, original: dict, foreign: dict[str, list[dict]], menu: str | None) -> tuple[dict, list[dict]]:
    """국문 음식점 한 곳 → (restaurants.json 의 한 곳, review 행). foreign 은 언어별 외국어 후보(호출이 실패한 언어는 없다)."""
    names, review = {}, []
    for lang in fp.NAME_LANGS:
        if lang not in foreign:
            continue  # 그 언어 호출이 실패했다. api_error 로 한 번만 남긴다
        item, reason, near = fp.pick_foreign(kor, foreign[lang])
        if item:
            names[lang] = item["name"]
        else:
            review.append({"lang": lang, "reason": reason, "candidates": fp._fmt_candidates(near)})
    kor_class = {key: (str(original[key]) if original.get(key) else None) for key in KOR_CLASS_KEYS}
    record = {
        "restaurant_id": f"kto-{kor['contentid']}",
        "name_ko": kor["title"].strip(),
        "names": names,
        "lat": kor["lat"],
        "lng": kor["lng"],
        "address_ko": kor["addr1"].strip(),
        "cuisine": CUISINE_BY_CLASS.get(kor_class["lclsSystm3"] or ""),
        "kor_class": kor_class,
        "menu_raw": menu,
    }
    return record, [{"restaurant_id": record["restaurant_id"], "name_ko": record["name_ko"], **row} for row in review]


def collect(anchors: list[dict], radius_m: int) -> tuple[dict, list[dict]]:
    """받아서 (RestaurantTable 에 넣을 dict, review 행)을 만든다. note·collected_at 은 main 이 채운다.

    국문 호출이 실패하면 FetchError 를 그대로 올린다(만들 수 있는 것이 없다). 외국어·메뉴 호출 실패는 review 에 남기고 계속한다.
    """
    review: list[dict] = []
    kor_items, kor_raws = fetch_pages("ko")
    originals = {str(r.get("contentid")): r for r in kor_raws}
    foreign: dict[str, list[dict]] = {}
    for lang in fp.NAME_LANGS:
        try:
            foreign[lang] = fetch_pages(lang)[0]
        except fp.FetchError as e:
            print(f"[실패] {lang}: {e}")
            review.append({"anchor": "*", "lang": lang, "reason": f"api_error: {e}"})

    nearby: dict[str, list[dict]] = {}  # 기준마다 반경 안의 국문 음식점, 가까운 순
    for anchor in anchors:
        measured = [(fp.haversine_m(anchor["lat"], anchor["lng"], k["lat"], k["lng"]), k["contentid"], k) for k in kor_items]
        nearby[anchor_key(anchor)] = [k for dist, _, k in sorted(measured, key=lambda m: m[:2]) if dist <= radius_m]

    menus: dict[str, str | None] = {}
    for key, found in nearby.items():  # 기준마다 가까운 MENU_TOP_N 곳만 메뉴를 받는다
        for kor in found[:MENU_TOP_N]:
            if kor["contentid"] in menus:
                continue
            try:
                menus[kor["contentid"]] = fetch_menu(kor["contentid"])
            except fp.FetchError as e:
                print(f"[실패] 메뉴 {kor['contentid']} {kor['title']}: {e}")
                review.append({"anchor": key, "restaurant_id": f"kto-{kor['contentid']}", "name_ko": kor["title"],
                               "lang": "ko", "reason": f"api_error: {e}"})

    records: dict[str, dict] = {}
    groups: dict[str, dict[str, list[str]]] = {"place": {}, "station": {}}
    for anchor in anchors:
        key = anchor_key(anchor)
        for kor in nearby[key]:
            rid = f"kto-{kor['contentid']}"
            if rid in records:  # 다른 기준 반경에도 걸친 음식점은 한 번만 저장한다
                continue
            records[rid], rows = build_record(kor, originals.get(kor["contentid"], {}), foreign, menus.get(kor["contentid"]))
            review += [{"anchor": key, **row} for row in rows]
        groups[anchor["kind"]][anchor["name"]] = [f"kto-{kor['contentid']}" for kor in nearby[key]]
    table = {"radius_m": radius_m, "anchors": groups["place"], "station_anchors": groups["station"],
             "restaurants": list(records.values())}
    return table, review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TourAPI areaBasedList2 로 restaurants.json 생성")
    ap.add_argument("--offline", action="store_true", help="API 를 부르지 않고 저장된 raw 응답으로 다시 만든다")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="raw 에 같은 요청의 응답이 있으면 다시 부르지 않고, 없는 요청만 호출한다")
    args = ap.parse_args(argv)
    fp.OFFLINE, fp.REUSE_RAW = args.offline, args.reuse_raw
    if not args.offline and not config.DATA_GO_KR_KEY:
        print("DATA_GO_KR_KEY_DECODING 이 비어 있습니다. backend/.env 를 확인하세요.", file=sys.stderr)
        return 1
    seeds = fp.load_json(SEEDS_PATH, {})
    try:
        anchors = load_anchors(seeds, fp.load_json(fp.PLACES_PATH, []), fp.load_json(STATIONS_PATH, {}).get("stations", []))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    calls_before = fp.API_CALLS
    try:
        data, review = collect(anchors, int(seeds["radius_m"]))
    except fp.FetchError as e:
        print(f"국문 음식점 조회 실패: {e}", file=sys.stderr)
        return 1
    collected_at = fp.load_json(OUT_PATH, {}).get("collected_at") if args.offline else None
    table = RestaurantTable(note=NOTE, collected_at=collected_at or fp._today(), **data)  # 형식이 틀리면 여기서 멈춘다
    OUT_PATH.write_text(dump_restaurants(table), encoding="utf-8", newline="\n")
    with REVIEW_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, restval="", lineterminator="\n")
        writer.writeheader()
        writer.writerows(review)

    print(f"음식점 {len(table.restaurants)}곳 저장 ({OUT_PATH.name}, 반경 {table.radius_m}m)")
    for name, ids in [*table.anchors.items(), *((f"station {n}", ids) for n, ids in table.station_anchors.items())]:
        print(f"  {name}: {len(ids)}곳")
    named = {lang: sum(lang in r.names for r in table.restaurants) for lang in fp.NAME_LANGS}
    print(f"외국어 이름 {named}, cuisine 있음 {sum(r.cuisine is not None for r in table.restaurants)}곳, "
          f"menu_raw 있음 {sum(r.menu_raw is not None for r in table.restaurants)}곳")
    print(f"검토 필요 {len(review)}건 ({REVIEW_PATH.name}), API 호출 {fp.API_CALLS - calls_before}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
