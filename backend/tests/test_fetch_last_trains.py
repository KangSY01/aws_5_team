"""scripts/fetch_last_trains.py 테스트. 실제 API를 부르지 않는다."""

import json
import urllib.error

import pytest

from scripts import fetch_last_trains as trains

CODES = {"Jung-dong": "202", "Haeundae": "203", "Dongbaek": "204", "Seomyeon": "219"}


def response(rows, code="00", message="NORMAL SERVICE", total=None, page=1):
    """--probe 로 확인한 구조: body.items.item 과 numOfRows·pageNo·totalCount."""
    count = len(rows) if isinstance(rows, list) else 1
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": message},
            "body": {"items": {"item": rows}, "numOfRows": 100, "pageNo": page,
                     "totalCount": count if total is None else total},
        }
    }


def row(arrtime="23:29:10", scode="203", day="2", updown="1", endcode="239", line="2"):
    return {
        "scode": scode, "sname": "해운대", "line": line, "engname": "Haeundae", "trainno": "2300",
        "arrtime": arrtime, "dayType": day, "updown": updown, "endcode": endcode,
    }


def pick(rows, scode="203", day="2", updown="1", dest="219"):
    return trains.last_train_time(rows, scode, day, updown, dest)


def test_요청_변수는_역과_시간_구간과_페이지만_바뀐다():
    assert trains.API_URL == "https://apis.data.go.kr/B551542/trainTime/getTrainTime"
    assert trains.WINDOWS == (("2200", "2359"), ("0000", "0130"))
    assert trains.request_params("203", "2200", "2359") == {
        "pageNo": "1", "numOfRows": "100", "day": "1", "updown": "0", "stime": "2200", "etime": "2359",
        "enum": "100", "act": "json", "scode": "203",
    }
    assert trains.request_params("219", "0000", "0130", 2)["pageNo"] == "2"


def test_대상_역코드는_CSV의_2호선_역번호다():
    assert trains.load_station_codes() == CODES  # 목적지(Seomyeon, Haeundae) 코드도 여기서 찾는다
    assert [(route["station"], route["toward"], route["updown"]) for route in trains.ROUTES] == [
        ("Haeundae", "Seomyeon", "1"),
        ("Dongbaek", "Seomyeon", "1"),
        ("Jung-dong", "Seomyeon", "1"),
        ("Seomyeon", "Haeundae", "0"),
    ]


def test_item이_dict_하나거나_없어도_행_목록으로_읽는다():
    one = row()
    assert trains.timetable_rows(response(one)) == [one]
    assert trains.timetable_rows(response([one, one])) == [one, one]
    assert trains.timetable_rows(response([])) == []
    assert trains.timetable_rows({"response": {"header": {}, "body": {"items": "", "totalCount": 0}}}) == []
    assert trains.timetable_rows({"body": {"items": {"item": one}}}) == [one]  # body 가 최상위에 있는 응답
    assert trains.total_count(response([one], total=137)) == 137 and trains.total_count({}) == 0


def test_요일과_방향과_역과_노선이_맞는_행만_본다():
    rows = [
        row("22:59:00"),
        row("23:10:59"),  # 초는 버린다
        row("23:50:00", day="1"),
        row("23:51:00", day="3"),
        row("23:52:00", updown="0", endcode="201"),
        row("23:53:00", scode="204"),
        row("23:54:00", line="1"),
    ]
    assert pick(rows) == "23:10"
    assert pick(rows, day="1") == "23:50" and pick(rows, day="3") == "23:51"
    assert pick(rows, scode="204") == "23:53"


def test_목적지_전에_끝나는_열차는_막차가_아니다():
    # 해운대 하행 23:46 은 209 종착이라 서면(219)까지 가지 않는다. 239 종착인 23:29 가 막차다
    rows = [row("23:29:10", endcode="239"), row("23:46:40", endcode="209"), row("23:10:00", endcode="243")]
    assert pick(rows) == "23:29"
    assert pick([row("23:40:00", endcode="219")]) == "23:40"  # 목적지가 종착이면 간다
    assert pick([row("23:40:00", endcode="")]) is None  # 종착역을 모르면 세지 않는다
    # 상행(0)은 역번호가 작아진다. 서면 → 해운대(203): 201·203 종착은 가고 208 종착은 못 간다
    up = [row("23:20:00", scode="219", updown="0", endcode="201"),
          row("23:35:00", scode="219", updown="0", endcode="203"),
          row("23:50:00", scode="219", updown="0", endcode="208")]
    assert pick(up, scode="219", updown="0", dest="203") == "23:35"


