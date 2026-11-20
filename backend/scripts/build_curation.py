"""장소별 큐레이션(curation.json)을 규칙으로 만든다. backend/ 에서 실행한다.

    uv run python -m scripts.build_curation

API 를 부르지 않는다. places.json·travel_times.json 이 바뀌면 다시 실행한다
(tests/test_build_curation.py 가 파일이 규칙 결과와 같은지 확인한다).
입력
  app/data/places.json, app/data/travel_times.json, app/data/curation_overrides.json,
  app/data/places_sources.json (kor_class: TourAPI 국문 분류 lclsSystm1·2)
출력
  app/data/curation.json  {place_id: {...}}. get_place_info 가 읽는다
장소 한 곳
  tags                TAGS 중 해당하는 것. category(CATEGORY_TAGS) + TourAPI 분류(LCLS_TAGS) + 실내면 "indoor"
  foreigner_friendly  0~3. 다국어 관광정보 제공 언어 수 기준: places.json names 에 영어·일본어·중국어(간체나 번체 중 하나)
                      이름이 있는 언어의 수. 한국관광공사 다국어 관광정보에 그 장소가 실린 언어 수이지,
                      현장의 외국어 안내 수준을 조사한 값이 아니다
  crowd_alternatives  붐빌 때 대신 갈 후보. 이동 시간 MAX_MINUTES 이내이고 indoor 를 뺀 tags 가 하나 이상 겹치는 장소,
                      가까운 순 MAX_ALTERNATIVES 곳
  rain_alternatives   비 올 때 대신 갈 후보. 이동 시간 MAX_MINUTES 이내의 실내(indoor=true) 장소, 가까운 순 MAX_ALTERNATIVES 곳.
                      RAIN_EXCLUDED(대형 상업·유료 시설)는 후보에서 뺀다
  source              "rule"(이 스크립트가 만든 값) 또는 "manual"(curation_overrides.json 으로 고친 항목)
이동 시간은 travel_times.json 의 추정값이다. 같은 시간이면 place_id 사전순.

사람이 고치는 방법: curation_overrides.json 에 {"<place_id>": {"tags": [...], "rain_alternatives": [...]}} 처럼
바꿀 필드만 적고 다시 실행한다. 적은 필드가 규칙 결과를 덮어쓰고 그 장소의 source 가 "manual" 이 된다.
"""
import json
import sys

from scripts import fetch_places as fp

OUT_PATH = fp.DATA_DIR / "curation.json"
OVERRIDES_PATH = fp.DATA_DIR / "curation_overrides.json"
TRAVEL_PATH = fp.DATA_DIR / "travel_times.json"
MAX_MINUTES = 30
MAX_ALTERNATIVES = 3
# 비 대안 후보에서 빼는 장소. 대형 상업·유료 시설(유료 수족관, 유료 전망대, 백화점)이라 비 올 때마다
# 이곳들만 추천되는 것을 막는다. 후보에서만 빼고, 이 장소 자체의 항목과 crowd_alternatives·tags 는 그대로다.
RAIN_EXCLUDED = frozenset({"sea-life-busan", "busan-x-the-sky", "shinsegae-centum-city"})
FIELDS = ("tags", "foreigner_friendly", "crowd_alternatives", "rain_alternatives")

TAGS = ["food", "sea", "history", "culture", "shopping", "nature", "night_view", "kids", "indoor"]  # 출력 순서
# places.json 의 category → 태그
CATEGORY_TAGS = {
    "beach": ["sea", "nature"],
    "market": ["food", "shopping"],
    "village": ["culture"],
    "observatory": ["night_view"],
    "temple": ["history", "culture"],
    "park": ["nature"],
    "shopping": ["shopping"],
    "museum": ["culture"],
    "street": ["culture"],
    "aquarium": ["kids"],
    "theme_park": ["kids"],
    "attraction": [],  # 성격이 제각각이라 TourAPI 분류로만 정한다
    "culture": ["culture"],
}
# TourAPI 국문 분류 코드(lclsSystm1, lclsSystm2) → 태그. 주석은 places_sources.json 에서 그 코드가 붙어 있는 장소.
LCLS_TAGS = {
    "NA": ["nature"],  # 해수욕장, 동백섬, 태종대, 용두산공원
    "NA02": ["sea"],  # 해운대·광안리·송정해수욕장, 동백섬, 태종대
    "HS": ["history"],  # 범어사, 해동용궁사, 부산타워
    "SH": ["shopping"],  # 시장, 백화점, 아울렛
    "VE01": ["night_view"],  # 부산엑스더스카이, 청사포 다릿돌전망대, 더베이101
    "VE02": ["kids"],  # 롯데월드 어드벤처 부산, 씨라이프부산아쿠아리움, 해운대 블루라인파크
    "VE07": ["culture"],  # 박물관, 미술관
}
ZH = ("zh-Hans", "zh-Hant")


