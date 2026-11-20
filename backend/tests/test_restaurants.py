"""주변 음식점 도구(app/tools/restaurants.py)와 수집 스크립트(scripts/fetch_restaurants.py) 테스트. 네트워크를 쓰지 않는다.

속성 테스트(설계 Property 1~7)는 Hypothesis 없이 대표 값 여러 개로 확인한다.
"""

import csv
import json
import math
import shutil
import socket

import pytest
from pydantic import ValidationError

from app import config
from app.tools import lookup
from app.tools import restaurants as rs
from app.tools.restaurants import RestaurantTable, dump_restaurants, get_restaurants
from scripts import fetch_places as fp
from scripts import fetch_restaurants as fr

REAL_DATA = lookup.DATA_DIR
PLACES = {p["place_id"]: p for p in json.loads((REAL_DATA / "places.json").read_text(encoding="utf-8"))}
STATIONS = {s["station"]: s for s in json.loads((REAL_DATA / "stations.json").read_text(encoding="utf-8"))["stations"]}
BEACH, SEOMYEON = PLACES["haeundae-beach"], STATIONS["Seomyeon"]
DIET_WORDS = ("halal", "vegetarian", "vegan", "allerg", "gluten", "diet")


def error_code(result) -> str:
    assert set(result) == {"error"} and set(result["error"]) == {"code", "message"}
    return result["error"]["code"]


def north(origin: dict, meters: float) -> dict:
    """origin 에서 정북으로 meters 떨어진 좌표 (자오선을 따라가므로 직선거리가 정확히 meters 다)."""
    return {"lat": origin["lat"] + math.degrees(meters / 6371000), "lng": origin["lng"]}


def record(number: int, origin: dict, meters: float, **extra) -> dict:
    return {"restaurant_id": f"kto-{number}", "name_ko": f"식당{number}", "names": {}, **north(origin, meters),
            "address_ko": "부산광역시", "cuisine": "korean", "kor_class": {"lclsSystm3": "FD010100"}, "menu_raw": None, **extra}


def sample_table() -> dict:
    """해운대해수욕장 주변 6곳(100m 두 곳은 거리가 같다)과 서면역 주변 1곳."""
    return {
        "note": "테스트", "collected_at": "2026-11-20", "radius_m": 500,
        "anchors": {"haeundae-beach": ["kto-1", "kto-2", "kto-3", "kto-4", "kto-5"], "jagalchi-market": []},
        "station_anchors": {"Seomyeon": ["kto-7"]},
        "restaurants": [
            record(5, BEACH, 450), record(3, BEACH, 100), record(1, BEACH, -100, names={"en": "One", "ja": "ワン"}),
            record(2, BEACH, 299.6, cuisine=None, menu_raw="돼지국밥 / 수육"), record(4, BEACH, 300.4),
            record(6, BEACH, 900), record(7, SEOMYEON, 50, cuisine="cafe"),
        ],
    }


@pytest.fixture(autouse=True)
def fresh_table_cache():
    rs._table.cache_clear()
    yield
    rs._table.cache_clear()


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    """실제 places·stations·travel_times 와 테스트용 restaurants.json 이 있는 폴더를 도구가 읽게 한다."""
    for name in ("places.json", "stations.json", "travel_times.json"):
        shutil.copy(REAL_DATA / name, tmp_path / name)
    (tmp_path / "restaurants.json").write_text(dump_restaurants(RestaurantTable(**sample_table())), encoding="utf-8")
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    return tmp_path


def ids(result) -> list[str]:
    return [r["restaurant_id"] for r in result["restaurants"]]


def all_keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in all_keys(v)}
    return {k for v in node for k in all_keys(v)} if isinstance(node, list) else set()


# ---------- 도구 등록 ----------

