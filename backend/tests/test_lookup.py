"""조회 도구(app/tools/lookup.py) 테스트. 네트워크를 쓰지 않는다."""

import datetime as dt
import json
import re
import urllib.error

import pytest
from pydantic import TypeAdapter

from app import config
from app.guardian import context as guardian_context
from app.guardian.context import Event, HourlyWeather, OpeningHours
from app.guardian.thresholds import WEEKDAY_RULE_PLACES
from app.models.plan import Place, Plan
from app.tools import lookup
from scripts import build_travel_times, fetch_events

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 11, 20, 11, 30, tzinfo=KST)  # 실제 예보 경로의 "현재"


def ids(result) -> set[str]:
    return {p["place_id"] for p in result}


def error_code(result) -> str:
    assert set(result) == {"error"} and set(result["error"]) == {"code", "message"}
    return result["error"]["code"]


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("USE_MOCK=1 에서는 호출하지 않는다"))


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "SECRET")
    monkeypatch.setattr(lookup, "_now", lambda: NOW)


class _Resp:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def kma(rows, code="00"):
    """rows: (fcstDate, fcstTime, category, fcstValue)."""
    items = [{"fcstDate": d, "fcstTime": t, "category": c, "fcstValue": v} for d, t, c, v in rows]
    return {"response": {"header": {"resultCode": code, "resultMsg": "x"}, "body": {"items": {"item": items}}}}


# ---------- 도구 등록 ----------

def test_조회_도구는_Strands_도구이고_입력_설명이_있다():
    for fn, args in [(lookup.search_places, {"query", "category", "indoor"}), (lookup.get_crowd, {"place_id", "date"}),
                     (lookup.get_weather, {"date"}), (lookup.get_hours, {"place_id"}),
                     (lookup.get_place_info, {"place_id"}),
                     (lookup.get_travel_time, {"from_place_id", "to_place_id"}), (lookup.get_events, {"date"})]:
        props = fn.tool_spec["inputSchema"]["json"]["properties"]
        assert set(props) == args and all(p.get("description") for p in props.values())
        assert len(fn.tool_spec["description"]) > 50


# ---------- search_places ----------

def test_search_places_이름_4개_언어와_place_id_부분_일치_대소문자_무시():
    assert "haeundae-beach" in ids(lookup.search_places(query="HAEUNDAE b"))  # en, 대소문자
    assert "haeundae-beach" in ids(lookup.search_places(query="海雲台"))  # ja
    assert "haeundae-beach" in ids(lookup.search_places(query="海云台"))  # zh-Hans
    assert "haeundae-beach" in ids(lookup.search_places(query="海雲臺"))  # zh-Hant
    assert ids(lookup.search_places(query="yonggungsa")) == {"haedong-yonggungsa"}  # place_id 의 일부
    assert lookup.search_places(query="no such place") == []


def test_search_places_결과는_Place_형식이고_빈_query는_전부():
    everything = lookup.search_places(query="")
    assert len(everything) >= 30
    TypeAdapter(list[Place]).validate_python(everything)


def test_search_places_category와_indoor로_거른다():
    markets = lookup.search_places(query="", category="Market")
    assert markets and all(p["category"] == "market" for p in markets)
    indoor = lookup.search_places(query="", indoor=True)
    outdoor = lookup.search_places(query="", indoor=False)
    assert indoor and all(p["indoor"] for p in indoor) and outdoor and not any(p["indoor"] for p in outdoor)
    assert ids(lookup.search_places(query="market", category="market", indoor=True)) == {"jagalchi-market"}
    assert lookup.search_places(query="haeundae", category="temple") == []


def test_search_places_파일을_못_읽으면_오류_dict(monkeypatch, tmp_path):
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert error_code(lookup.search_places(query="x")) == "data_unavailable"


# ---------- get_crowd ----------

def test_get_crowd_집중률이_없는_장소는_ratio_null_weekday_rule():
    for place_id in [*WEEKDAY_RULE_PLACES, "busan-tower"]:  # congestion.json 에 없는 장소
        assert lookup.get_crowd(place_id=place_id, date="2026-11-21") == {
            "place_id": place_id, "date": "2026-11-21", "ratio": None, "source": "weekday_rule"}


