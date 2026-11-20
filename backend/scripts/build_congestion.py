"""관광지 집중률 원본에서 우리 장소만 뽑아 congestion.json 을 만든다. backend/ 에서 실행한다.

    uv run python -m scripts.build_congestion

API 를 부르지 않는다. 원본은 한국관광공사 TatsCnctrRateService/tatsCnctrRatedList 를 부산 구·군별로 받은 파일이다.
입력
  app/data/raw/congestion_busan.json  {구·군 코드: [{baseYmd, signguCd, tAtsNm, cnctrRate(문자열), ...}]} (git 에 올리지 않는다)
  app/data/places.json                여기 없는 place_id 는 건너뛴다
출력
  app/data/congestion.json  {"meta": 출처·기간, "places": {place_id: {"YYYY-MM-DD": 집중률}}}. get_crowd 가 읽는다

장소 연결은 PLACE_NAMES 표의 이름(tAtsNm)과 정확히 같은 항목만 쓴다. 비슷한 이름을 자동으로 찾지 않는다.
집중률(cnctrRate)은 그 장소 자신의 최고 시기를 100 으로 둔 상대값이다. 장소끼리 비교하지 않는다.
"""
import datetime as dt
import json
import sys

from scripts import fetch_places as fp

RAW_PATH = fp.RAW_DIR / "congestion_busan.json"
OUT_PATH = fp.DATA_DIR / "congestion.json"
API = "TatsCnctrRateService/tatsCnctrRatedList"

# place_id → 집중률 원본의 관광지 이름(tAtsNm). 정확히 같은 이름만 쓴다.
PLACE_NAMES = {
    "haeundae-beach": "해운대해수욕장",
    "gwangalli-beach": "광안리해수욕장",
    "jagalchi-market": "부산 자갈치시장",
    "gukje-market": "국제시장",
    "taejongdae": "태종대 (부산 국가지질공원)",
    "beomeosa-temple": "범어사(부산)",
    "dongbaekseom": "해운대 동백섬",
    "the-bay-101": "더베이101",
    "haeundae-market": "부산 해운대시장",
    "cheongsapo-skywalk": "청사포 다릿돌전망대",
    "sea-life-busan": "SEA LIFE 부산아쿠아리움",
    "songjeong-beach": "송정해수욕장",
    "busan-museum-of-art": "부산시립미술관",
    "millak-waterside-park": "민락수변공원",
    "lotte-world-busan": "롯데월드 어드벤처 부산",
    "biff-square": "BIFF 광장",
    "yongdusan-park": "용두산공원",
    "songdo-cable-car": "부산 송도해상케이블카",
    "national-maritime-museum": "국립해양박물관",
    "busan-chinatown": "부산 차이나타운특구(상해문.상해거리)",
    "busan-museum": "부산박물관",
    "busan-citizens-park": "부산시민공원",
    "jeonpo-cafe-street": "전포카페거리",
}


def build_congestion(raw: dict[str, list[dict]], place_ids: list[str]) -> dict[str, dict[str, float]]:
    """원본 → {place_id: {"YYYY-MM-DD": 집중률}}. place_ids(places.json 순서) 중 PLACE_NAMES 에 있고 원본에 값이 있는 곳만.

    날짜·값을 읽을 수 없는 항목은 버린다. 같은 장소·날짜에 다른 값이 두 번 나오면(이름이 같은 다른 관광지) ValueError.
    """
    wanted = {PLACE_NAMES[pid]: pid for pid in place_ids if pid in PLACE_NAMES}
    found: dict[str, dict[str, float]] = {}
    for rows in raw.values():
        for row in rows:
            pid = wanted.get(row.get("tAtsNm"))
            if pid is None:
                continue
            try:
                day = dt.datetime.strptime(str(row["baseYmd"]), "%Y%m%d").date().isoformat()
                rate = float(row["cnctrRate"])
            except (KeyError, TypeError, ValueError):
                continue
            if found.setdefault(pid, {}).setdefault(day, rate) != rate:
                raise ValueError(f"{row['tAtsNm']} {day}: 값이 둘입니다. 이름이 같은 관광지가 여러 구·군에 있는지 확인하세요")
    return {pid: dict(sorted(found[pid].items())) for pid in place_ids if pid in found}


def dump_congestion(meta: dict, places: dict[str, dict[str, float]]) -> str:
    """congestion.json 본문. 장소 하나를 한 줄로 쓴다."""
    rows = ",\n".join(f"    {json.dumps(pid)}: {json.dumps(days)}" for pid, days in places.items())
    return json.dumps({"meta": meta}, ensure_ascii=False, indent=2)[:-2] + f',\n  "places": {{\n{rows}\n  }}\n}}\n'


def main() -> int:
    if not RAW_PATH.exists():
        print(f"원본이 없습니다: {RAW_PATH} ({API} 로 받은 파일을 여기에 둡니다)", file=sys.stderr)
        return 1
    place_ids = [p["place_id"] for p in fp.load_json(fp.PLACES_PATH, [])]
    places = build_congestion(json.loads(RAW_PATH.read_text(encoding="utf-8")), place_ids)
    days = sorted({day for values in places.values() for day in values})
    meta = {
        "provider": "한국관광공사 관광지 집중률 (공공데이터포털)",
        "api": API,
        "period": {"start": days[0], "end": days[-1]} if days else None,
        "note": "집중률은 장소마다 자기 최고 시기를 100 으로 둔 상대값이다. 서로 다른 장소의 값을 비교하지 않는다.",
        "names": {pid: PLACE_NAMES[pid] for pid in places},
    }
    OUT_PATH.write_text(dump_congestion(meta, places), encoding="utf-8", newline="\n")

    for pid in PLACE_NAMES:
        if pid not in place_ids:
            print(f"[건너뜀] {pid}: places.json 에 없습니다")
        elif pid not in places:
            print(f"[경고] {pid}: 원본에 '{PLACE_NAMES[pid]}' 이름의 항목이 없습니다")
    period = f"{days[0]} ~ {days[-1]}" if days else "없음"
    print(f"congestion {len(places)}곳 저장 ({OUT_PATH.name}): 기간 {period}, "
          f"집중률 없는 장소 {[pid for pid in place_ids if pid not in places]}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
