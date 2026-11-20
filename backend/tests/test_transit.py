"""대중교통 정보 도구(app/tools/transit.py) 테스트. 네트워크를 쓰지 않는다.

속성 테스트(설계 Property 8~13)는 Hypothesis 없이 실제 데이터의 모든 장소·역 조합으로 확인한다.
"""

import itertools
import json
import socket

import pytest

from app import config
from app.tools import lookup
from app.tools import return_options as ro
from app.tools import transit
from app.tools.transit import get_transit_info

PLACES = {p["place_id"]: p for p in json.loads((lookup.DATA_DIR / "places.json").read_text(encoding="utf-8"))}
STATIONS = {s["station"]: s for s in json.loads((lookup.DATA_DIR / "stations.json").read_text(encoding="utf-8"))["stations"]}
RULE = {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 10, "walk_kmh": 4.5}
WITH_STATION = sorted(pid for pid, p in PLACES.items() if p["nearest_station"] in STATIONS)
WITHOUT_STATION = sorted(set(PLACES) - set(WITH_STATION))


def error_code(result) -> str:
    assert set(result) == {"error"} and set(result["error"]) == {"code", "message"}
    return result["error"]["code"]


# ---------- 도구 등록 ----------

def test_도구는_Strands_도구이고_설명은_영어로_한계를_밝힌다():
    spec = get_transit_info.tool_spec
    props = spec["inputSchema"]["json"]["properties"]
    assert set(props) == {"from_place_id", "to_place_id", "to_station"} and all(p.get("description") for p in props.values())
    assert spec["inputSchema"]["json"]["required"] == ["from_place_id"]
    text = " ".join(get_transit_info.__doc__.split())
    assert not any("가" <= ch <= "힣" for ch in text)  # 모델이 읽는 문장은 영어
    for phrase in ('"about N minutes"', "do not state which line to take", "transfer", "first and last train",
                   "train intervals", "not real routes or timetables", "Donghae Line", "far_from_station",
                   "missing_argument", "place_not_found", "same_place", "station_not_found", "no_station"):
        assert phrase in text, phrase


# ---------- 해운대 → 서면 ----------

def test_장소에서_역으로_해운대에서_서면():
    result = get_transit_info(from_place_id="haeundae-beach", to_station="Seomyeon")
    assert result == {
        "from": {"place_id": "haeundae-beach", "station": "Haeundae", "station_ko": "해운대역", "lines": ["2"],
                 "is_transfer_station": False, "walk_to_station_min": 10, "warnings": []},
        "to": {"place_id": None, "station": "Seomyeon", "station_ko": "서면역", "lines": ["1", "2"],
               "is_transfer_station": True, "walk_from_station_min": 0, "warnings": []},
        "subway": {"minutes": 39, "same_station": False},
        "total_min": 49,
        "basis": {
            "kind": "rule", "measured": False, "travel_time_rule": RULE,
            "note": "Estimated from coordinates, not routes or timetables. 'lines' are the lines that serve each "
                    "station (reference only). Transfers between the two stations are not computed.",
            "not_included": ["timetable", "real_time", "first_last_train", "fare", "transfer_walk"],
            "coverage": "Busan Metro lines 1-4 only. Donghae Line and light rail stations are not in the station table.",
        },
    }
    assert json.loads(json.dumps(result)) == result
    # 귀가 분산 도구와 같은 계산이다
    assert result["subway"]["minutes"] == ro.subway_minutes(STATIONS["Haeundae"], STATIONS["Seomyeon"], RULE)
    assert get_transit_info("haeundae-beach", to_station="Seomyeon") == result  # 위치 인자로도 같다


def test_to_station은_대소문자와_공백을_무시하고_to_place_id보다_우선한다():
    expected = get_transit_info(from_place_id="haeundae-beach", to_station="Seomyeon")
    assert get_transit_info(from_place_id="haeundae-beach", to_station="  seoMYEON ") == expected
    # 둘 다 주면 to_station 이 우선이고 to_place_id 는 검증도 하지 않는다 (없는 장소, 같은 장소여도)
    assert get_transit_info(from_place_id="haeundae-beach", to_place_id="no-such-place", to_station="Seomyeon") == expected
    assert get_transit_info(from_place_id="haeundae-beach", to_place_id="haeundae-beach", to_station="Seomyeon") == expected
    assert get_transit_info(from_place_id="busan-tower", to_station="pusan nat'l univ.")["to"]["station"] == "Pusan Nat'l Univ."