def test_get_crowd_congestion_json_에_값이_있으면_concentration(monkeypatch, tmp_path):
    (tmp_path / "places.json").write_text('[{"place_id": "a"}, {"place_id": "b"}]', encoding="utf-8")
    (tmp_path / "congestion.json").write_text('{"meta": {}, "places": {"a": {"2026-11-21": 87.5}}}', encoding="utf-8")
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert lookup.get_crowd(place_id="a", date="2026-11-21") == {
        "place_id": "a", "date": "2026-11-21", "ratio": 87.5, "source": "concentration"}
    for place_id, date in (("a", "2026-11-22"), ("b", "2026-11-21")):  # 기간 밖 날짜, 표에 없는 장소
        result = lookup.get_crowd(place_id=place_id, date=date)
        assert (result["ratio"], result["source"]) == (None, "weekday_rule")
    (tmp_path / "congestion.json").unlink()
    assert error_code(lookup.get_crowd(place_id="a", date="2026-11-21")) == "data_unavailable"


def test_get_crowd_실제_데이터_기간_안은_값_기간_밖은_weekday_rule():
    data = json.loads((lookup.DATA_DIR / "congestion.json").read_text(encoding="utf-8"))
    result = lookup.get_crowd(place_id="haeundae-beach", date="2026-11-28")
    assert result["source"] == "concentration" and result["ratio"] == data["places"]["haeundae-beach"]["2026-11-28"]
    assert 0 <= result["ratio"] <= 100
    for date in ("2026-11-17", "2026-12-18", "2027-06-01"):  # 받아 둔 기간(11/18~12/17) 밖
        result = lookup.get_crowd(place_id="haeundae-beach", date=date)
        assert (result["ratio"], result["source"]) == (None, "weekday_rule")


def test_get_crowd_잘못된_입력은_오류_dict():
    assert error_code(lookup.get_crowd(place_id="haeundae-beach", date="11/21")) == "invalid_date"
    assert error_code(lookup.get_crowd(place_id="no-such-place", date="2026-11-21")) == "place_not_found"


# ---------- get_weather (USE_MOCK=1) ----------

def test_get_weather_샘플_예보(mock_mode):
    result = lookup.get_weather(date="2026-11-21")
    assert result["date"] == "2026-11-21" and len(result["hourly"]) == 24
    hourly = TypeAdapter(list[HourlyWeather]).validate_python(result["hourly"])
    assert all(h.time.date() == dt.date(2026, 11, 21) and h.time.utcoffset() == dt.timedelta(hours=9) for h in hourly)
    # 샘플 일정의 s4(15:30-17:00, 해운대)가 비에 걸린다: check_response.json 의 s4-rain 과 같은 시나리오
    assert [(h.pop, h.pty) for h in hourly if h.time.hour in (15, 16)] == [(80, 1), (80, 1)]
    assert not any(h.has_precipitation for h in hourly if h.time.hour < 15)


def test_get_weather_샘플에_없는_날짜는_예보_없음(mock_mode):
    assert lookup.get_weather(date="2026-12-25") == {"date": "2026-12-25", "hourly": []}


def test_get_weather_잘못된_날짜는_오류_dict(mock_mode):
    assert error_code(lookup.get_weather(date="tomorrow")) == "invalid_date"


# ---------- get_weather (USE_MOCK=0, 기상청) ----------

@pytest.mark.parametrize("now, expected", [
    ((2026, 11, 20, 11, 30), (2026, 11, 20, 11)),
    ((2026, 11, 20, 11, 9), (2026, 11, 20, 8)),  # 발표 10분 전이면 이전 발표분
    ((2026, 11, 20, 11, 10), (2026, 11, 20, 11)),
    ((2026, 11, 20, 2, 5), (2026, 11, 19, 23)),  # 새벽에는 전날 23시
    ((2026, 11, 20, 0, 5), (2026, 11, 19, 23)),
    ((2026, 11, 20, 23, 59), (2026, 11, 20, 23)),
])
def test_latest_kma_base(now, expected):
    assert lookup.latest_kma_base(dt.datetime(*now, tzinfo=KST)) == dt.datetime(*expected, tzinfo=KST)


