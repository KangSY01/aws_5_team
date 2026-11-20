"""귀가 분산 도구(app/tools/return_options.py)와 역 표(scripts/build_stations.py) 테스트. 네트워크를 쓰지 않는다."""

import csv
import datetime as dt
import json
import re
import shutil
import socket
import time
from pathlib import Path

import pytest

from app import config
from app.ranking import rank_routes
from app.tools import kakao_route, lookup
from app.tools import return_options as ro
from app.tools.return_options import get_return_options
from scripts import build_stations

REAL_DATA = lookup.DATA_DIR
FESTIVAL = "해운대 빛축제"
DAY = "2026-11-28"


def load(name: str):
    return json.loads((REAL_DATA / name).read_text(encoding="utf-8"))


def error_code(result) -> str:
    assert set(result) == {"error"} and set(result["error"]) == {"code", "message"}
    return result["error"]["code"]


def event(name, end="23:00:00", place_ids=("haeundae-beach",), main="haeundae-beach", start="18:00:00", end_day=DAY):
    return {"name": name, "start": f"{DAY}T{start}+09:00", "end": f"{end_day}T{end}+09:00",
            "place_ids": list(place_ids), "main_place_id": main}


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    """실제 데이터를 복사한 폴더를 도구가 읽게 한다. 반환한 함수로 파일을 바꿔 쓴다."""
    for name in ("places.json", "stations.json", "travel_times.json", "events.json"):
        shutil.copy(REAL_DATA / name, tmp_path / name)
    if (REAL_DATA / "last_trains.json").exists():
        shutil.copy(REAL_DATA / "last_trains.json", tmp_path / "last_trains.json")
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)

    def write(name: str, data) -> None:
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    return write


def walks(result) -> dict[str, dict]:
    return {o["station"]: o for o in result["options"] if o["type"] == "walk_to_station"}


# ---------- 도구 등록 ----------

def test_도구는_Strands_도구이고_설명은_영어로_가정을_밝힌다():
    spec = get_return_options.tool_spec
    props = spec["inputSchema"]["json"]["properties"]
    assert set(props) == {"date", "place_id", "event_name", "destination_station", "destination_place_id",
                          "planned_departure"}
    assert all(p.get("description") for p in props.values())
    assert spec["inputSchema"]["json"]["required"] == ["date"]  # destination_station 의 인자 기본값은 None 이다
    text = " ".join(get_return_options.__doc__.split())  # 줄바꿈을 무시하고 문구를 찾는다
    assert not re.search("[가-힣]", text)  # 모델이 읽는 문장은 영어 (tech.md)
    for phrase in ("after a festival or event ends", "rule-based estimate", "not measured or real-time",
                   "assumption made without supporting data", "station coordinates", "stored standard timetable",
                   "last_train_missed", "last_train_unknown", "defaults to Seomyeon", "destination_place_id",
                   "is_default"):
        assert phrase in text, phrase


# ---------- 장면 7 ----------

