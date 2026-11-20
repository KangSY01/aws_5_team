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

def test_get_crowd_요일_규칙_장소와_데이터_없는_장소는_ratio_null():
    for place_id in [*WEEKDAY_RULE_PLACES, "haeundae-beach"]:  # 집중률 파일이 아직 없다
        assert lookup.get_crowd(place_id=place_id, date="2026-11-21") == {
            "place_id": place_id, "date": "2026-11-21", "ratio": None, "source": "weekday_rule"}


def test_get_crowd_집중률이_있으면_concentration_요일_규칙_장소는_그대로(monkeypatch):
    monkeypatch.setattr(lookup, "_concentration", lambda place_id, day: 87.5)
    result = lookup.get_crowd(place_id="haeundae-beach", date="2026-11-21")
    assert (result["ratio"], result["source"]) == (87.5, "concentration")
    result = lookup.get_crowd(place_id="gamcheon-village", date="2026-11-21")
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

def test_get_hours_모르는_값을_돌려준다():
    result = lookup.get_hours(place_id="busan-tower")
    assert result == {"place_id": "busan-tower", "opens": None, "closes": None, "closed_weekdays": [], "closed_dates": []}
    OpeningHours.model_validate({k: v for k, v in result.items() if k != "place_id"})
    assert error_code(lookup.get_hours(place_id="no-such-place")) == "place_not_found"


# ---------- get_weather 샘플 폴더 (app/data/weather/) ----------

def test_weather_폴더_파일은_이름_규칙과_get_weather_형식을_따른다():
    files = sorted((lookup.DATA_DIR / "weather").glob("*"))
    assert {f.name for f in files} >= {"rain-afternoon.json", "2026-11-21.json"}
    for f in files:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*\.json", f.name), f.name  # 소문자·숫자·하이픈만
        data = json.loads(f.read_text(encoding="utf-8"))
        assert set(data) == {"date", "hourly"}
        hourly = TypeAdapter(list[HourlyWeather]).validate_python(data["hourly"])
        assert all(h.time.date().isoformat() == data["date"] and h.time.utcoffset() == dt.timedelta(hours=9)
                   for h in hourly)


def test_rain_afternoon_프리셋은_13_15시만_비이고_Guardian이_읽는다():
    hourly = guardian_context.load_weather_preset("rain-afternoon")
    assert [h.time.hour for h in hourly] == list(range(9, 22)) and hourly[0].time.date() == dt.date(2026, 11, 28)
    assert all((h.pop, h.pty) == ((80, 1) if 13 <= h.time.hour <= 15 else (20, 0)) for h in hourly)


def test_get_weather_샘플은_날짜_이름_파일만_읽는다(mock_mode):
    # rain-afternoon 은 데모 스위치용이라, 프리셋 없이는 2026-11-28 예보가 없다
    assert lookup.get_weather(date="2026-11-28") == {"date": "2026-11-28", "hourly": []}


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
    def event(name, start, end, place_ids):
        return {"name": name, "start": f"{start}T00:00:00+09:00", "end": f"{end}T23:59:59+09:00",
                "place_ids": place_ids, "contentid": "1", "addr1": "부산", "lat": 35.1, "lng": 129.1}

    monkeypatch.setattr(lookup, "DATA_DIR", _events_dir(tmp_path, [
        event("가", "2026-11-01", "2026-11-27", []),
        event("나", "2026-11-28", "2026-11-28", ["haeundae-beach"]),
        event("다", "2026-11-20", "2026-12-31", ["busan-tower"]),
        event("라", "2026-11-29", "2026-11-30", []),
    ]))
    result = lookup.get_events(date="2026-11-28")
    assert result == {"date": "2026-11-28", "events": [
        {"name": "나", "start": "2026-11-28T00:00:00+09:00", "end": "2026-11-28T23:59:59+09:00", "place_ids": ["haeundae-beach"]},
        {"name": "다", "start": "2026-11-20T00:00:00+09:00", "end": "2026-12-31T23:59:59+09:00", "place_ids": ["busan-tower"]},
    ]}
    TypeAdapter(list[Event]).validate_python(result["events"])
    assert [e["name"] for e in lookup.get_events("2026-11-27")["events"]] == ["가", "다"]  # 경계일 포함, 위치 인자
    assert lookup.get_events(date="2027-01-01") == {"date": "2027-01-01", "events": []}


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