def test_get_weather_기상청_응답을_시간별로_변환(real_mode, monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout):
        seen.update(url=url, timeout=timeout)
        return _Resp(kma([
            ("20261121", "1500", "TMP", "12"), ("20261121", "1500", "POP", "80"), ("20261121", "1500", "PTY", "1"),
            ("20261121", "1400", "PTY", "0"), ("20261121", "1400", "POP", "60"), ("20261121", "1400", "PCP", "강수없음"),
            ("20261121", "1600", "POP", "70"),  # PTY 가 없으면 0
            ("20261121", "1700", "PTY", "4"),  # POP 이 없으면 뺀다
            ("20261122", "0000", "POP", "30"), ("20261122", "0000", "PTY", "0"),  # 다른 날짜
        ]))

    monkeypatch.setattr(lookup.urllib.request, "urlopen", fake_urlopen)
    result = lookup.get_weather(date="2026-11-21")
    assert result == {"date": "2026-11-21", "hourly": [
        {"time": "2026-11-21T14:00:00+09:00", "pop": 60, "pty": 0},
        {"time": "2026-11-21T15:00:00+09:00", "pop": 80, "pty": 1},
        {"time": "2026-11-21T16:00:00+09:00", "pop": 70, "pty": 0},
    ]}
    TypeAdapter(list[HourlyWeather]).validate_python(result["hourly"])
    assert seen["timeout"] == 5 and seen["url"].startswith(lookup.KMA_URL + "?")
    for part in ("nx=98", "ny=76", "base_date=20261120", "base_time=1100", "dataType=JSON"):
        assert part in seen["url"]


def test_get_weather_예보_범위_밖_날짜는_호출하지_않고_빈_목록(real_mode, monkeypatch):
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("호출하지 않는다"))
    assert lookup.get_weather(date="2026-11-30") == {"date": "2026-11-30", "hourly": []}  # 약 3일 이후
    assert lookup.get_weather(date="2026-11-19") == {"date": "2026-11-19", "hourly": []}  # 지난 날짜


def test_get_weather_범위_안이어도_응답에_없으면_빈_목록(real_mode, monkeypatch):
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: _Resp(kma([("20261121", "0900", "POP", "20")])))
    assert lookup.get_weather(date="2026-11-24")["hourly"] == []
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: _Resp(kma([], code="03")))  # NO_DATA
    assert lookup.get_weather(date="2026-11-21")["hourly"] == []


def test_get_weather_500은_1회_재시도(real_mode, monkeypatch):
    calls = []

    def flaky(url, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("http://x", 500, "err", {}, None)
        return _Resp(kma([("20261120", "1800", "POP", "10"), ("20261120", "1800", "PTY", "0")]))

    monkeypatch.setattr(lookup.urllib.request, "urlopen", flaky)
    assert lookup.get_weather(date="2026-11-20")["hourly"] == [{"time": "2026-11-20T18:00:00+09:00", "pop": 10, "pty": 0}]
    assert len(calls) == 2


@pytest.mark.parametrize("failure, attempts", [
    (urllib.error.HTTPError("http://x", 500, "err", {}, None), 2),
    (urllib.error.HTTPError("http://x", 403, "err", {}, None), 1),  # 4xx 는 재시도하지 않는다
    (TimeoutError("timed out"), 2),
    (ValueError("https://x?serviceKey=SECRET"), 2),  # 예외 메시지에 URL 이 들어 있어도 새지 않는다
])
def test_get_weather_호출_실패는_오류_dict_키는_남기지_않는다(real_mode, monkeypatch, caplog, failure, attempts):
    calls = []

    def boom(url, timeout):
        calls.append(1)
        raise failure

    monkeypatch.setattr(lookup.urllib.request, "urlopen", boom)
    with caplog.at_level("DEBUG"):
        result = lookup.get_weather(date="2026-11-21")
    assert error_code(result) == "upstream_error" and len(calls) == attempts
    assert "SECRET" not in json.dumps(result) and "SECRET" not in caplog.text


def test_get_weather_이상한_응답은_오류_dict(real_mode, monkeypatch):
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: _Resp(b"<OpenAPI_ServiceResponse/>"))  # 키 오류는 XML
    assert error_code(lookup.get_weather(date="2026-11-21")) == "upstream_error"
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: _Resp({"response": {"header": {}}}))
    assert error_code(lookup.get_weather(date="2026-11-21")) == "upstream_error"
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: _Resp(kma([], code="30")))
    assert error_code(lookup.get_weather(date="2026-11-21")) == "upstream_error"