def test_장면7_행사_이름만_주면_대표_장소에서_서면역까지_제안한다():
    result = get_return_options(date=DAY, event_name=FESTIVAL)
    expected = {
        "date": DAY,
        "basis": {
            "kind": "rule", "measured": False,
            "assumed_window": {"before_end_min": 30, "after_end_min": 60},
            "travel_time_rule": {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 10, "walk_kmh": 4.5},
            "note": "Rule-based estimate, not measured or real-time crowding. The crowded window (30 min before to "
                    "60 min after the event end) is an assumption. Travel times use live Kakao public-transit routes "
                    "when available and otherwise fall back to estimates from station coordinates; they exclude "
                    "walking to and from places. Kakao route results are not stored or cached. Last-train warnings "
                    "use the stored Busan Metro standard timetable when the requested station and direction are "
                    "available; actual train times can differ.",
        },
        "event": {"name": FESTIVAL, "start": "2026-11-28T18:00:00+09:00", "end": "2026-11-28T23:00:00+09:00",
                  "main_place_id": "sea-life-busan"},
        "origin": {"place_id": "sea-life-busan", "station": "Haeundae"},
        "destination": {"station": "Seomyeon", "place_id": None, "is_default": True},
        "congested_station": {"station": "Haeundae", "main_place_id": "sea-life-busan",
                              "from": "2026-11-28T22:30:00+09:00", "to": "2026-11-29T00:00:00+09:00"},
        "baseline": {"depart_at": "2026-11-28T23:00:00+09:00", "station": "Haeundae", "congested": True,
                     "minutes": 39, "mode": "subway", "time_source": "estimate",
                     "last_train": "23:29", "warnings": []},
        "options": [
            {"type": "shift_earlier", "depart_at": "2026-11-28T22:20:00+09:00", "station": "Haeundae", "walk_min": 0,
             "extra_min": 0, "avoids_congestion": True, "warnings": ["leaves_before_event_end"],
             "time_source": "estimate", "last_train": "23:29"},
            {"type": "shift_later", "depart_at": "2026-11-29T00:00:00+09:00", "station": "Haeundae", "walk_min": 0,
             "extra_min": 0, "avoids_congestion": True,
             "warnings": ro.last_train_warnings(
                 dt.date.fromisoformat(DAY), "Haeundae", "Seomyeon",
                 dt.datetime.fromisoformat("2026-11-29T00:00:00+09:00"),
             ), "time_source": "estimate", "last_train": "23:29"},
            # 설계 「장면 7 어림값」: 동백 도보 18 + 지하철 36 − 39 = +15, 중동 17 + 42 − 39 = +20
            {"type": "walk_to_station", "depart_at": "2026-11-28T23:00:00+09:00", "station": "Dongbaek",
             "walk_min": 18, "extra_min": 15, "avoids_congestion": True, "warnings": [], "time_source": "estimate",
             "last_train": "23:31"},
            {"type": "walk_to_station", "depart_at": "2026-11-28T23:00:00+09:00", "station": "Jung-dong",
             "walk_min": 17, "extra_min": 20, "avoids_congestion": True, "warnings": [], "time_source": "estimate",
             "last_train": "23:28"},
        ],
    }
    # ranked 는 손으로 적은 위 기대값을 rank_routes 에 넣은 결과와 같다 (카카오가 없으면 추정값 그대로 채점한다)
    expected["ranked"] = [route.model_dump() for route in rank_routes(expected)]
    assert result == expected
    assert [(r["option"]["station"], r["option"]["type"], r["labels"]) for r in result["ranked"]] == [
        ("Dongbaek", "walk_to_station", ["best"]),
        ("Jung-dong", "walk_to_station", []),
        ("Haeundae", "shift_earlier", ["earliest_arrival", "least_walking"]),
    ]
    assert json.loads(json.dumps(result)) == result  # JSON 으로 그대로 나간다
    assert "ratio" not in json.dumps(result)  # 집중률·혼잡 등급을 넣지 않는다


def test_막차_시간표가_있으면_출발_시각과_비교하고_없으면_unknown(data_dir, tmp_path):
    def save(last_train: str, toward: str = "Seomyeon") -> None:
        data_dir("last_trains.json", {"stations": {
            "Haeundae": {"scode": "203", "toward": toward, "updown": 1,
                           "last_train": {"1": last_train, "2": last_train, "3": last_train}}
        }})

    save("24:00")
    on_time = get_return_options(date=DAY, event_name=FESTIVAL)
    assert next(o for o in on_time["options"] if o["type"] == "shift_later")["warnings"] == []  # 같은 시각은 이후가 아니다

    save("23:59")
    missed = get_return_options(date=DAY, event_name=FESTIVAL)
    assert next(o for o in missed["options"] if o["type"] == "shift_later")["warnings"] == ["last_train_missed"]

    save("24:10", toward="다른 방향")
    wrong_direction = get_return_options(date=DAY, event_name=FESTIVAL)
    assert next(o for o in wrong_direction["options"] if o["type"] == "shift_later")["warnings"] == ["last_train_unknown"]

    (tmp_path / "last_trains.json").unlink()
    unavailable = get_return_options(date=DAY, event_name=FESTIVAL)
    assert next(o for o in unavailable["options"] if o["type"] == "shift_later")["warnings"] == ["last_train_unknown"]


