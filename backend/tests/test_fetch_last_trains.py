"""scripts/fetch_last_trains.py 테스트. 실제 API를 부르지 않는다."""

import json
import urllib.error

import pytest

from scripts import fetch_last_trains as trains


def response(rows, code="00", message="NORMAL SERVICE"):
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": message},
            "body": {"items": {"item": rows}},
        }
    }


def row(scode="203", day="2", updown="1", hour="23", minute="40"):
    return {
        "sname": "해운대", "engname": "Haeundae", "trainno": "1", "hour": hour, "time": minute,
        "day": day, "updown": updown, "endcode": "243", "scode": scode, "line": "2",
    }


def test_대상_역코드는_CSV의_2호선_역번호다():
    assert trains.load_station_codes() == {
        "Jung-dong": "202", "Haeundae": "203", "Dongbaek": "204", "Seomyeon": "219"
    }
    assert [(route["station"], route["toward"], route["updown"]) for route in trains.ROUTES] == [
        ("Haeundae", "Seomyeon", "1"),
        ("Dongbaek", "Seomyeon", "1"),
        ("Jung-dong", "Seomyeon", "1"),
        ("Seomyeon", "Haeundae", "0"),
    ]


def test_요청한_역_요일_방향의_가장_늦은_시각만_고른다():
    params = {"scode": "203", "day": "2", "updown": "1", "act": "json"}
    data = response([
        row(hour="22", minute="59"),
        row(hour="24", minute="03"),
        row(hour="00", minute="04"),  # 자정 뒤 00시는 같은 운행일의 24시로 정규화한다
        row(day="1", hour="25", minute="00"),
        row(updown="0", hour="25", minute="10"),
        row(scode="204", hour="25", minute="20"),
    ])
    assert trains.last_train_time(data, params) == "24:04"
    assert trains.timetable_rows(data)[0]["scode"] == "203"


def test_빈_행과_잘못된_시각은_실패한다():
    params = {"scode": "203", "day": "2", "updown": "1", "act": "json"}
    with pytest.raises(trains.FetchError, match="시간표 행이 없습니다"):
        trains.last_train_time(response([row(day="1")]), params)
    with pytest.raises(trains.FetchError, match="범위"):
        trains.last_train_time(response([row(minute="61")]), params)


def test_collect은_4역_3요일을_각각_한번_조회하고_막차만_남긴다(monkeypatch):
    calls = []

    def fake_call(params, raw_path):
        calls.append((dict(params), raw_path.name))
        return response([row(
            scode=params["scode"], day=params["day"], updown=params["updown"],
            hour="23", minute=str(40 + int(params["day"])),
        )])

    monkeypatch.setattr(trains, "call_and_save", fake_call)
    monkeypatch.setattr(trains.config, "DEMO_NOW", "2026-11-20T12:00:00+09:00")
    data = trains.collect(trains.load_station_codes())

    assert len(calls) == 12
    assert all(set(params) == {"scode", "day", "updown", "act"} and params["act"] == "json" for params, _ in calls)
    assert data["stations"]["Haeundae"] == {
        "scode": "203", "toward": "Seomyeon", "updown": 1,
        "last_train": {"1": "23:41", "2": "23:42", "3": "23:43"},
    }
    assert data["stations"]["Seomyeon"]["toward"] == "Haeundae"
    assert "items" not in data and data["source"]["data_go_kr_id"] == "15000522"


def _http_error(code: int):
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, None)


def test_401_403은_재시도하지_않고_승인_오류로_중단한다(monkeypatch):
    for code in (401, 403):
        calls = []

        def denied(url, timeout):
            calls.append((url, timeout))
            raise _http_error(code)

        monkeypatch.setattr(trains.urllib.request, "urlopen", denied)
        monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET")
        monkeypatch.setattr(trains, "API_CALLS", 0)
        with pytest.raises(trains.ApprovalError, match=str(code)) as error:
            trains.request_json({"scode": "203", "day": "1", "updown": "1", "act": "json"})
        assert len(calls) == 1 and "SECRET" not in str(error.value)


def test_미승인_resultCode_12도_승인_오류다():
    with pytest.raises(trains.ApprovalError):
        trains.last_train_time(response([], "12", "NO OPENAPI SERVICE ERROR."), {
            "scode": "203", "day": "1", "updown": "1", "act": "json"
        })


def test_raw_재사용과_저장에는_키가_없다(monkeypatch, tmp_path):
    params = {"scode": "203", "day": "1", "updown": "1", "act": "json"}
    raw_path = tmp_path / "raw" / "203.json"
    monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET")
    monkeypatch.setattr(trains, "OFFLINE", False)
    monkeypatch.setattr(trains, "REUSE_RAW", False)
    monkeypatch.setattr(trains, "request_json", lambda got: response([row(day="1")]))

    first = trains.call_and_save(params, raw_path)
    assert trains.last_train_time(first, params) == "23:40"
    assert "SECRET" not in raw_path.read_text(encoding="utf-8")

    monkeypatch.setattr(trains, "OFFLINE", True)
    monkeypatch.setattr(trains, "request_json", lambda got: pytest.fail("offline에서 API를 부르면 안 됩니다."))
    assert trains.call_and_save(params, raw_path) == first
    saved = json.loads(raw_path.read_text(encoding="utf-8"))
    assert saved["params"] == params
