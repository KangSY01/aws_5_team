"""귀가 분산 도구(app/tools/return_options.py)와 역 표(scripts/build_stations.py) 테스트. 네트워크를 쓰지 않는다."""

import csv
import json
import re
import shutil
import socket
import time
from pathlib import Path

import pytest

from app import config
from app.tools import lookup
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
                   "assumption made without supporting data", "station coordinates", "last train time is unknown",
                   "defaults to Seomyeon", "destination_place_id", "is_default"):
        assert phrase in text, phrase


# ---------- 장면 7 ----------

def test_장면7_행사_이름만_주면_대표_장소에서_서면역까지_제안한다():
    result = get_return_options(date=DAY, event_name=FESTIVAL)
    assert result == {
        "date": DAY,
        "basis": {
            "kind": "rule", "measured": False,
            "assumed_window": {"before_end_min": 30, "after_end_min": 60},
            "travel_time_rule": {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 10, "walk_kmh": 4.5},
            "note": "Rule-based estimate, not measured or real-time crowding. The crowded window (30 min before to "
                    "60 min after the event end) is an assumption. Travel times are estimated from station "
                    "coordinates, not routes or timetables, and exclude walking to and from stations.",
        },
        "event": {"name": FESTIVAL, "start": "2026-11-28T18:00:00+09:00", "end": "2026-11-28T23:00:00+09:00",
                  "main_place_id": "sea-life-busan"},
        "origin": {"place_id": "sea-life-busan", "station": "Haeundae"},
        "destination": {"station": "Seomyeon", "place_id": None, "is_default": True},
        "congested_station": {"station": "Haeundae", "main_place_id": "sea-life-busan",
                              "from": "2026-11-28T22:30:00+09:00", "to": "2026-11-29T00:00:00+09:00"},
        "baseline": {"depart_at": "2026-11-28T23:00:00+09:00", "station": "Haeundae", "congested": True,
                     "minutes": 39, "mode": "subway"},
        "options": [
            {"type": "shift_earlier", "depart_at": "2026-11-28T22:20:00+09:00", "station": "Haeundae", "walk_min": 0,
             "extra_min": 0, "avoids_congestion": True, "warnings": ["leaves_before_event_end"]},
            {"type": "shift_later", "depart_at": "2026-11-29T00:00:00+09:00", "station": "Haeundae", "walk_min": 0,
             "extra_min": 0, "avoids_congestion": True, "warnings": ["last_train_unknown"]},
            # 설계 「장면 7 어림값」: 동백 도보 18 + 지하철 36 − 39 = +15, 중동 17 + 42 − 39 = +20
            {"type": "walk_to_station", "depart_at": "2026-11-28T23:00:00+09:00", "station": "Dongbaek",
             "walk_min": 18, "extra_min": 15, "avoids_congestion": True, "warnings": []},
            {"type": "walk_to_station", "depart_at": "2026-11-28T23:00:00+09:00", "station": "Jung-dong",
             "walk_min": 17, "extra_min": 20, "avoids_congestion": True, "warnings": []},
        ],
    }
    assert json.loads(json.dumps(result)) == result  # JSON 으로 그대로 나간다
    assert "ratio" not in json.dumps(result)  # 집중률·혼잡 등급을 넣지 않는다


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
                                  "minutes": 36, "mode": "subway"}  # 제안이 없어도 기준 이동 시간은 준다
    assert result["options"] == []


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
                                  "minutes": 39, "mode": "subway"}
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


def test_경로_API_값이_없고_네트워크와_현재_시각을_쓰지_않는다(monkeypatch):
    root = Path(build_stations.__file__).parent.parent
    for path in ("app/tools/return_options.py", "scripts/build_stations.py", "app/data/stations.json"):
        text = (root / path).read_text(encoding="utf-8").casefold()
        assert not any(word in text for word in ("kakao", "카카오", "http://", "https://")), path
    expected = get_return_options(date=DAY, event_name=FESTIVAL)

    def blocked(*args, **kwargs):
        pytest.fail("네트워크나 현재 시각을 쓰면 안 된다")

    monkeypatch.setattr(lookup.urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(lookup, "_now", blocked)
    for use_mock, demo_now in ((True, "2026-11-21T10:00:00+09:00"), (False, None)):
        monkeypatch.setattr(config, "USE_MOCK", use_mock)
        monkeypatch.setattr(config, "DEMO_NOW", demo_now, raising=False)
        assert get_return_options(date=DAY, event_name=FESTIVAL) == expected


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
    assert build_stations.dump_stations(stations) == (REAL_DATA / "stations.json").read_text(encoding="utf-8")
    names = [s["station"] for s in stations]
    assert (len(rows), len(names), len(set(names))) == (114, 108, 108)  # 환승역 6곳을 합친다
    by_name = {s["station"]: s for s in stations}
    assert {n for n, s in by_name.items() if len(s["lines"]) > 1} == {
        "Seomyeon", "Yeonsan", "Dongnae", "Suyeong", "Deokcheon", "Minam"}
    assert by_name["Seomyeon"] == {"station": "Seomyeon", "name_ko": "서면역", "lines": ["1", "2"],
                                   "lat": 35.158011, "lng": 129.05932}  # 1·2호선 두 행의 평균 좌표
    assert by_name[ro.DEFAULT_DESTINATION_STATION] and by_name["Haeundae"]["name_ko"] == "해운대역"
    # places.json 의 nearest_station 중 표에 없는 값은 동해선 OSIRIA 하나뿐이다
    assert {p["nearest_station"] for p in load("places.json")} - set(names) - {None} == {"OSIRIA"}