def last_trains(result) -> dict[tuple[str, str], tuple]:
    rows = [{"type": "baseline", **result["baseline"]}, *result["options"]]
    return {(row["type"], row["station"]): (row["last_train"], row["warnings"]) for row in rows}


def test_막차_전_출발이면_모든_항목에_막차_시각이_있고_경고가_없다():
    result = get_return_options(date=DAY, event_name=FESTIVAL, planned_departure="22:40")
    assert last_trains(result) == {
        ("baseline", "Haeundae"): ("23:29", []),
        ("shift_earlier", "Haeundae"): ("23:29", ["leaves_before_event_end"]),
        ("shift_later", "Haeundae"): ("23:29", ["last_train_missed"]),  # 11/29 00:00 출발
        ("walk_to_station", "Dongbaek"): ("23:31", []),
        ("walk_to_station", "Jung-dong"): ("23:28", []),
    }
    assert all(row["option"]["last_train"] for row in result["ranked"])  # ranked 의 option 에도 그대로 있다


def test_막차_뒤에_역에_닿는_항목은_모두_missed이고_ranked에서_빠진다():
    # 23:15 출발: 해운대(23:29)는 탈 수 있고, 동백은 23:33 도착(막차 23:31), 중동은 23:32 도착(막차 23:28)
    result = get_return_options(date=DAY, event_name=FESTIVAL, planned_departure="23:15")
    assert last_trains(result) == {
        ("baseline", "Haeundae"): ("23:29", []),
        ("shift_earlier", "Haeundae"): ("23:29", ["leaves_before_event_end"]),
        ("shift_later", "Haeundae"): ("23:29", ["last_train_missed"]),
        ("walk_to_station", "Dongbaek"): ("23:31", ["last_train_missed"]),  # 걸어서 역에 닿는 시각으로 비교한다
        ("walk_to_station", "Jung-dong"): ("23:28", ["last_train_missed"]),
    }
    assert [row["option"]["type"] for row in result["ranked"]] == ["shift_earlier"]
    late = get_return_options(date=DAY, event_name=FESTIVAL, planned_departure="23:30")
    assert late["baseline"]["warnings"] == ["last_train_missed"]


def test_막차_표가_없으면_last_train은_null이고_unknown(data_dir, tmp_path):
    (tmp_path / "last_trains.json").unlink()
    result = get_return_options(date=DAY, event_name=FESTIVAL, planned_departure="22:40")
    assert last_trains(result) == {
        ("baseline", "Haeundae"): (None, ["last_train_unknown"]),
        ("shift_earlier", "Haeundae"): (None, ["leaves_before_event_end", "last_train_unknown"]),
        ("shift_later", "Haeundae"): (None, ["last_train_unknown"]),
        ("walk_to_station", "Dongbaek"): (None, ["last_train_unknown"]),
        ("walk_to_station", "Jung-dong"): (None, ["last_train_unknown"]),
    }
    # 자정 뒤 막차는 24시 이상 그대로 돌려준다. 걸어서 도착역까지 가는 안은 열차를 타지 않는다
    data_dir("last_trains.json", {"stations": {"Haeundae": {"toward": "Seomyeon", "last_train": {"2": "24:05"}}}})
    assert get_return_options(date=DAY, event_name=FESTIVAL)["baseline"]["last_train"] == "24:05"
    walk = walks(get_return_options(date=DAY, event_name=FESTIVAL, destination_station="Dongbaek"))["Dongbaek"]
    assert (walk["last_train"], walk["warnings"]) == (None, [])