def test_도구는_Strands_도구이고_설명은_영어로_한계를_밝힌다():
    spec = get_restaurants.tool_spec
    props = spec["inputSchema"]["json"]["properties"]
    assert set(props) == {"place_id", "station", "radius_m", "limit"} and all(p.get("description") for p in props.values())
    assert spec["inputSchema"]["json"].get("required", []) == []  # place_id 와 station 중 하나는 코드가 확인한다
    text = " ".join(get_restaurants.__doc__.split())
    assert not any("가" <= ch <= "힣" for ch in text)  # 모델이 읽는 문장은 영어
    for phrase in ("There is no dietary information", "halal", "ask the restaurant", "It is not a ranking", "no ratings",
                   "opening hours", '"about N minutes"', "not a place_id", "missing_argument", "invalid_argument",
                   "place_not_found", "station_not_found", "restaurants_not_collected", "data_unavailable"):
        assert phrase in text, phrase


# ---------- 조회 ----------

def test_가까운_순으로_돌려주고_거리가_같으면_ID_순이다(data_dir):
    result = get_restaurants(place_id="haeundae-beach")
    assert ids(result) == ["kto-1", "kto-3", "kto-2", "kto-4", "kto-5"]  # 900m 인 kto-6 은 반경 밖
    assert [r["distance_m"] for r in result["restaurants"]] == [100, 100, 300, 300, 450]
    assert [r["walk_min"] for r in result["restaurants"]] == [2, 2, 6, 6, 8]  # 거리 × 1.3 ÷ 4.5km/h, 올림
    assert {k: v for k, v in result.items() if k != "restaurants"} == {
        "place_id": "haeundae-beach", "station": None, "radius_m": 500, "total_in_radius": 5,
        "basis": {
            "kind": "collected_public_data", "source": "한국관광공사 TourAPI 음식점 정보 (공공데이터포털)",
            "collected_at": "2026-11-20", "distance": "straight_line_estimate", "diet_info": "not_available",
            "note": "Opening hours, closed days, prices, menus and dietary options (halal, vegetarian, allergens) are "
                    "not included. Ask the restaurant.",
        },
    }
    first = result["restaurants"][0]
    assert first == {"restaurant_id": "kto-1", "name_ko": "식당1", "names": {"en": "One", "ja": "ワン"},
                     "lat": first["lat"], "lng": first["lng"], "address_ko": "부산광역시", "cuisine": "korean",
                     "menu_raw": None, "distance_m": 100, "walk_min": 2}  # kor_class 는 돌려주지 않는다
    assert result["restaurants"][2]["menu_raw"] == "돼지국밥 / 수육" and result["restaurants"][2]["cuisine"] is None
    assert json.loads(json.dumps(result)) == result
    assert get_restaurants(place_id="haeundae-beach") == result  # 같은 입력에 같은 결과


def test_반경은_반올림_전_거리로_판단하고_limit은_개수만_줄인다(data_dir):
    # 299.6m 와 300.4m 는 둘 다 300m 로 보이지만 반경 300m 안은 앞의 것뿐이다
    assert ids(get_restaurants(place_id="haeundae-beach", radius_m=300)) == ["kto-1", "kto-3", "kto-2"]
    assert ids(get_restaurants(place_id="haeundae-beach", radius_m=301)) == ["kto-1", "kto-3", "kto-2", "kto-4"]
    limited = get_restaurants(place_id="haeundae-beach", limit=2)
    assert ids(limited) == ["kto-1", "kto-3"] and limited["total_in_radius"] == 5
    assert get_restaurants(place_id="haeundae-beach", radius_m=99)["restaurants"] == []
    empty = get_restaurants(place_id="jagalchi-market")  # 수집했지만 반경 안에 없다
    assert (empty["restaurants"], empty["total_in_radius"]) == ([], 0)