def test_get_weather_키가_없으면_호출하지_않고_오류_dict(real_mode, monkeypatch):
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "")
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("호출하지 않는다"))
    assert error_code(lookup.get_weather(date="2026-11-21")) == "missing_key"


# ---------- get_hours ----------

HOURS_KEYS = {"place_id", "opens", "closes", "closed_weekdays", "closed_dates", "raw_text"}


def test_get_hours_hours_json_의_값을_돌려준다():
    tower = lookup.get_hours(place_id="busan-tower")
    assert tower == {"place_id": "busan-tower", "opens": "10:00", "closes": "22:00", "closed_weekdays": [],
                     "closed_dates": [], "raw_text": "이용시간: 10:00~22:00 (발권 마감 21:30)\n쉬는날: 연중무휴"}
    museum = lookup.get_hours(place_id="busan-museum")
    assert (museum["opens"], museum["closes"], museum["closed_weekdays"]) == ("09:00", "18:00", [0])
    # 계절별 시간처럼 한 구간으로 쓸 수 없으면 원문만 준다
    seasonal = lookup.get_hours(place_id="blueline-park")
    assert seasonal["opens"] is None and seasonal["closes"] is None and "동절기" in seasonal["raw_text"]
    assert error_code(lookup.get_hours(place_id="no-such-place")) == "place_not_found"


def test_get_hours_모든_장소가_OpeningHours_로_읽힌다():
    for place in lookup._load_places():
        result = lookup.get_hours(place_id=place["place_id"])
        assert set(result) == HOURS_KEYS
        OpeningHours.model_validate(result)  # Guardian 은 place_id·raw_text 를 무시한다


def test_get_hours_파일에_없는_장소는_모르는_값(monkeypatch, tmp_path):
    (tmp_path / "places.json").write_text('[{"place_id": "a"}]', encoding="utf-8")
    (tmp_path / "hours.json").write_text('{"hours": {}}', encoding="utf-8")
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert lookup.get_hours(place_id="a") == {"place_id": "a", "opens": None, "closes": None, "closed_weekdays": [],
                                              "closed_dates": [], "raw_text": None}
    (tmp_path / "hours.json").unlink()
    assert error_code(lookup.get_hours(place_id="a")) == "data_unavailable"


# ---------- get_place_info ----------

def test_get_place_info_Place와_큐레이션과_운영시간을_한_번에_돌려준다():
    info = lookup.get_place_info(place_id="haeundae-beach")
    place = {k: v for k, v in info.items() if k not in ("curation", "hours")}
    assert [place] == lookup.search_places(query="haeundae-beach")  # Place 필드는 search_places 와 같다
    Place.model_validate(place)
    assert set(info["curation"]) == {"tags", "foreigner_friendly", "crowd_alternatives", "rain_alternatives", "source"}
    assert info["curation"]["tags"] == ["sea", "nature"] and info["curation"]["foreigner_friendly"] == 3
    hours = lookup.get_hours(place_id="haeundae-beach")
    assert info["hours"] == {k: v for k, v in hours.items() if k != "place_id"}
    assert error_code(lookup.get_place_info(place_id="no-such-place")) == "place_not_found"


def test_search_places_결과에는_큐레이션을_넣지_않는다():
    assert all(set(p) == set(Place.model_fields) for p in lookup.search_places(query=""))