def place_tags(place: dict, lcls_codes: list[str]) -> list[str]:
    """category, TourAPI 분류 코드, indoor 로 정한 태그 (TAGS 순서)."""
    found = set(CATEGORY_TAGS.get(place["category"], []))
    for code in lcls_codes:
        found.update(LCLS_TAGS.get(code, []))
    if place["indoor"]:
        found.add("indoor")
    return [tag for tag in TAGS if tag in found]


def foreigner_friendly(names: dict) -> int:
    """다국어 관광정보 제공 언어 수 기준(0~3): 영어, 일본어, 중국어(간체·번체 중 하나라도) 이름이 있는 언어의 수."""
    return ("en" in names) + ("ja" in names) + any(lang in names for lang in ZH)


def nearby(place_id: str, minutes: dict[frozenset, int], candidates: list[str]) -> list[str]:
    """candidates 중 place_id 에서 MAX_MINUTES 이내인 곳을 가까운 순으로 MAX_ALTERNATIVES 곳. 자기 자신은 뺀다."""
    timed = [(minutes[frozenset((place_id, other))], other) for other in candidates
             if other != place_id and frozenset((place_id, other)) in minutes]
    return [other for m, other in sorted(timed) if m <= MAX_MINUTES][:MAX_ALTERNATIVES]


def build_curation(places: list[dict], pairs: list[dict], lcls: dict[str, list[str]], overrides: dict) -> dict:
    """규칙으로 만든 {place_id: 큐레이션}. overrides 에 적힌 필드는 마지막에 덮어쓴다."""
    minutes = {frozenset((p["from_place_id"], p["to_place_id"])): p["minutes"] for p in pairs}
    tags = {p["place_id"]: place_tags(p, lcls.get(p["place_id"], [])) for p in places}
    indoor = [p["place_id"] for p in places if p["indoor"] and p["place_id"] not in RAIN_EXCLUDED]
    result = {}
    for place in places:
        pid = place["place_id"]
        # indoor 는 성격이 아니라 조건이라, indoor 만 겹치는 곳(시장 ↔ 전망대)은 비슷한 장소로 보지 않는다
        similar = [other for other in tags if (set(tags[pid]) & set(tags[other])) - {"indoor"}]
        result[pid] = {
            "tags": tags[pid],
            "foreigner_friendly": foreigner_friendly(place["names"]),
            "crowd_alternatives": nearby(pid, minutes, similar),
            "rain_alternatives": nearby(pid, minutes, indoor),
            "source": "rule",
        }
    # ponytail: 덮어쓰기는 그 장소의 필드만 바꾼다. tags 를 고쳐도 다른 장소의 crowd_alternatives 는 다시 계산하지 않는다.
    # 고친 태그가 대체 후보에도 반영돼야 하면 tags 덮어쓰기를 후보 계산 앞으로 옮긴다.
    for pid, fields in overrides.items():
        if pid in result:
            result[pid] = {**result[pid], **{k: v for k, v in fields.items() if k in FIELDS}, "source": "manual"}
    return result


def dump_curation(curation: dict) -> str:
    """curation.json 본문. 장소 하나를 한 줄로 쓴다."""
    rows = ",\n".join(f"  {json.dumps(pid)}: {json.dumps(entry, ensure_ascii=False)}" for pid, entry in curation.items())
    return "{\n" + rows + "\n}\n"


def load_inputs() -> tuple[list[dict], list[dict], dict[str, list[str]], dict]:
    """(places, 이동 시간 쌍, {place_id: [lclsSystm1, lclsSystm2]}, overrides)."""
    places = fp.load_json(fp.PLACES_PATH, [])
    sources = fp.load_json(fp.SOURCES_PATH, {})
    lcls = {}
    for place in places:
        kor_class = sources.get(place["place_id"], {}).get("kor_class", {})
        lcls[place["place_id"]] = [code for code in (kor_class.get("lclsSystm1"), kor_class.get("lclsSystm2")) if code]
    return places, fp.load_json(TRAVEL_PATH, {}).get("pairs", []), lcls, fp.load_json(OVERRIDES_PATH, {})


def main() -> int:
    places, pairs, lcls, overrides = load_inputs()
    known = {p["place_id"] for p in places}
    for pid in overrides:
        if pid not in known:
            print(f"[경고] curation_overrides.json 의 {pid} 는 places.json 에 없어 건너뜁니다")
    curation = build_curation(places, pairs, lcls, overrides)
    OUT_PATH.write_text(dump_curation(curation), encoding="utf-8", newline="\n")
    manual = sum(entry["source"] == "manual" for entry in curation.values())
    untagged = [pid for pid, entry in curation.items() if not entry["tags"]]
    print(f"curation {len(curation)}곳 저장 ({OUT_PATH.name}): 수동 {manual}곳, 태그 없음 {untagged}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