def test_역_이름으로_조회한다(data_dir):
    result = get_restaurants(station=" seomyeon ")
    assert (result["place_id"], result["station"], ids(result)) == (None, "Seomyeon", ["kto-7"])
    assert (result["restaurants"][0]["distance_m"], result["restaurants"][0]["walk_min"]) == (50, 1)
    both = get_restaurants(place_id="haeundae-beach", station="Seomyeon")  # 둘 다 주면 place_id 가 우선
    assert (both["place_id"], both["station"], len(both["restaurants"])) == ("haeundae-beach", None, 5)


def test_반경과_limit을_바꿔도_불변식이_지켜진다(data_dir):  # Property 1~3
    previous: set[str] = set()
    for radius in (1, 50, 100, 101, 299, 300, 301, 450, 451, 500):
        everything = get_restaurants(place_id="haeundae-beach", radius_m=radius, limit=20)
        found = ids(everything)
        assert previous <= set(found) and everything["total_in_radius"] == len(found)  # 반경이 커지면 줄지 않는다
        previous = set(found)
        keys = [(r["distance_m"], r["restaurant_id"]) for r in everything["restaurants"]]
        assert keys == sorted(keys) and all(d <= radius + 1 for d, _ in keys)
        for limit in (1, 2, 3, 20):
            cut = get_restaurants(place_id="haeundae-beach", radius_m=radius, limit=limit)
            assert ids(cut) == found[:limit] and len(cut["restaurants"]) == min(limit, cut["total_in_radius"])


def test_식단_평점_영업시간_필드가_없다(data_dir):  # Property 4
    for result in (get_restaurants(place_id="haeundae-beach"), get_restaurants(station="Seomyeon"),
                   get_restaurants(place_id="jagalchi-market")):
        keys = all_keys(result) - {"diet_info"}
        assert not any(word in key for key in keys for word in DIET_WORDS)
        assert not keys & {"rating", "rank", "score", "price", "popularity", "opens", "closes", "hours", "closed_weekdays"}
        assert result["basis"]["diet_info"] == "not_available"
        assert all(r["restaurant_id"].startswith("kto-") for r in result["restaurants"])
        assert result["place_id"] in {None, *PLACES}  # 장소 ID 는 places.json 값만


# ---------- 오류 ----------

def test_입력_오류(data_dir):
    assert error_code(get_restaurants()) == "missing_argument"
    assert error_code(get_restaurants(place_id="", station="")) == "missing_argument"
    assert error_code(get_restaurants(place_id="no-such-place")) == "place_not_found"
    assert error_code(get_restaurants(station="Osiria")) == "station_not_found"
    not_collected = get_restaurants(place_id="busan-tower")
    assert error_code(not_collected) == "restaurants_not_collected"
    assert "haeundae-beach, jagalchi-market, station Seomyeon" in not_collected["error"]["message"]
    assert error_code(get_restaurants(station="Haeundae")) == "restaurants_not_collected"
    for bad in ({"radius_m": 0}, {"radius_m": 1001}, {"radius_m": -5}, {"radius_m": "500"}, {"radius_m": 300.5},
                {"radius_m": True}, {"limit": 0}, {"limit": 21}, {"limit": None}):
        assert error_code(get_restaurants(place_id="haeundae-beach", **bad)) == "invalid_argument", bad
    too_wide = get_restaurants(place_id="haeundae-beach", radius_m=501)  # 수집 반경(500m)보다 넓으면 답할 수 없다
    assert error_code(too_wide) == "invalid_argument" and "collected within 500 m" in too_wide["error"]["message"]
    assert ids(get_restaurants(place_id="haeundae-beach", radius_m=500, limit=20)) == ["kto-1", "kto-3", "kto-2", "kto-4", "kto-5"]


def test_파일이_없거나_형식이_틀리면_data_unavailable(data_dir):
    path = data_dir / "restaurants.json"
    table = sample_table()
    table["restaurants"][0]["halal"] = True  # 모델이 모르는 필드(식단)를 막는다
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    assert error_code(get_restaurants(place_id="haeundae-beach")) == "data_unavailable"
    path.unlink()
    rs._table.cache_clear()
    assert error_code(get_restaurants(place_id="haeundae-beach")) == "data_unavailable"
    assert error_code(get_restaurants(place_id="no-such-place")) == "place_not_found"  # 입력 오류가 먼저다