# ---------- get_weather 샘플 폴더 (app/data/weather/) ----------

def test_weather_폴더_파일은_이름_규칙과_get_weather_형식을_따른다():
    files = sorted((lookup.DATA_DIR / "weather").glob("*"))
    assert {f.name for f in files} >= {"rain-afternoon.json", "2026-11-21.json"}
    for f in files:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*\.json", f.name), f.name  # 소문자·숫자·하이픈만
        data = json.loads(f.read_text(encoding="utf-8"))
        assert {"date", "hourly"} <= set(data) <= {"date", "hourly", "note"}
        hourly = TypeAdapter(list[HourlyWeather]).validate_python(data["hourly"])
        assert all(h.time.date().isoformat() == data["date"] and h.time.utcoffset() == dt.timedelta(hours=9)
                   for h in hourly)


def test_rain_afternoon_프리셋은_13_15시만_비이고_Guardian이_읽는다():
    hourly = guardian_context.load_weather_preset("rain-afternoon")
    assert [h.time.hour for h in hourly] == list(range(9, 22)) and hourly[0].time.date() == dt.date(2026, 11, 28)
    # 13:00~15:00 비: 13시·14시 칸만 비다. 15시 칸(15~16시)은 맑음이라 15:30 으로 옮긴 일정에 비가 남지 않는다
    assert all((h.pop, h.pty) == ((80, 1) if h.time.hour in (13, 14) else (20, 0)) for h in hourly)


def test_get_weather_샘플은_날짜_이름_파일만_읽는다(mock_mode):
    # 데모일 기본은 맑음(weather/2026-11-28.json). rain-afternoon 은 데모 스위치로만 쓴다
    result = lookup.get_weather(date="2026-11-28")
    assert set(result) == {"date", "hourly"}  # 파일의 note 는 돌려주지 않는다
    assert [h["time"][11:13] for h in result["hourly"]] == [f"{h:02d}" for h in range(9, 24)]
    assert all((h["pop"], h["pty"]) == (20, 0) for h in result["hourly"])
    note = json.loads((lookup.DATA_DIR / "weather" / "2026-11-28.json").read_text(encoding="utf-8"))["note"]
    assert "데모" in note
    assert guardian_context.load_weather_preset("2026-11-28")[0].pop == 20  # note 가 있어도 Guardian 이 읽는다


# ---------- get_travel_time ----------

@pytest.mark.parametrize("straight_m, expected", [
    (0, (0, "walk")),
    (500, (9, "walk")),  # 0.65km ÷ 4.5km/h = 8.67분 → 올림
    (923, (16, "walk")),  # 경로 1.1999km: 걷기 상한 바로 아래
    (924, (13, "subway")),  # 경로 1.2012km: 1.2km 를 넘으면 지하철 (2.88분 + 10분 → 올림)
    (10000, (42, "subway")),  # 13km ÷ 25km/h = 31.2분 + 10분 → 올림
])
def test_이동_시간_추정_규칙(straight_m, expected):
    result = build_travel_times.estimate(straight_m)
    assert (result["minutes"], result["mode"]) == expected


def test_travel_times_json은_places_json_으로_다시_만든_표와_같다():
    places = json.loads((lookup.DATA_DIR / "places.json").read_text(encoding="utf-8"))
    table = json.loads((lookup.DATA_DIR / "travel_times.json").read_text(encoding="utf-8"))
    assert table["pairs"] == build_travel_times.build_pairs(places)  # 다르면 scripts.build_travel_times 를 다시 실행
    assert len(table["pairs"]) == len(places) * (len(places) - 1) // 2 and table["rule"] == build_travel_times.RULE