def test_막차_요일_코드는_평일_토요일_일요일을_구분한다():
    assert ro._service_day_code(dt.date(2026, 11, 27)) == "1"
    assert ro._service_day_code(dt.date(2026, 11, 28)) == "2"
    assert ro._service_day_code(dt.date(2026, 11, 29)) == "3"


def test_장면7_place_id만_주면_그_장소가_출발_장소다():
    by_name = get_return_options(date=DAY, event_name=FESTIVAL)
    by_place = get_return_options(date=DAY, place_id="haeundae-beach")
    assert by_place["origin"] == {"place_id": "haeundae-beach", "station": "Haeundae"}
    assert by_place["event"] == by_name["event"] and by_place["options"] == by_name["options"]
    both = get_return_options(date=DAY, event_name=FESTIVAL, place_id="haeundae-market")
    assert both["origin"]["place_id"] == "haeundae-market" and both["options"] == by_name["options"]


def test_혼잡_역은_대표_장소의_역_하나뿐이고_다른_역에서_출발하면_제안이_없다():
    # the-bay-101 은 행사 장소(place_ids)지만 가까운 역이 동백이라 혼잡 역(해운대)에서 출발하지 않는다
    result = get_return_options(date=DAY, place_id="the-bay-101")
    assert result["congested_station"]["station"] == "Haeundae"
    assert result["origin"] == {"place_id": "the-bay-101", "station": "Dongbaek"}
    assert result["baseline"] == {"depart_at": "2026-11-28T23:00:00+09:00", "station": "Dongbaek", "congested": False,
                                  "minutes": 36, "mode": "subway", "last_train": "23:31", "warnings": [],
                                  "time_source": "estimate"}  # 제안이 없어도 기준 이동 시간과 막차는 준다
    assert result["options"] == [] and result["ranked"] == []


# ---------- 도착역 ----------

def test_도착역_정규화_장소로_지정_우선순위():
    assert get_return_options(date=DAY, event_name=FESTIVAL, destination_station=" seomyeon ")["destination"] == {
        "station": "Seomyeon", "place_id": None, "is_default": False}  # 직접 지정은 기본값이 아니다
    by_place = get_return_options(date=DAY, event_name=FESTIVAL, destination_place_id="gwangalli-beach")
    station = next(p["nearest_station"] for p in load("places.json") if p["place_id"] == "gwangalli-beach")
    assert by_place["destination"] == {"station": station, "place_id": "gwangalli-beach", "is_default": False}
    # 둘 다 주면 destination_station 이 우선이고 destination_place_id 는 검증도 하지 않는다
    both = get_return_options(date=DAY, event_name=FESTIVAL, destination_station="BUSAN STATION",
                              destination_place_id="no-such-place")
    assert both["destination"] == {"station": "Busan Station", "place_id": None, "is_default": False}
    assert both["baseline"]["minutes"] != by_place["baseline"]["minutes"]


def test_도착역_오류():
    def code(**kwargs):
        return error_code(get_return_options(date=DAY, event_name=FESTIVAL, **kwargs))

    assert code(destination_station="Osiria") == "station_not_found"  # 동해선은 역 표에 없다
    assert code(destination_place_id="no-such-place") == "place_not_found"
    assert code(destination_place_id="taejongdae") == "no_station"  # nearest_station 이 null
    assert code(destination_place_id="haedong-yonggungsa") == "no_station"  # OSIRIA: 역 표에 없는 역
    assert code(destination_station="Haeundae") == "same_station"
    assert code(destination_place_id="haeundae-market") == "same_station"
    # 혼잡 역이 아닌 역에서 출발해도, 그 역이 도착역이면 제안할 것이 없다
    assert error_code(get_return_options(date=DAY, place_id="the-bay-101", destination_station="Dongbaek")) == "same_station"