def test_네트워크와_개발_모드에_상관없이_파일만_읽는다(data_dir, monkeypatch):
    expected = get_restaurants(place_id="haeundae-beach")

    def blocked(*args, **kwargs):
        pytest.fail("네트워크나 현재 시각을 쓰면 안 된다")

    monkeypatch.setattr(lookup.urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(lookup, "_now", blocked)
    for use_mock, fake_llm in ((True, True), (False, False)):
        monkeypatch.setattr(config, "USE_MOCK", use_mock)
        monkeypatch.setattr(config, "FAKE_LLM", fake_llm)
        assert get_restaurants(place_id="haeundae-beach") == expected
    text = (REAL_DATA.parent / "tools" / "restaurants.py").read_text(encoding="utf-8").casefold()
    assert not any(word in text for word in ("kakao", "카카오", "http://", "https://", "urllib"))


# ---------- 파일 형식 ----------

def test_파일_왕복과_정렬(tmp_path):  # Property 5
    table = RestaurantTable(**sample_table())
    text = dump_restaurants(table)
    assert RestaurantTable.model_validate_json(text).model_dump() == {
        **table.model_dump(), "restaurants": sorted(table.model_dump()["restaurants"], key=lambda r: r["restaurant_id"])}
    assert dump_restaurants(RestaurantTable.model_validate_json(text)) == text  # 다시 써도 바이트까지 같다
    shuffled = sample_table()
    shuffled["restaurants"].reverse()
    shuffled["anchors"] = dict(reversed(shuffled["anchors"].items()))
    shuffled["anchors"]["haeundae-beach"].reverse()
    assert dump_restaurants(RestaurantTable(**shuffled)) == text  # 입력 순서와 상관없이 같은 파일
    rows = [line for line in text.splitlines() if line.startswith('    {"restaurant_id"')]
    assert [json.loads(row.rstrip(","))["restaurant_id"] for row in rows] == [f"kto-{n}" for n in range(1, 8)]
    assert "식당1" in text and "ワン" in text and text.endswith("}\n")  # 한국어·일본어 그대로, 음식점 하나가 한 줄
    empty = RestaurantTable(note="n", collected_at="2026-11-20", radius_m=500, anchors={}, restaurants=[])
    assert RestaurantTable.model_validate_json(dump_restaurants(empty)) == empty
    path = tmp_path / "restaurants.json"
    path.write_text(text, encoding="utf-8", newline="\n")
    assert rs._table(path) == RestaurantTable.model_validate_json(text)


def test_모델은_중복_ID와_모르는_필드와_없는_ID를_막는다():  # Property 6
    def broken(change) -> dict:
        table = sample_table()
        change(table)
        return table

    for change in (
        lambda t: t["restaurants"].append(record(1, BEACH, 10)),  # 같은 restaurant_id 두 번
        lambda t: t["anchors"]["haeundae-beach"].append("kto-999"),  # restaurants 에 없는 ID
        lambda t: t["station_anchors"]["Seomyeon"].append("kto-999"),
        lambda t: t["restaurants"][0].update(vegetarian=True),  # 식단 필드
        lambda t: t["restaurants"][0].update(cuisine="halal"),  # 정해진 분류가 아닌 값
        lambda t: t["restaurants"][0]["names"].update(ko="식당"),  # names 는 외국어 4개만
        lambda t: t.update(diet="none"),
        lambda t: t.pop("collected_at"),
    ):
        with pytest.raises(ValidationError):
            RestaurantTable(**broken(change))
    RestaurantTable(**sample_table())


# ---------- 수집 스크립트 ----------

def api_item(contentid, title, coord, **extra) -> dict:
    return {"contentid": str(contentid), "title": title, "addr1": "부산광역시 테스트구", "mapx": str(coord["lng"]),
            "mapy": str(coord["lat"]), "contenttypeid": "39", **extra}


def api_response(items: list[dict], total: int | None = None) -> dict:
    body = {"items": {"item": items} if items else "", "totalCount": len(items) if total is None else total}
    return {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"}, "body": body}}


KOR_A = api_item(101, "해운대국밥", north(BEACH, 100), lclsSystm1="FD", lclsSystm2="FD01", lclsSystm3="FD010100")
KOR_B = api_item(102, "서면초밥", north(SEOMYEON, 50), lclsSystm1="FD", lclsSystm2="FD02", lclsSystm3="FD020200")
KOR_FAR = api_item(103, "먼집", north(BEACH, 5000), lclsSystm1="FD", lclsSystm2="FD09", lclsSystm3="FD999999")
KOR_NEW = api_item(104, "새분류집", north(BEACH, 200), lclsSystm1="FD", lclsSystm2="FD09", lclsSystm3="FD999999")


@pytest.fixture
def collector(monkeypatch, tmp_path):
    """수집 스크립트를 임시 폴더와 고정 응답으로 돌린다. 반환한 dict 의 calls 에 실제로 보낸 요청이 쌓인다."""
    state = {"calls": [], "fail": {"ChsService2"}, "tmp": tmp_path}

    def request_json(service, operation, extra):
        state["calls"].append((service, operation, extra.get("pageNo") or extra.get("contentId")))
        if service in state["fail"]:
            raise fp.FetchError(f"{service}/{operation} 호출 실패 (HTTP 500)")
        if operation == "detailIntro2":
            menus = {"101": {"firstmenu": "돼지국밥", "treatmenu": "돼지국밥<br>수육"}, "104": {"firstmenu": "", "treatmenu": ""},
                     "102": {"firstmenu": "초밥", "treatmenu": "모둠초밥 / 우동"}}  # "초밥" 은 "모둠초밥" 과 다른 메뉴다
            return api_response([{"contentid": extra["contentId"], **menus.get(extra["contentId"], {})}])
        if service == "KorService2":  # 2건씩 2쪽 (totalCount 4)
            return api_response({1: [KOR_A, KOR_B], 2: [KOR_FAR, KOR_NEW]}[extra["pageNo"]], total=4)
        if service == "EngService2":  # 한국어가 같다 → exact
            return api_response([api_item(901, "Haeundae Gukbap (해운대국밥)", north(BEACH, 100), contenttypeid="82")])
        if service == "JpnService2":  # 한국어가 포함된다 → contains
            return api_response([api_item(902, "ソミョン寿司本店（서면초밥 본점）", north(SEOMYEON, 60), contenttypeid="82")])
        return api_response([])  # ChtService2: 0건

    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps({"radius_m": 500, "place_ids": ["haeundae-beach", "jagalchi-market"],
                                 "stations": ["Seomyeon"]}), encoding="utf-8")
    monkeypatch.setattr(fp, "request_json", request_json)
    monkeypatch.setattr(fp, "_today", lambda: "2026-11-20")
    monkeypatch.setattr(fp, "OFFLINE", False)  # main 이 바꾼 값이 다른 테스트에 남지 않게 한다
    monkeypatch.setattr(fp, "REUSE_RAW", False)
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "SECRET")
    monkeypatch.setattr(fr, "ROWS", 2)
    monkeypatch.setattr(fr, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(fr, "OUT_PATH", tmp_path / "restaurants.json")
    monkeypatch.setattr(fr, "REVIEW_PATH", tmp_path / "review.csv")
    monkeypatch.setattr(fr, "SEEDS_PATH", seeds)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("네트워크를 쓰면 안 된다"))
    return state