def test_자정_뒤_행은_24시대로_본다():
    rows = [row("23:29:10"), row("00:12:30"), row("00:40:00", endcode="209")]
    assert pick(rows) == "24:12"


def test_조건에_맞는_행이_없으면_None이고_시각이_이상하면_실패한다():
    assert pick([row(day="1")]) is None and pick([]) is None
    with pytest.raises(trains.FetchError, match="범위"):
        pick([row("23:61:00")])
    with pytest.raises(trains.FetchError, match="arrtime"):
        pick([row("2329")])


def test_역마다_구간_두개를_호출하고_totalCount가_넘치면_다음_페이지를_받는다(monkeypatch):
    calls = []

    def fake_call(params, raw_path):
        calls.append((params["stime"], params["pageNo"], raw_path.name))
        if params["stime"] == "0000":
            return response([])  # 자정 뒤 구간은 비어도 통과한다
        if params["pageNo"] == "1":
            return response([row("22:10:00")] * 100, total=101)
        return response(row("23:29:10"), total=101, page=2)  # 마지막 장은 item 이 dict 하나

    monkeypatch.setattr(trains, "call_and_save", fake_call)
    rows = trains.fetch_station_rows("203")

    assert calls == [("2200", "1", "203_2200_2359_p1.json"), ("2200", "2", "203_2200_2359_p2.json"),
                     ("0000", "1", "203_0000_0130_p1.json")]
    assert len(rows) == 101 and pick(rows) == "23:29"


def test_collect은_역_4개_구간_2개만_호출하고_없는_요일은_빼고_경고한다(monkeypatch, capsys):
    calls = []

    def fake_call(params, raw_path):
        calls.append((params["scode"], params["stime"], params["etime"], params["pageNo"]))
        assert params == trains.request_params(params["scode"], params["stime"], params["etime"])
        scode = params["scode"]
        if params["stime"] == "0000":
            # 서면 상행만 자정 뒤 열차가 있다
            return response([row("00:05:00", scode="219", day=day, updown="0", endcode="201") for day in "123"]
                            if scode == "219" else [])
        rows = []
        for day in "123":
            if (scode, day) == ("204", "3"):
                continue  # 동백 일요일은 조건에 맞는 행이 없다
            rows += [
                row(f"23:2{day}:10", scode=scode, day=day, updown="1", endcode="239"),
                row("23:46:40", scode=scode, day=day, updown="1", endcode="209"),  # 서면 전 종착
                row("23:30:00", scode=scode, day=day, updown="0", endcode="201"),
            ]
        return response(rows)

    monkeypatch.setattr(trains, "call_and_save", fake_call)
    monkeypatch.setattr(trains.config, "DEMO_NOW", "2026-11-20T12:00:00+09:00")
    data = trains.collect(trains.load_station_codes())

    assert calls == [(scode, stime, etime, "1") for scode in ("203", "204", "202", "219")
                     for stime, etime in trains.WINDOWS]
    assert data["stations"]["Haeundae"] == {
        "scode": "203", "toward": "Seomyeon", "updown": 1,
        "last_train": {"1": "23:21", "2": "23:22", "3": "23:23"},
    }
    assert data["stations"]["Dongbaek"]["last_train"] == {"1": "23:21", "2": "23:22"}  # 지어내지 않는다
    assert data["stations"]["Seomyeon"] == {
        "scode": "219", "toward": "Haeundae", "updown": 0,
        "last_train": {"1": "24:05", "2": "24:05", "3": "24:05"},
    }
    assert set(data) == {"source", "stations"} and data["source"]["api"] == trains.API_URL
    assert data["source"]["fetched_at"] == "2026-11-20"
    err = capsys.readouterr().err
    assert err.count("[경고]") == 1 and "Dongbaek → Seomyeon 일요일·공휴일" in err


