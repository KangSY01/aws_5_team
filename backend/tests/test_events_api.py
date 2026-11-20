"""지도용 행사 조회와 GET /events 테스트. 외부 API를 부르지 않는다."""

import json

import pytest

from app.handler import handler
from app.models.api import ErrorResponse
from app.tools import events_map, lookup
from scripts import fetch_events
from scripts import fetch_places as fp
from scripts.local_invoke import make_event

DAY = "2026-11-28"
EXPECTED = {
    "광안리 M(Marvelous) 드론 × 레이저쇼",
    "부산국제매직페스티벌",
    "크리스마스 빌리지 부산 2026",
    "해운대 빛축제",
}
FIELDS = {
    "contentid", "name", "names", "type", "lat", "lng", "main_place_id", "place_ids",
    "start", "end", "period_start", "period_end",
}


def call(date: str | None) -> tuple[int, dict]:
    query = None if date is None else {"date": date}
    result = handler(make_event("GET", "/events", query=query))
    return result["statusCode"], json.loads(result["body"])


def test_11월28일_API는_기간중인_행사4건을_돌려준다():
    status, body = call(DAY)

    assert status == 200 and body["date"] == DAY
    assert {event["name"] for event in body["events"]} == EXPECTED
    assert len(body["events"]) == 4
    assert all(set(event) == FIELDS for event in body["events"])
    assert all(event["type"] in {"festival", "performance", "exhibition", "event"} for event in body["events"])
    assert all(event["names"]["ko"] == event["name"] for event in body["events"])

    light = next(event for event in body["events"] if event["name"] == "해운대 빛축제")
    assert (light["contentid"], light["start"], light["end"]) == (
        "2048902", "2026-11-28T18:00:00+09:00", "2026-11-28T23:00:00+09:00"
    )
    assert light["period_start"] == "2026-11-28T18:00:00+09:00"
    assert light["period_end"] == "2027-01-10T23:00:00+09:00"


def test_events_json은_14건이고_외국어_이름과_type을_수집값만_가진다():
    data = json.loads((lookup.DATA_DIR / "events.json").read_text(encoding="utf-8"))
    events = data["events"]
    assert len(events) == 14
    assert {lang: sum(lang in event["names"] for event in events) for lang in fp.NAME_LANGS} == {
        "en": 4, "ja": 2, "zh-Hans": 1, "zh-Hant": 1,
    }
    assert all(event["names"]["ko"] == event["name"] for event in events)
    assert all(set(event["names"]) <= {"ko", *fp.NAME_LANGS} for event in events)
    assert {kind: sum(event["type"] == kind for event in events) for kind in events_map.EventType.__args__} == {
        "festival": 6, "performance": 1, "exhibition": 2, "event": 5,
    }
    assert not (lookup.DATA_DIR / "events_layer.json").exists()


def test_지도_API와_Guardian_행사_규칙은_분리되어_있다():
    map_names = {event.name for event in events_map.events_on_date(DAY).events}
    guardian = lookup.get_events(DAY)
    assert map_names == EXPECTED
    assert [(event["name"], event["kind"]) for event in guardian["events"]] == [("해운대 빛축제", "opening_day")]


def test_date_누락과_형식_오류는_422_계약_오류다():
    for date in (None, "", "28/11/2026", "2026-02-30"):
        status, body = call(date)
        assert status == 422
        assert ErrorResponse.model_validate(body).error.code == "validation_error"


def test_지도_함수는_긴_행사도_기간_중이면_매일_포함한다(monkeypatch, tmp_path):
    data = {"events": [
        {
            "contentid": "long", "name": "상설", "names": {"ko": "상설", "en": "Permanent"},
            "type": "event", "lat": None, "lng": None, "main_place_id": None, "place_ids": [],
            "start": "2026-01-01T00:00:00+09:00", "end": "2026-12-31T23:59:59+09:00",
        },
        {
            "contentid": "night", "name": "야간", "names": {"ko": "야간", "ja": "夜間"},
            "type": "festival", "lat": 35.1, "lng": 129.1, "main_place_id": "haeundae-beach",
            "place_ids": ["haeundae-beach"], "start": "2026-11-27T18:00:00+09:00",
            "end": "2026-11-29T23:00:00+09:00",
        },
    ]}
    (tmp_path / "events.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(lookup, "DATA_DIR", tmp_path)

    result = events_map.events_on_date(DAY).model_dump(mode="json")
    assert [event["contentid"] for event in result["events"]] == ["long", "night"]
    assert result["events"][0]["start"] == "2026-11-28T00:00:00+09:00"
    assert result["events"][0]["end"] == "2026-11-28T23:59:59+09:00"
    assert result["events"][1]["start"] == "2026-11-28T18:00:00+09:00"
    assert result["events"][1]["end"] == "2026-11-28T23:00:00+09:00"


@pytest.mark.parametrize(("raw", "expected"), [
    ({"lclsSystm2": "EV01", "lclsSystm3": "EV010200"}, "festival"),
    ({"lclsSystm2": "EV02", "lclsSystm3": "EV020900"}, "performance"),
    ({"lclsSystm2": "EV03", "lclsSystm3": "EV030200"}, "exhibition"),
    ({"lclsSystm2": "EV03", "lclsSystm3": "EV030400"}, "event"),
    ({"cat2": "A0207", "cat3": "A02070200"}, "festival"),
    ({"cat2": "A0208", "cat3": "A02080500"}, "exhibition"),
    ({"cat2": "A0208", "cat3": "A02080300"}, "performance"),
    ({}, "event"),
])
def test_행사_type은_TourAPI_원본_분류로_정한다(raw, expected):
    assert fetch_events.classify_event(raw) == expected


def _foreign(contentid: str, title: str, lat: float = 35.16) -> dict:
    return {"contentid": contentid, "title": title, "addr1": "Busan", "lat": lat, "lng": 129.16}


def test_외국어_이름은_한국어_제목과_거리로_일치한_값만_쓴다():
    korean = [{
        "contentid": "1", "title": "해운대 빛축제", "addr1": "부산", "mapy": "35.16", "mapx": "129.16"
    }]
    foreign = {
        "en": [
            _foreign("wrong", "Other Festival (다른 축제)", 35.1601),
            _foreign("right", "Haeundae Light Festival (해운대 빛축제)", 35.1602),
        ],
        "ja": [_foreign("far", "海雲台光祭り（해운대 빛축제）", 35.166)],  # 약 670m, exact 보충 일치
        "zh-Hans": [_foreign("no-ko", "海云台灯光节", 35.1601)],  # 한국어 원문이 없어 사용하지 않는다
    }

    assert fetch_events.match_event_names(korean, foreign) == {
        "1": {"en": "Haeundae Light Festival", "ja": "海雲台光祭り"}
    }


def test_외국어_searchFestival은_언어별_한번만_호출한다(monkeypatch):
    calls = []

    def fake_call(service, operation, params, raw_path):
        calls.append((service, operation, params, raw_path.name))
        return []

    monkeypatch.setattr(fp, "_call_and_save", fake_call)
    params = {"eventStartDate": "20261101", "eventEndDate": "20261130", "lDongRegnCd": "26"}
    result = fetch_events.fetch_foreign_candidates(params)

    assert set(result) == set(fp.NAME_LANGS)
    assert len(calls) == len(fp.NAME_LANGS) == 4
    assert [service for service, *_ in calls] == [fp.SERVICES[lang] for lang in fp.NAME_LANGS]
    assert all(operation == "searchFestival2" and got == params for _, operation, got, _ in calls)