def test_수집_스크립트는_반경_안의_음식점을_합치고_이름을_맞춘다(collector, capsys):
    assert fr.main([]) == 0
    tmp = collector["tmp"]
    table = RestaurantTable.model_validate_json((tmp / "restaurants.json").read_text(encoding="utf-8"))
    assert (table.collected_at, table.radius_m) == ("2026-11-20", 500)
    assert table.anchors == {"haeundae-beach": ["kto-101", "kto-104"], "jagalchi-market": []}
    assert table.station_anchors == {"Seomyeon": ["kto-102"]}
    by_id = {r.restaurant_id: r for r in table.restaurants}
    assert list(by_id) == ["kto-101", "kto-102", "kto-104"]  # 5km 떨어진 곳은 어느 기준에도 들지 않는다
    assert by_id["kto-101"].model_dump() == {
        "restaurant_id": "kto-101", "name_ko": "해운대국밥", "names": {"en": "Haeundae Gukbap"},
        "lat": float(KOR_A["mapy"]), "lng": float(KOR_A["mapx"]), "address_ko": "부산광역시 테스트구", "cuisine": "korean",
        "kor_class": {"lclsSystm1": "FD", "lclsSystm2": "FD01", "lclsSystm3": "FD010100"},
        "menu_raw": "돼지국밥 / 수육",  # treatmenu 원문(태그만 정리). firstmenu 가 그 안에 있으면 한 번만 적는다
    }
    assert (by_id["kto-102"].names, by_id["kto-102"].cuisine) == ({"ja": "ソミョン寿司本店"}, "japanese")
    assert by_id["kto-102"].menu_raw == "초밥 / 모둠초밥 / 우동"  # 대표 메뉴가 취급 메뉴의 한 항목과 같을 때만 줄인다
    assert (by_id["kto-104"].cuisine, by_id["kto-104"].menu_raw) == (None, None)  # 표에 없는 분류 코드, 빈 메뉴
    # 실제로 보낸 요청: 국문 2쪽 + 외국어 4개 서비스 1쪽씩 + 메뉴 3곳
    assert collector["calls"] == [
        ("KorService2", "areaBasedList2", 1), ("KorService2", "areaBasedList2", 2), ("EngService2", "areaBasedList2", 1),
        ("JpnService2", "areaBasedList2", 1), ("ChsService2", "areaBasedList2", 1), ("ChtService2", "areaBasedList2", 1),
        ("KorService2", "detailIntro2", "101"), ("KorService2", "detailIntro2", "104"), ("KorService2", "detailIntro2", "102"),
    ]
    with (tmp / "review.csv").open(encoding="utf-8", newline="") as f:
        review = list(csv.DictReader(f))
    assert {"anchor": "*", "restaurant_id": "", "name_ko": "", "lang": "zh-Hans",
            "reason": "api_error: ChsService2/areaBasedList2 호출 실패 (HTTP 500)", "candidates": ""} in review
    missing = {(r["restaurant_id"], r["lang"], r["reason"]) for r in review if r["restaurant_id"]}
    assert missing == {("kto-101", "ja", "no_korean_match"), ("kto-101", "zh-Hant", "no_korean_match"),
                       ("kto-102", "en", "no_korean_match"), ("kto-102", "zh-Hant", "no_korean_match"),
                       ("kto-104", "en", "no_korean_match"), ("kto-104", "ja", "no_korean_match"),
                       ("kto-104", "zh-Hant", "no_korean_match")}  # 호출이 실패한 zh-Hans 는 음식점마다 남기지 않는다
    raw_files = sorted(p.relative_to(tmp / "raw").as_posix() for p in (tmp / "raw").rglob("*.json"))
    assert raw_files == ["_intro/101.json", "_intro/102.json", "_intro/104.json", "en_p1.json", "ja_p1.json",
                         "ko_p1.json", "ko_p2.json", "zh-Hant_p1.json"]
    assert not any(word in p.read_text(encoding="utf-8") for p in tmp.rglob("*.*") for word in ("SECRET", "serviceKey"))
    out = capsys.readouterr().out
    for part in ("음식점 3곳 저장", "haeundae-beach: 2곳", "jagalchi-market: 0곳", "station Seomyeon: 1곳",
                 "검토 필요 8건", "API 호출 0회"):  # 호출 수는 fp.API_CALLS 기준 (가짜 request_json 은 세지 않는다)
        assert part in out, part