def test_이용할_역이_도착역이면_지하철_시간은_0분():
    result = get_return_options(date=DAY, event_name=FESTIVAL, destination_station="Dongbaek")
    option = walks(result)["Dongbaek"]
    assert option["extra_min"] == option["walk_min"] - result["baseline"]["minutes"] == 18 - 14
    assert result["options"][0]["type"] == "shift_earlier"  # extra_min 이 작은 순, 같으면 시각 제안이 먼저


# ---------- 이동 시간 규칙 ----------

def test_이동_시간_규칙은_travel_times_json의_rule을_읽는다(data_dir):
    assert load("travel_times.json")["rule"] == {
        "route_factor": 1.3, "walk_max_km": 1.2, "walk_kmh": 4.5, "subway_kmh": 25, "subway_overhead_min": 10}
    data_dir("travel_times.json", {"rule": {"route_factor": 1.3, "walk_kmh": 9, "subway_kmh": 25,
                                            "subway_overhead_min": 0}, "pairs": []})
    result = get_return_options(date=DAY, event_name=FESTIVAL)
    assert result["basis"]["travel_time_rule"] == {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 0,
                                                   "walk_kmh": 9}
    assert result["baseline"]["minutes"] == 29  # 39분에서 고정 10분이 빠진다
    assert (walks(result)["Dongbaek"]["walk_min"], walks(result)["Jung-dong"]["walk_min"]) == (9, 9)  # 걷는 속도 2배


def test_도보_상한_이내의_역만_가까운_순으로_최대_5개(monkeypatch):
    result = get_return_options(date=DAY, event_name=FESTIVAL)
    assert set(walks(result)) == {"Dongbaek", "Jung-dong"}  # 장산(31분)·시립미술관(34분)은 20분을 넘는다
    assert all(o["walk_min"] <= ro.WALK_ALT_MAX_MIN for o in walks(result).values())
    monkeypatch.setattr(ro, "WALK_ALT_MAX_MIN", 60)
    wide = get_return_options(date=DAY, event_name=FESTIVAL)["options"]
    assert len(wide) == ro.MAX_OPTIONS == 5 and "Haeundae" not in walks({"options": wide})  # 혼잡 역은 후보가 아니다
    assert [o["extra_min"] for o in wide] == sorted(o["extra_min"] for o in wide)
    assert [o["type"] for o in wide[:2]] == ["shift_earlier", "shift_later"]
    assert {o["type"] for o in wide} == {"shift_earlier", "shift_later", "walk_to_station"}  # other_line 은 없다


# ---------- 혼잡 시간대 ----------

@pytest.mark.parametrize("planned, depart_at, congested", [
    ("22:29", "2026-11-28T22:29:00+09:00", False),
    ("22:30", "2026-11-28T22:30:00+09:00", True),  # 시작 포함
    ("23:59", "2026-11-28T23:59:00+09:00", True),
    ("00:00", "2026-11-29T00:00:00+09:00", False),  # 끝 제외. 행사 시작(18:00)보다 이른 시각은 다음 날
    ("17:59", "2026-11-29T17:59:00+09:00", False),
    ("18:00", "2026-11-28T18:00:00+09:00", False),
])
def test_혼잡_시간대_경계와_planned_departure(planned, depart_at, congested):
    result = get_return_options(date=DAY, event_name=FESTIVAL, planned_departure=planned)
    assert (result["baseline"]["depart_at"], result["baseline"]["congested"]) == (depart_at, congested)
    assert bool(result["options"]) == congested
    assert all(o["depart_at"] == depart_at for o in walks(result).values())  # 걸어서 다른 역은 출발 시각 그대로