def test_막차를_하나도_못_찾으면_파일을_만들지_않고_실패한다(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(trains, "call_and_save", lambda params, raw_path: response([]))
    monkeypatch.setattr(trains, "OUT_PATH", tmp_path / "last_trains.json")
    assert trains.main(["--offline"]) == 1
    assert "하나도 찾지 못했습니다" in capsys.readouterr().err and not (tmp_path / "last_trains.json").exists()


def test_main은_형식을_유지해_저장하고_총_호출_수를_출력한다(monkeypatch, tmp_path, capsys):
    def fake_request(params):
        trains.API_CALLS += 1
        return response([row(scode=params["scode"], day=day, updown=updown, endcode=end)
                         for day in "123" for updown, end in (("1", "243"), ("0", "201"))])

    monkeypatch.setattr(trains, "request_json", fake_request)
    monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET")
    monkeypatch.setattr(trains, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(trains, "OUT_PATH", tmp_path / "last_trains.json")
    monkeypatch.setattr(trains, "API_CALLS", 0)

    assert trains.main([]) == 0
    out = capsys.readouterr().out
    assert "API 호출 8회" in out and "값 12/12개" in out
    saved = json.loads((tmp_path / "last_trains.json").read_text(encoding="utf-8"))
    # return_options._last_train_at 이 읽는 형식: stations[역]["toward"], ["last_train"][요일 코드]
    assert saved["stations"]["Haeundae"]["toward"] == "Seomyeon"
    assert saved["stations"]["Haeundae"]["last_train"] == {"1": "23:29", "2": "23:29", "3": "23:29"}
    assert sorted(path.name for path in (tmp_path / "raw").iterdir()) == sorted(
        f"{scode}_{stime}_{etime}_p1.json" for scode in CODES.values() for stime, etime in trains.WINDOWS)
    assert "SECRET" not in "".join(path.read_text(encoding="utf-8") for path in (tmp_path / "raw").iterdir())

    # --offline 은 저장된 raw 로 같은 결과를 만들고 API 를 부르지 않는다
    monkeypatch.setattr(trains, "request_json", lambda params: pytest.fail("offline에서 API를 부르면 안 됩니다."))
    monkeypatch.setattr(trains, "API_CALLS", 0)
    assert trains.main(["--offline"]) == 0
    assert "API 호출 0회" in capsys.readouterr().out
    assert json.loads((tmp_path / "last_trains.json").read_text(encoding="utf-8"))["stations"] == saved["stations"]


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
            trains.request_json(trains.request_params("203", "2200", "2359"))
        assert len(calls) == 1 and "SECRET" not in str(error.value)
        assert calls[0][0].startswith(trains.API_URL + "?serviceKey=SECRET&pageNo=1&numOfRows=100&")


def test_resultCode를_구분한다():
    with pytest.raises(trains.ApprovalError):
        trains._check_response(response([], "12", "NO OPENAPI SERVICE ERROR."))
    with pytest.raises(trains.FetchError, match="resultCode=10.*잘못된 요청 파라미터") as bad_params:
        trains._check_response(response([], "10", "INVALID_REQUEST_PARAMETER_ERROR"))
    assert not isinstance(bad_params.value, trains.ApprovalError)
    with pytest.raises(trains.ApprovalError, match="resultCode=20.*PERMISSION_DENIED.*승인"):
        trains._check_response(response([], "20", "SERVICE ACCESS DENIED ERROR"))
    with pytest.raises(trains.FetchError, match="resultCode=22.*호출 한도") as limit:
        trains._check_response(response([], "22", "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS ERROR"))
    assert not isinstance(limit.value, trains.ApprovalError)
    # header 가 최상위에 있는 응답도 읽는다
    with pytest.raises(trains.ApprovalError):
        trains._check_response({"header": {"resultCode": "20", "resultMsg": "x"}})
    trains._check_response(response([], "03", "NODATA_ERROR"))  # 빈 구간은 오류가 아니다


class FakeResponse:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_probe는_1회만_호출하고_구조만_출력하며_저장하지_않는다(monkeypatch, tmp_path, capsys):
    calls = []
    rows = [row(f"22:1{i}:00", day="1") for i in range(8)]

    def fake_urlopen(url, timeout):
        calls.append(url)
        return FakeResponse(json.dumps(response(rows)).encode("utf-8"))

    monkeypatch.setattr(trains.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET+KEY/==")
    monkeypatch.setattr(trains, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(trains, "OUT_PATH", tmp_path / "last_trains.json")
    monkeypatch.setattr(trains, "API_CALLS", 0)

    assert trains.main(["--probe"]) == 0
    out, err = capsys.readouterr()
    assert len(calls) == 1 and "scode=203" in calls[0] and "stime=2200" in calls[0] and "etime=2359" in calls[0]
    assert "SECRET" not in out + err and "serviceKey" not in out.replace("serviceKey 제외", "")
    assert "resultCode: 00" in out and "resultMsg: NORMAL SERVICE" in out
    assert "item: list (len 8)" in out and "arrtime: str" in out and "totalCount: int" in out
    assert "시간표 행으로 보이는 항목: 8개" in out
    assert out.count("[처음]") == 3 and out.count("[마지막]") == 3
    assert '"arrtime": "22:10:00"' in out and '"arrtime": "22:17:00"' in out and '"arrtime": "22:13:00"' not in out
    assert list(tmp_path.iterdir()) == []


def test_probe는_오류_코드와_JSON이_아닌_응답도_키_없이_알린다(monkeypatch, capsys):
    monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET+KEY/==")
    body = json.dumps(response([], "20", "SERVICE ACCESS DENIED ERROR")).encode("utf-8")
    monkeypatch.setattr(trains.urllib.request, "urlopen", lambda url, timeout: FakeResponse(body))
    assert trains.main(["--probe"]) == 3
    out = capsys.readouterr().out
    assert "resultCode: 20" in out and "PERMISSION_DENIED" in out

    xml = b"<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR SECRET+KEY/==</returnAuthMsg>"
    monkeypatch.setattr(trains.urllib.request, "urlopen", lambda url, timeout: FakeResponse(xml))
    assert trains.main(["--probe"]) == 1
    out = capsys.readouterr().out
    assert "JSON이 아닌 응답" in out and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in out and "SECRET" not in out

    def offline(url, timeout):
        raise urllib.error.URLError(f"cannot open {url}")

    monkeypatch.setattr(trains.urllib.request, "urlopen", offline)
    assert trains.main(["--probe"]) == 1
    out, err = capsys.readouterr()
    assert "호출 실패: URLError" in out and "SECRET" not in out + err


def test_raw_재사용과_저장에는_키가_없다(monkeypatch, tmp_path):
    params = trains.request_params("203", "2200", "2359")
    raw_path = tmp_path / "raw" / "203_2200_2359_p1.json"
    monkeypatch.setattr(trains.config, "DATA_GO_KR_KEY", "SECRET")
    monkeypatch.setattr(trains, "OFFLINE", False)
    monkeypatch.setattr(trains, "REUSE_RAW", False)
    monkeypatch.setattr(trains, "request_json", lambda got: response([row(day="1")]))

    first = trains.call_and_save(params, raw_path)
    assert pick(trains.timetable_rows(first), day="1") == "23:29"
    assert "SECRET" not in raw_path.read_text(encoding="utf-8")

    monkeypatch.setattr(trains, "OFFLINE", True)
    monkeypatch.setattr(trains, "request_json", lambda got: pytest.fail("offline에서 API를 부르면 안 됩니다."))
    assert trains.call_and_save(params, raw_path) == first
    saved = json.loads(raw_path.read_text(encoding="utf-8"))
    assert saved["params"] == params
    # 다른 구간의 요청은 같은 raw 를 재사용하지 않는다
    with pytest.raises(trains.FetchError, match="--offline"):
        trains.call_and_save(trains.request_params("203", "0000", "0130"), raw_path)