def test_수집_스크립트_offline은_호출_없이_같은_파일을_만든다(collector, monkeypatch):  # Property 7
    assert fr.main([]) == 0
    out = collector["tmp"] / "restaurants.json"
    online = out.read_bytes()
    collector["calls"].clear()
    monkeypatch.setattr(fp, "_today", lambda: "2026-12-31")  # offline 은 수집일을 바꾸지 않는다
    for _ in range(2):
        assert fr.main(["--offline"]) == 0
        assert out.read_bytes() == online
    assert collector["calls"] == []
    # --reuse-raw 는 저장된 응답이 없는 요청(실패했던 간체)만 다시 보낸다
    collector["fail"].clear()
    assert fr.main(["--reuse-raw"]) == 0
    assert collector["calls"] == [("ChsService2", "areaBasedList2", 1)]
    assert json.loads(out.read_text(encoding="utf-8"))["collected_at"] == "2026-12-31"


def test_수집_스크립트는_키가_없거나_시드가_틀리면_1로_끝난다(collector, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "")
    assert fr.main([]) == 1 and "DATA_GO_KR_KEY_DECODING" in capsys.readouterr().err
    assert fr.main(["--offline"]) == 1  # 저장된 국문 응답이 없다
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "SECRET")
    fr.SEEDS_PATH.write_text(json.dumps({"radius_m": 500, "place_ids": ["seomyeon-street"], "stations": ["Nowhere"]}),
                             encoding="utf-8")
    assert fr.main([]) == 1 and "seomyeon-street, Nowhere" in capsys.readouterr().err  # 새 장소 ID 를 만들지 않는다
    assert collector["calls"] == [] and not (collector["tmp"] / "restaurants.json").exists()
    collector["fail"].add("KorService2")
    fr.SEEDS_PATH.write_text(json.dumps({"radius_m": 500, "place_ids": ["haeundae-beach"]}), encoding="utf-8")
    assert fr.main([]) == 1 and "국문 음식점 조회 실패" in capsys.readouterr().err