def test_장소에서_장소로_도착_쪽도_걷는_시간이_있다():
    result = get_transit_info(from_place_id="haeundae-beach", to_place_id="jagalchi-market")
    assert result["to"] == {"place_id": "jagalchi-market", "station": "Jagalchi", "station_ko": "자갈치역", "lines": ["1"],
                            "is_transfer_station": False, "walk_from_station_min": 7, "warnings": []}
    subway = ro.subway_minutes(STATIONS["Haeundae"], STATIONS["Jagalchi"], RULE)
    assert result["subway"] == {"minutes": subway, "same_station": False}
    assert result["total_min"] == 10 + subway + 7


def test_같은_역이면_지하철은_0분이고_같은_장소는_오류():
    result = get_transit_info(from_place_id="haeundae-beach", to_place_id="haeundae-market")  # 둘 다 해운대역
    assert result["subway"] == {"minutes": 0, "same_station": True}
    assert result["total_min"] == result["from"]["walk_to_station_min"] + result["to"]["walk_from_station_min"]
    to_own_station = get_transit_info(from_place_id="haeundae-beach", to_station="Haeundae")
    assert to_own_station["subway"] == {"minutes": 0, "same_station": True} and to_own_station["total_min"] == 10
    assert error_code(get_transit_info(from_place_id="haeundae-beach", to_place_id="haeundae-beach")) == "same_place"


def test_역이_먼_장소는_far_from_station_경고():
    result = get_transit_info(from_place_id="beomeosa-temple", to_place_id="songjeong-beach")
    assert (result["from"]["walk_to_station_min"], result["from"]["warnings"]) == (41, ["far_from_station"])
    assert (result["to"]["walk_from_station_min"], result["to"]["warnings"]) == (40, ["far_from_station"])
    assert transit.FAR_FROM_STATION_MIN == ro.WALK_ALT_MAX_MIN == 20
    for pid in WITH_STATION:  # 20분은 경고가 아니고 21분부터다
        side = get_transit_info(from_place_id=pid, to_station="Seomyeon")["from"]
        assert side["warnings"] == (["far_from_station"] if side["walk_to_station_min"] > 20 else [])


# ---------- 오류 ----------

def test_입력_오류와_검증_순서():
    assert error_code(get_transit_info(from_place_id="haeundae-beach")) == "missing_argument"
    assert error_code(get_transit_info(from_place_id="no-such-place")) == "missing_argument"  # 인자 확인이 먼저
    assert error_code(get_transit_info(from_place_id="no-such-place", to_station="Seomyeon")) == "place_not_found"
    assert error_code(get_transit_info(from_place_id="no-such-place", to_place_id="no-such-place")) == "place_not_found"
    assert error_code(get_transit_info(from_place_id="haeundae-beach", to_place_id="no-such-place")) == "place_not_found"
    assert error_code(get_transit_info(from_place_id="haeundae-beach", to_station="Osiria")) == "station_not_found"
    # 출발 장소에 역이 없어도 도착 인자의 오류가 먼저 나온다
    assert error_code(get_transit_info(from_place_id="taejongdae", to_station="Nowhere")) == "station_not_found"


def test_역_표에_없는_역이_가까운_장소는_no_station():
    assert WITHOUT_STATION == ["haedong-yonggungsa", "lotte-outlet-dongbusan", "lotte-world-busan",
                               "national-maritime-museum", "taejongdae"]
    assert PLACES["haedong-yonggungsa"]["nearest_station"] == "OSIRIA" and PLACES["taejongdae"]["nearest_station"] is None
    for pid in WITHOUT_STATION:
        for result in (get_transit_info(from_place_id=pid, to_station="Seomyeon"),
                       get_transit_info(from_place_id="haeundae-beach", to_place_id=pid)):
            assert error_code(result) == "no_station"
            assert "Donghae Line and light rail stations are not in the data" in result["error"]["message"]


def test_파일을_못_읽으면_오류_dict(monkeypatch, tmp_path):
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert error_code(get_transit_info(from_place_id="haeundae-beach", to_station="Seomyeon")) == "data_unavailable"