def test_혼잡_시간대가_자정을_넘는다(data_dir):
    data_dir("events.json", {"events": [event("심야", end="23:30:00"), event("짧은", start="22:50:00", end="23:20:00",
                                                                           place_ids=["haeundae-market"])]})
    result = get_return_options(date=DAY, event_name="심야", planned_departure="00:10")
    assert (result["congested_station"]["from"], result["congested_station"]["to"]) == (
        "2026-11-28T23:00:00+09:00", "2026-11-29T00:30:00+09:00")
    assert result["baseline"] == {"depart_at": "2026-11-29T00:10:00+09:00", "station": "Haeundae", "congested": True,
                                  "minutes": 39, "mode": "subway", "time_source": "estimate",
                                  "last_train": "23:29", "warnings": ["last_train_missed"]}  # 00:10 은 막차 뒤
    assert [(o["type"], o["depart_at"]) for o in result["options"][:2]] == [
        ("shift_earlier", "2026-11-28T22:50:00+09:00"), ("shift_later", "2026-11-29T00:30:00+09:00")]
    assert error_code(get_return_options(date=DAY, event_name="심야", planned_departure="11pm")) == "invalid_time"
    # 종료 40분 전이 행사 시작보다 이르면 "일찍 떠나기"는 제안하지 않는다
    short = get_return_options(date=DAY, event_name="짧은")
    assert [o["type"] for o in short["options"]] == ["shift_later", "walk_to_station", "walk_to_station"]


# ---------- 행사 찾기와 오류 ----------

def test_입력_오류():
    assert error_code(get_return_options(date=DAY)) == "missing_argument"
    assert error_code(get_return_options(date="28/11", event_name=FESTIVAL)) == "invalid_date"
    assert error_code(get_return_options(date=DAY, place_id="no-such-place")) == "place_not_found"
    assert error_code(get_return_options(date=DAY, event_name="없는 행사")) == "event_not_found"
    assert error_code(get_return_options(date=DAY, place_id="busan-tower")) == "event_not_found"  # 행사 장소가 아니다
    assert error_code(get_return_options(date="2026-11-29", event_name=FESTIVAL)) == "event_not_found"  # 개막일만 나온다
    # 진행 시간을 모르는 행사(00:00~23:59)는 종료 시각을 짐작하지 않는다
    assert error_code(get_return_options(date="2026-11-07", event_name="부산불꽃축제")) == "no_time_basis"
    # 위치 인자 순서는 (date, place_id, event_name, ...) 이다. 행사 이름을 첫 자리에 넣으면 날짜 오류가 난다
    assert error_code(get_return_options(FESTIVAL, DAY, destination_station="Seomyeon")) == "invalid_date"


def test_행사가_여럿이거나_대표_장소에_역이_없을_때(data_dir):
    data_dir("events.json", {"events": [
        event("가"), event("나"),
        event("역 없음", place_ids=["taejongdae"], main="taejongdae"),
        event("대표 없음", place_ids=[], main=None),
        event("표에 없는 역", place_ids=["haedong-yonggungsa"], main="haedong-yonggungsa"),
    ]})
    result = get_return_options(date=DAY, place_id="haeundae-beach")
    assert error_code(result) == "ambiguous_event" and "가, 나" in result["error"]["message"]
    assert get_return_options(date=DAY, place_id="haeundae-beach", event_name="나")["event"]["name"] == "나"
    for name in ("역 없음", "대표 없음", "표에 없는 역"):
        assert error_code(get_return_options(date=DAY, event_name=name)) == "no_event_station"
    # 혼잡 역은 있지만 출발 장소에 쓸 역이 없으면 기준 이동 시간을 계산할 수 없다
    assert error_code(get_return_options(date=DAY, event_name="가", place_id="taejongdae")) == "no_station"


def test_파일을_못_읽으면_오류_dict(data_dir, tmp_path):
    (tmp_path / "stations.json").unlink()
    assert error_code(get_return_options(date=DAY, event_name=FESTIVAL)) == "data_unavailable"
    shutil.copy(REAL_DATA / "stations.json", tmp_path / "stations.json")
    (tmp_path / "events.json").unlink()
    assert error_code(get_return_options(date=DAY, event_name=FESTIVAL)) == "data_unavailable"