def test_외국어_이름_일치_규칙과_cuisine_표():
    kor = fp.parse_items(api_response([KOR_A]))[0]
    exact = fp.parse_items(api_response([api_item(1, "Haeundae Gukbap (해운대국밥)", north(BEACH, 2000))]))
    contains = fp.parse_items(api_response([api_item(2, "海雲台クッパ本店（해운대국밥 본점）", north(BEACH, 150))]))
    far_contains = fp.parse_items(api_response([api_item(3, "海雲台クッパ本店（해운대국밥 본점）", north(BEACH, 450))]))
    other = fp.parse_items(api_response([api_item(4, "Other Place (다른집)", north(BEACH, 100))]))
    made, review = fr.build_record(kor, KOR_A, {"en": exact, "ja": contains, "zh-Hans": far_contains, "zh-Hant": other}, None)
    # exact 는 300m 안에서만 찾는다(pick_foreign 기본 반경). 2km 떨어진 exact 는 쓰지 않는다
    assert made["names"] == {"ja": "海雲台クッパ本店"}
    assert [(r["lang"], r["reason"]) for r in review] == [("en", "no_korean_match"), ("zh-Hans", "no_korean_match"),
                                                          ("zh-Hant", "no_korean_match")]
    assert "4|Other Place (다른집)|0m" in review[2]["candidates"]
    near_exact = fp.parse_items(api_response([api_item(1, "Haeundae Gukbap (해운대국밥)", north(BEACH, 110))]))
    assert fr.build_record(kor, KOR_A, {"en": near_exact}, "메뉴")[0]["names"] == {"en": "Haeundae Gukbap"}
    assert set(fr.CUISINE_BY_CLASS.values()) <= {"korean", "western", "japanese", "chinese", "cafe", "other"}
    assert (fr.CUISINE_BY_CLASS["FD010100"], fr.CUISINE_BY_CLASS["FD020100"], fr.CUISINE_BY_CLASS["FD020200"],
            fr.CUISINE_BY_CLASS["FD020300"], fr.CUISINE_BY_CLASS["FD050100"]) == ("korean", "chinese", "japanese", "western", "cafe")
    with pytest.raises(ValueError):
        fr.load_anchors({"place_ids": ["no-such-place"]}, list(PLACES.values()), list(STATIONS.values()))