def test_get_travel_time_표의_값을_양방향_같게_돌려준다(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)  # USE_MOCK 과 무관하다
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("호출하지 않는다"))
    there = lookup.get_travel_time(from_place_id="jagalchi-market", to_place_id="busan-tower")
    assert there == {"from_place_id": "jagalchi-market", "to_place_id": "busan-tower", "minutes": 10, "mode": "walk"}
    back = lookup.get_travel_time("busan-tower", "jagalchi-market")  # Guardian 은 위치 인자로 부른다
    assert (back["from_place_id"], back["minutes"], back["mode"]) == ("busan-tower", 10, "walk")
    far = lookup.get_travel_time(from_place_id="gamcheon-village", to_place_id="haeundae-beach")
    assert far["mode"] == "subway" and isinstance(far["minutes"], int) and far["minutes"] > 30
    same = lookup.get_travel_time(from_place_id="busan-tower", to_place_id="busan-tower")
    assert (same["minutes"], same["mode"]) == (0, "walk")


def test_get_travel_time_표에_없는_ID와_표가_없을_때는_오류_dict(monkeypatch, tmp_path):
    assert error_code(lookup.get_travel_time(from_place_id="busan-tower", to_place_id="no-such-place")) == "place_not_found"
    assert error_code(lookup.get_travel_time(from_place_id="no-such-place", to_place_id="no-such-place")) == "place_not_found"
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert error_code(lookup.get_travel_time(from_place_id="busan-tower", to_place_id="jagalchi-market")) == "data_unavailable"


def test_build_context는_실제_도구로_이동_시간과_행사를_채운다(mock_mode):
    plan = Plan.model_validate_json((lookup.DATA_DIR / "sample_plan.json").read_text(encoding="utf-8"))
    ctx = guardian_context.build_context(plan)
    assert ctx.travel("jagalchi-market", "busan-tower") == 10
    assert all(ctx.travel(a.place_id, b.place_id) is not None for a in plan.stops for b in plan.stops)
    assert ctx.weather is not None and len(ctx.weather) == 24  # weather/2026-11-21.json
    assert all(e.start.date() <= plan.date <= e.end.date() for e in ctx.events)


# ---------- get_events ----------