# ---------- 금지 사항·무결성 ----------

def test_응답의_장소_ID와_역_이름은_모두_데이터에_있다():
    places = {p["place_id"] for p in load("places.json")}
    stations = {s["station"] for s in load("stations.json")["stations"]}
    for kwargs in ({"event_name": FESTIVAL}, {"place_id": "busan-x-the-sky"},
                   {"event_name": FESTIVAL, "destination_place_id": "busan-tower"}):
        r = get_return_options(date=DAY, **kwargs)
        assert {r["event"]["main_place_id"], r["origin"]["place_id"], r["congested_station"]["main_place_id"]} <= places
        assert r["destination"]["place_id"] in places | {None}
        assert {r["origin"]["station"], r["destination"]["station"], r["congested_station"]["station"],
                r["baseline"]["station"], *(o["station"] for o in r["options"])} <= stations


def test_카카오_경로가_없으면_전부_추정이고_네트워크와_현재_시각을_쓰지_않는다(monkeypatch):
    # 카카오는 실시간 호출만 한다. 저장하는 역 표와 그 스크립트에는 카카오에서 온 값이 없다 (요구사항 6의 저장 금지)
    root = Path(build_stations.__file__).parent.parent
    for path in ("scripts/build_stations.py", "app/data/stations.json"):
        text = (root / path).read_text(encoding="utf-8").casefold()
        assert not any(word in text for word in ("kakao", "카카오", "http://", "https://")), path

    blocked_calls = []

    def blocked(*args, **kwargs):
        blocked_calls.append(args)  # 스레드 안에서 불려 예외가 삼켜져도 마지막에 잡는다
        pytest.fail("네트워크나 현재 시각을 쓰면 안 된다")

    monkeypatch.setattr(lookup.urllib.request, "urlopen", blocked)  # kakao_route 도 같은 urllib.request 를 쓴다
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(lookup, "_now", blocked)
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "TEST-KAKAO-KEY")  # 키가 있어도 결과는 같다

    # fetch_routes 가 None 이면(conftest 의 no_kakao) 시간은 전부 좌표 추정이고 카카오 경로 상세(legs 등)가 없다
    monkeypatch.setattr(config, "USE_MOCK", False)
    expected = get_return_options(date=DAY, event_name=FESTIVAL)
    assert expected["options"] and expected["ranked"]
    rows = [expected["baseline"], *expected["options"], *(r["option"] for r in expected["ranked"])]
    assert all(row["time_source"] == "estimate" for row in rows)
    assert not any(key in row for row in rows for key in ro.KAKAO_DETAIL_KEYS)

    for use_mock, demo_now in ((True, "2026-11-21T10:00:00+09:00"), (False, None)):
        monkeypatch.setattr(config, "USE_MOCK", use_mock)
        monkeypatch.setattr(config, "DEMO_NOW", demo_now, raising=False)
        assert get_return_options(date=DAY, event_name=FESTIVAL) == expected

    # USE_MOCK=1 이면 진짜 fetch_routes 를 끼워도 네트워크를 타지 않는다
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(ro, "fetch_routes", kakao_route.fetch_routes)
    stations = ro.station_table()
    haeundae, seomyeon = stations["Haeundae"], stations["Seomyeon"]
    assert kakao_route.fetch_routes(haeundae["lat"], haeundae["lng"], seomyeon["lat"], seomyeon["lng"]) is None
    assert get_return_options(date=DAY, event_name=FESTIVAL) == expected
    assert blocked_calls == []


def test_응답은_100ms_이내():
    get_return_options(date=DAY, event_name=FESTIVAL)
    started = time.perf_counter()
    get_return_options(date=DAY, event_name=FESTIVAL)
    assert time.perf_counter() - started < 0.1


# ---------- 역 표 ----------