@pytest.mark.parametrize("kwargs", [
    {"from_place_id": ""}, {"from_place_id": "x", "to_place_id": "y"}, {"from_place_id": "haeundae-beach", "to_station": ""},
    {"from_place_id": "haeundae-beach", "to_station": "서면"}, {"from_place_id": "haeundae-beach", "to_place_id": "OSIRIA"},
])
def test_잘못된_입력은_항상_오류_dict_하나다(kwargs):  # Property 13
    error_code(get_transit_info(**kwargs))


# ---------- 속성 (실제 데이터의 모든 조합) ----------

def test_모든_장소_쌍에서_합계_대칭_환승역_ID가_맞다():  # Property 8~12
    for a, b in itertools.combinations(WITH_STATION, 2):
        there, back = get_transit_info(from_place_id=a, to_place_id=b), get_transit_info(from_place_id=b, to_place_id=a)
        start, end = STATIONS[there["from"]["station"]], STATIONS[there["to"]["station"]]
        # Property 8: 귀가 분산 도구와 같은 지하철 분, 합계는 세 값의 합
        assert there["subway"]["minutes"] == ro.subway_minutes(start, end, RULE)
        assert there["total_min"] == (there["from"]["walk_to_station_min"] + there["subway"]["minutes"]
                                      + there["to"]["walk_from_station_min"])
        # Property 9: 방향을 바꾸면 지하철 분은 같고 걷는 시간은 서로 바뀐다
        assert back["subway"] == there["subway"] and back["total_min"] == there["total_min"]
        assert back["from"]["walk_to_station_min"] == there["to"]["walk_from_station_min"]
        assert back["to"]["walk_from_station_min"] == there["from"]["walk_to_station_min"]
        # Property 10: 같은 역이면 0분
        same = PLACES[a]["nearest_station"] == PLACES[b]["nearest_station"]
        assert there["subway"]["same_station"] is same and (there["subway"]["minutes"] == 0) is same
        for side in (there["from"], there["to"]):
            # Property 11: lines 는 역 표 값 그대로, 환승역은 호선이 2개 이상
            assert side["lines"] == STATIONS[side["station"]]["lines"] and side["station_ko"] == STATIONS[side["station"]]["name_ko"]
            assert side["is_transfer_station"] is (len(side["lines"]) >= 2)
            assert side["place_id"] in PLACES  # Property 12
            assert isinstance(side["walk_to_station_min" if side is there["from"] else "walk_from_station_min"], int)


def test_모든_역으로_가는_결과가_역_표와_맞다():
    transfer = {"Seomyeon", "Yeonsan", "Dongnae", "Suyeong", "Deokcheon", "Minam"}
    for name, station in STATIONS.items():
        result = get_transit_info(from_place_id="haeundae-beach", to_station=name.upper())
        assert result["to"] == {"place_id": None, "station": name, "station_ko": station["name_ko"], "lines": station["lines"],
                                "is_transfer_station": name in transfer, "walk_from_station_min": 0, "warnings": []}
        assert result["subway"]["minutes"] == ro.subway_minutes(STATIONS["Haeundae"], station, RULE)


# ---------- 금지 사항 ----------

def test_경로_API_네트워크_현재_시각을_쓰지_않는다(monkeypatch):
    text = (lookup.DATA_DIR.parent / "tools" / "transit.py").read_text(encoding="utf-8").casefold()
    assert not any(word in text for word in ("kakao", "카카오", "http://", "https://", "urllib", "datetime"))
    expected = get_transit_info(from_place_id="haeundae-beach", to_place_id="busan-tower")

    def blocked(*args, **kwargs):
        pytest.fail("네트워크나 현재 시각을 쓰면 안 된다")

    monkeypatch.setattr(lookup.urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(lookup, "_now", blocked)
    for use_mock, fake_llm in ((True, True), (False, False)):
        monkeypatch.setattr(config, "USE_MOCK", use_mock)
        monkeypatch.setattr(config, "FAKE_LLM", fake_llm)
        assert get_transit_info(from_place_id="haeundae-beach", to_place_id="busan-tower") == expected
    forbidden = ("transfers", "transfer_count", "line", "fare", "timetable", "first_train", "last_train", "arrival")
    assert not set(expected["subway"]) & set(forbidden) and not set(expected) & set(forbidden)  # 환승·호선 선택을 만들지 않는다