def _events_dir(tmp_path, events):
    (tmp_path / "events.json").write_text(json.dumps({"source": {}, "events": events}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_get_events_기간에_날짜가_포함된_행사만_돌려준다(monkeypatch, tmp_path):
    def event(name, start, end, place_ids, playtime=None):
        opens, closes = playtime or ("00:00:00", "23:59:59")
        return {"name": name, "start": f"{start}T{opens}+09:00", "end": f"{end}T{closes}+09:00",
                "place_ids": place_ids, "contentid": "1", "addr1": "부산", "lat": 35.1, "lng": 129.1,
                **({"playtime_raw": "18:00~23:00"} if playtime else {})}

    monkeypatch.setattr(lookup, "DATA_DIR", _events_dir(tmp_path, [
        event("상설", "2026-01-01", "2026-12-31", ["gwangalli-beach"]),  # 긴 행사: 개막일만
        event("빛축제", "2026-11-28", "2027-01-10", ["haeundae-beach"], ("18:00:00", "23:00:00")),  # 긴 행사 + 행사 시간
        event("하루", "2026-11-28", "2026-11-28", ["busan-tower"]),
        event("7일", "2026-11-22", "2026-11-28", []),  # 첫날·마지막 날 포함 7일 → 기간 전체
        event("8일", "2026-11-21", "2026-11-28", []),  # 8일 → 개막일만
        event("야간 7일", "2026-12-01", "2026-12-07", [], ("18:00:00", "23:00:00")),  # 짧은 행사 + 행사 시간
    ]))

    def on(date):
        return [(e["name"], e["kind"]) for e in lookup.get_events(date)["events"]]  # Guardian 처럼 위치 인자

    result = lookup.get_events(date="2026-11-28")
    assert result == {"date": "2026-11-28", "events": [
        # 행사 시간을 아는 행사: start·end 는 요청한 날짜의 그 시간대, 원래 기간은 period_start·period_end
        {"name": "빛축제", "start": "2026-11-28T18:00:00+09:00", "end": "2026-11-28T23:00:00+09:00",
         "period_start": "2026-11-28T18:00:00+09:00", "period_end": "2027-01-10T23:00:00+09:00",
         "place_ids": ["haeundae-beach"], "kind": "opening_day"},
        # 행사 시간을 모르는 행사: 그날 00:00~23:59
        {"name": "하루", "start": "2026-11-28T00:00:00+09:00", "end": "2026-11-28T23:59:59+09:00",
         "period_start": "2026-11-28T00:00:00+09:00", "period_end": "2026-11-28T23:59:59+09:00",
         "place_ids": ["busan-tower"], "kind": "short"},
        {"name": "7일", "start": "2026-11-28T00:00:00+09:00", "end": "2026-11-28T23:59:59+09:00",
         "period_start": "2026-11-22T00:00:00+09:00", "period_end": "2026-11-28T23:59:59+09:00",
         "place_ids": [], "kind": "short"},
    ]}
    events = TypeAdapter(list[Event]).validate_python(result["events"])  # Guardian 의 Event 모델로 읽힌다 (period_* 는 무시)
    assert all(e.start.date() == e.end.date() == dt.date(2026, 11, 28) and e.start < e.end for e in events)
    # 기간 중간 날짜를 물으면 그 날짜의 시간대가 나온다. kind 는 원래 기간(7일)으로 정한다
    middle = lookup.get_events(date="2026-12-03")["events"]
    assert [(e["name"], e["kind"], e["start"], e["end"], e["period_start"], e["period_end"]) for e in middle] == [
        ("야간 7일", "short", "2026-12-03T18:00:00+09:00", "2026-12-03T23:00:00+09:00",
         "2026-12-01T18:00:00+09:00", "2026-12-07T23:00:00+09:00")]
    assert on("2026-11-29") == []  # 빛축제 둘째 날은 행사일이 아니다
    assert on("2026-11-22") == [("7일", "short")] and on("2026-11-25") == [("7일", "short")]
    assert on("2026-11-21") == [("8일", "opening_day")]
    assert on("2026-01-01") == [("상설", "opening_day")] and on("2026-06-15") == []
    assert lookup.get_events(date="2027-01-01") == {"date": "2027-01-01", "events": []}


def test_get_events_실제_데이터_데모일에는_빛축제_개막만_나온다():
    events = lookup.get_events(date="2026-11-28")["events"]
    assert [(e["name"], e["kind"], e["start"][:10]) for e in events] == [("해운대 빛축제", "opening_day", "2026-11-28")]
    assert "haeundae-beach" in events[0]["place_ids"]
    assert lookup.get_events(date="2026-11-29")["events"] == []
    all_events = json.loads((lookup.DATA_DIR / "events.json").read_text(encoding="utf-8"))["events"]
    assert len(all_events) == 14 and "kind" not in all_events[0]  # 파일에는 모든 행사가 그대로 있다
    # 빛축제는 행사 시간(playtime)을 확인했다: 개막일 18:00~23:00. 원래 기간(1/10 까지)은 period_* 로 나온다
    assert (events[0]["start"], events[0]["end"]) == ("2026-11-28T18:00:00+09:00", "2026-11-28T23:00:00+09:00")
    assert (events[0]["period_start"], events[0]["period_end"]) == ("2026-11-28T18:00:00+09:00", "2027-01-10T23:00:00+09:00")
    # 파일은 기간 + playtime_raw 그대로다
    festival = next(e for e in all_events if e["name"] == "해운대 빛축제")
    assert (festival["start"], festival["end"]) == (events[0]["period_start"], events[0]["period_end"])
    with_playtime = [e for e in all_events if "playtime_raw" in e]
    assert [(e["name"], e["playtime_raw"]) for e in with_playtime] == [("해운대 빛축제", "18:00~23:00")]
    for e in all_events:  # 나머지 행사는 날짜만 안다
        if "playtime_raw" not in e:
            assert e["start"].endswith("T00:00:00+09:00") and e["end"].endswith("T23:59:59+09:00")


def test_get_events_잘못된_날짜와_파일이_없을_때는_오류_dict(monkeypatch, tmp_path):
    assert error_code(lookup.get_events(date="28/11")) == "invalid_date"
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)
    assert error_code(lookup.get_events(date="2026-11-28")) == "data_unavailable"


def test_events_json은_Event_형식이고_place_ids는_places_json_에_있다():
    data = json.loads((lookup.DATA_DIR / "events.json").read_text(encoding="utf-8"))
    known = {p["place_id"] for p in json.loads((lookup.DATA_DIR / "places.json").read_text(encoding="utf-8"))}
    events = TypeAdapter(list[Event]).validate_python(data["events"])
    assert all(e.start <= e.end and set(e.place_ids) <= known for e in events)
    assert "serviceKey" not in json.dumps(data)


def test_fetch_events_build_events():
    places = [{"place_id": "near", "lat": 35.1587, "lng": 129.1604}, {"place_id": "far", "lat": 35.10, "lng": 129.03}]
    items = [
        {"contentid": 1, "title": " 빛축제 ", "addr1": "부산광역시 해운대구", "eventstartdate": "20261128",
         "eventenddate": "20270117", "mapx": "129.1604", "mapy": "35.1650"},  # near 에서 약 700m
        {"contentid": 2, "title": "좌표 없는 행사", "eventstartdate": "20261101", "eventenddate": "20261102", "mapx": "", "mapy": ""},
        {"contentid": 3, "title": "날짜 이상", "eventstartdate": "미정", "eventenddate": "20261102"},
        {"contentid": 4, "title": "끝이 시작보다 빠름", "eventstartdate": "20261110", "eventenddate": "20261101"},
    ]
    events = fetch_events.build_events(items, places)
    assert [e["name"] for e in events] == ["좌표 없는 행사", "빛축제"]  # 시작일 순, 읽을 수 없는 항목은 뺀다
    assert events[0]["place_ids"] == [] and events[0]["lat"] is None
    assert events[1] == {"name": "빛축제", "start": "2026-11-28T00:00:00+09:00", "end": "2027-01-17T23:59:59+09:00",
                         "place_ids": ["near"], "contentid": "1", "addr1": "부산광역시 해운대구", "lat": 35.165, "lng": 129.1604}
    assert json.loads(fetch_events.dump_events({"api": "x"}, events)) == {"source": {"api": "x"}, "events": events}

    # 행사 시간 원문이 단순한 한 구간이면 첫날 시작 시각·마지막 날 종료 시각으로 쓰고, 원문을 playtime_raw 에 둔다
    timed = fetch_events.build_events(items, places, {"1": "18:00~23:00"})
    assert [e["name"] for e in timed] == ["좌표 없는 행사", "빛축제"]  # 순서는 날짜 기준 그대로
    assert (timed[1]["start"], timed[1]["end"], timed[1]["playtime_raw"]) == (
        "2026-11-28T18:00:00+09:00", "2027-01-17T23:00:00+09:00", "18:00~23:00")
    assert "playtime_raw" not in timed[0]
    # 애매한 원문은 시각을 바꾸지 않고 원문만 남긴다
    for vague in ("일몰 후 ~ 23:00", "평일 18:00~23:00 / 주말 17:00~24:00", "18:00~23:00 (점등식 19:00)"):
        event = fetch_events.build_events(items, places, {"1": vague})[1]
        assert (event["start"], event["end"], event["playtime_raw"]) == (
            "2026-11-28T00:00:00+09:00", "2027-01-17T23:59:59+09:00", vague)
    assert json.loads(fetch_events.dump_events({}, [])) == {"source": {}, "events": []}
    one = {"response": {"body": {"items": {"item": items[0]}}}}
    assert fetch_events.festival_items(one) == [items[0]]
    assert fetch_events.festival_items({"response": {"body": {"items": ""}}}) == []


# ---------- 공통 ----------

def test_예상하지_못한_예외도_오류_dict(monkeypatch):
    monkeypatch.setattr(lookup, "_load_places", lambda: 1 / 0)
    for result in (lookup.search_places(query="x"), lookup.get_hours(place_id="busan-tower"),
                   lookup.get_crowd(place_id="busan-tower", date="2026-11-21")):
        assert error_code(result) == "internal_error"