def test_stations_json은_CSV로_다시_만든_값과_같고_환승역은_한_항목이다():
    with build_stations.CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    stations = build_stations.build_stations(rows)
    unmatched = build_stations.add_names(stations, build_stations.read_name_rows())
    assert build_stations.dump_stations(stations) == (REAL_DATA / "stations.json").read_text(encoding="utf-8")
    names = [s["station"] for s in stations]
    assert (len(rows), len(names), len(set(names))) == (114, 108, 108)  # 환승역 6곳을 합친다
    by_name = {s["station"]: s for s in stations}
    assert {n for n, s in by_name.items() if len(s["lines"]) > 1} == {
        "Seomyeon", "Yeonsan", "Dongnae", "Suyeong", "Deokcheon", "Minam"}
    assert by_name["Seomyeon"] == {"station": "Seomyeon", "name_ko": "서면역", "lines": ["1", "2"],
                                   "lat": 35.158011, "lng": 129.05932,  # 1·2호선 두 행의 평균 좌표
                                   "names": {"ja": "西面", "zh-Hans": "西面", "zh-Hant": "西面"}}
    # 일본어·중국어 역명은 2호선 역명 파일에 있는 값만 넣는다. 2호선 밖 역과 빈 칸은 넣지 않는다
    assert by_name["Haeundae"]["names"] == {"ja": "海雲台", "zh-Hans": "海云台", "zh-Hant": "海雲台"}
    assert by_name["Dongbaek"]["names"] == {"ja": "冬柏", "zh-Hans": "冬柏", "zh-Hant": "冬柏"}
    assert by_name["Jung-dong"]["names"] == {"ja": "中洞", "zh-Hans": "中洞", "zh-Hant": "中洞"}
    assert by_name["Centum City"]["names"] == {"ja": "センタムシティ"}  # 출처의 중국어 칸이 비어 있다
    assert not [n for n, s in by_name.items() if "2" not in s["lines"] and "names" in s]
    assert by_name["Busan Station"].keys() == {"station", "name_ko", "lines", "lat", "lng"}
    assert all(s["names"] and set(s["names"]) <= set(build_stations.NAME_LANGS) and all(s["names"].values())
               for s in stations if "names" in s)
    assert unmatched == ["Busan Museum of Art", "Kyungsung Univ. Pukyong Nat'l Univ.",
                         "Busan Int'l Finance Center Busan Bank"]  # 역명 표기가 달라 맞지 않는 2호선 역
    assert by_name[ro.DEFAULT_DESTINATION_STATION] and by_name["Haeundae"]["name_ko"] == "해운대역"
    # places.json 의 nearest_station 중 표에 없는 값은 동해선 OSIRIA 하나뿐이다
    assert {p["nearest_station"] for p in load("places.json")} - set(names) - {None} == {"OSIRIA"}


def test_작은따옴표가_든_역_이름은_1개로_복원한_값이다():
    # busan_stations.csv 원본의 이중 이스케이프(Nat''''''''l)를 작은따옴표 1개로 고쳤다
    by_name = {s["station"]: s["name_ko"] for s in load("stations.json")["stations"]}
    fixed = {"Busan Nat'l Univ. of Edu.": "교대역", "Pusan Nat'l Univ.": "부산대역",
             "Kyungsung Univ. Pukyong Nat'l Univ.": "경성대부경대역",
             "Busan Int'l Finance Center Busan Bank": "국제금융센터부산은행역",
             "Pusan Nat'l Univ. Yangsan Campus": "부산대양산캠퍼스역"}
    assert {name: by_name.get(name) for name in fixed} == fixed
    assert {name for name in by_name if "'" in name} == set(fixed) and not any("''" in name for name in by_name)
    result = get_return_options(date=DAY, event_name=FESTIVAL, destination_station="pusan nat'l univ.")
    assert result["destination"]["station"] == "Pusan Nat'l Univ."