# ---------- 실제 데이터 (app/data/restaurants.json) ----------

def test_실제_파일은_시드의_기준을_모두_담고_형식이_맞다():
    path = REAL_DATA / "restaurants.json"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw  # UTF-8, BOM 없음, LF
    table = RestaurantTable.model_validate_json(raw)
    assert dump_restaurants(table) == raw.decode("utf-8")  # 스크립트가 쓴 형식 그대로 (ID 오름차순)
    seeds = json.loads(fr.SEEDS_PATH.read_text(encoding="utf-8"))
    assert seeds == {"radius_m": 500, "place_ids": ["haeundae-beach", "jagalchi-market", "gamcheon-village"],
                     "stations": ["Seomyeon"]}
    assert (table.radius_m, set(table.anchors), set(table.station_anchors)) == (500, set(seeds["place_ids"]), {"Seomyeon"})
    assert set(table.anchors) <= set(PLACES) and set(table.station_anchors) <= set(STATIONS)  # 새 ID 를 만들지 않는다
    by_id = {r.restaurant_id: r for r in table.restaurants}
    listed: set[str] = set()
    for origin, found in [*((PLACES[name], found) for name, found in table.anchors.items()),
                          *((STATIONS[name], found) for name, found in table.station_anchors.items())]:
        assert found, "기준마다 음식점이 한 곳 이상 있어야 한다"
        assert all(fp.haversine_m(origin["lat"], origin["lng"], by_id[rid].lat, by_id[rid].lng) <= 500 for rid in found)
        listed |= set(found)
    assert listed == set(by_id)  # 어느 기준에도 들지 않는 음식점은 없다
    for r in table.restaurants:
        assert r.restaurant_id.startswith("kto-") and r.restaurant_id not in PLACES and r.name_ko and r.address_ko.startswith("부산")
        assert r.cuisine == fr.CUISINE_BY_CLASS.get(r.kor_class["lclsSystm3"] or "")
    assert sum(r.menu_raw is not None for r in table.restaurants) <= fr.MENU_TOP_N * 4  # 기준마다 가까운 5곳만 메뉴를 받는다


def test_실제_데이터로_데모_기준_네_곳을_조회한다():
    seomyeon = get_restaurants(station="Seomyeon", limit=3)
    assert [(r["name_ko"], r["distance_m"], r["walk_min"]) for r in seomyeon["restaurants"]] == [
        ("급행장", 120, 3), ("회국수할매집", 161, 3), ("고향맛", 192, 4)]
    assert (seomyeon["total_in_radius"], seomyeon["basis"]["collected_at"]) == (14, "2026-11-20")
    assert seomyeon["restaurants"][1]["names"] == {"en": "Hoeguksu Halmaejip"}  # 외국어 이름은 있는 언어만
    totals = {pid: get_restaurants(place_id=pid, limit=20)["total_in_radius"]
              for pid in ("haeundae-beach", "jagalchi-market", "gamcheon-village")}
    assert totals == {"haeundae-beach": 11, "jagalchi-market": 17, "gamcheon-village": 1}
    assert error_code(get_restaurants(place_id="busan-tower")) == "restaurants_not_collected"
    assert error_code(get_restaurants(place_id="haeundae-beach", radius_m=501)) == "invalid_argument"
