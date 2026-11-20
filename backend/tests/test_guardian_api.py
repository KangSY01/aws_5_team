"""build_context(스펙 작업 8)와 /plan/check·/plan/{plan_id}/delay 연결(스펙 작업 9) 테스트.

조회 도구(app/tools/lookup.py)는 같은 이름의 함수를 가진 가짜 객체로 바꿔 넣는다. 수치는 테스트용 값이다.
"""

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from app import config
from app.guardian import context as guardian_context
from app.guardian.context import (
    KST,
    WeatherPresetNotFound,
    build_context,
    load_weather_preset,
    resolve_now,
    with_repair_travel,
)
from app.guardian.service import run_check, run_delay
from app.handler import SAMPLE_PLAN, handler
from app.models.api import CheckResponse, DelayResponse, DemoOverride, ErrorResponse
from guardian_fixtures import at
from scripts.local_invoke import make_event

PLAN = SAMPLE_PLAN  # s1 감천 10:00-11:30 · s2 자갈치(고정) · s3 부산타워 13:30-14:30 · s4 해운대 15:30-17:00
DATE = PLAN.date.isoformat()
RAIN_15_18 = {"date": DATE, "hourly": [
    {"time": at(h).isoformat(), "pop": 80 if 15 <= h < 18 else 20, "pty": 1 if 15 <= h < 18 else 0}
    for h in range(8, 21)
]}
TRAVEL = {
    ("gamcheon-village", "jagalchi-market"): 15,
    ("jagalchi-market", "busan-tower"): 10,
    ("busan-tower", "haeundae-beach"): 40,
    ("busan-tower", "busan-museum-of-art"): 45,
}


def fake_lookups(weather=None, crowd=None, hours=None, events=None, travel=TRAVEL, calls=None):
    """design.md 「조회 도구 반환 형식」과 같은 dict 를 돌려주는 가짜 도구 묶음."""
    log = calls if calls is not None else []

    def get_weather(date):
        log.append(("get_weather", date))
        return weather or {"date": date, "hourly": []}

    def get_crowd(place_id, date):
        ratio = (crowd or {}).get(place_id)
        return {"place_id": place_id, "date": date, "ratio": ratio,
                "source": "concentration" if ratio is not None else "weekday_rule"}

    def get_hours(place_id):
        if place_id not in (hours or {}):
            return {"error": {"code": "not_found", "message": "영업 정보 없음"}}
        return {"place_id": place_id, **hours[place_id]}

    def get_travel_time(a, b):
        log.append(("get_travel_time", a, b))
        minutes = travel.get((a, b), travel.get((b, a)))
        if minutes is None:
            return {"error": {"code": "no_route", "message": "경로 없음"}}
        return {"from_place_id": a, "to_place_id": b, "minutes": minutes, "mode": "subway"}

    def get_events(date):
        return {"date": date, "events": events or []}

    return SimpleNamespace(get_weather=get_weather, get_crowd=get_crowd, get_hours=get_hours,
                           get_travel_time=get_travel_time, get_events=get_events)


# ---------- 작업 8: build_context ----------

def test_build_context_maps_tool_results():
    lookups = fake_lookups(
        weather=RAIN_15_18,
        crowd={"haeundae-beach": 70},
        hours={"busan-tower": {"opens": "10:00", "closes": "22:00", "closed_weekdays": [], "closed_dates": []}},
        events=[{"name": "테스트 행사", "start": at(18).isoformat(), "end": at(22).isoformat(),
                 "place_ids": ["haeundae-beach"]}],
    )
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)

    assert ctx.now == at(9)
    assert len(ctx.weather) == 13 and ctx.weather[8].pty == 1  # 16시
    assert ctx.crowd == {"haeundae-beach": 70.0}  # ratio null(감천 등)은 넣지 않는다
    assert ctx.hours["busan-tower"].opens == dt.time(10)
    assert [e.name for e in ctx.events] == ["테스트 행사"]
    assert ctx.travel("busan-tower", "haeundae-beach") == 40
    assert "busan-museum-of-art" not in {p for pair in ctx.travel_min for p in pair}  # 교체 후보는 아직
    assert set(ctx.places) >= {"haeundae-beach", "busan-museum-of-art"}


def test_build_context_skips_missing_or_failing_tools():
    # 도구가 없거나(get_hours 등 미구현), 예외를 던지거나, error 를 돌려줘도 점검은 계속된다 (요구사항 6.4)
    def boom(*args):
        raise NotImplementedError("TODO(도구 담당)")

    lookups = SimpleNamespace(get_weather=boom, get_crowd=lambda *a: {"error": {"code": "x", "message": "y"}})
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)
    assert (ctx.weather, ctx.crowd, ctx.hours, ctx.travel_min, ctx.events) == (None, {}, {}, {}, [])
    # 이 context 로도 check_plan 이 돈다: 요일 규칙(감천·부산타워, 토요일)만 남는다
    response = run_check(PLAN, DemoOverride(now=at(9)), lookups=lookups)
    assert [i.issue_id for i in response.issues] == ["s1-crowded", "s3-crowded"]


@pytest.fixture
def no_lookup_data(monkeypatch):
    """handler 가 쓰는 기본 조회 도구를 '데이터 없음'으로 고정한다 (실행 환경·도구 구현 상태와 무관하게)."""
    monkeypatch.setattr(guardian_context, "_default_lookups", lambda: fake_lookups(travel={}))


def test_build_context_with_real_lookup_module_in_mock_mode(monkeypatch):
    # 실제 app/tools/lookup.py (#25) + USE_MOCK=1 샘플: 날씨는 sample_weather.json, 감천은 요일 규칙(ratio null)
    monkeypatch.setattr(config, "USE_MOCK", True)
    ctx = build_context(PLAN, demo_now=at(9))
    assert ctx.weather is not None and any(w.has_precipitation for w in ctx.weather)
    assert "gamcheon-village" not in ctx.crowd


def test_with_repair_travel_adds_candidates_for_issue_stops_only():
    calls = []
    lookups = fake_lookups(calls=calls)
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)
    calls.clear()
    ctx = with_repair_travel(ctx, PLAN, ["s4", "s2"], lookups=lookups)  # s2 는 고정이라 무시

    assert ctx.travel("busan-tower", "busan-museum-of-art") == 45
    asked = {c[1:] for c in calls if c[0] == "get_travel_time"}
    assert ("busan-tower", "gwangalli-beach") in asked  # 같은 beach
    # s4 의 이웃(부산타워)에서, 또는 s4 장소(해운대)에서 시장·거리까지 (도보권 상권 판정)
    local = {pid for pid, p in ctx.places.items() if p.category in ("market", "street")}
    assert all(a == "busan-tower" or (a == "haeundae-beach" and b in local) for a, b in asked)
    assert any(a == "haeundae-beach" for a, _ in asked)
    assert ("busan-tower", "haeundae-beach") not in asked  # 이미 아는 구간은 다시 묻지 않는다


def test_with_repair_travel_adds_candidate_crowd_and_hours():
    # 후보의 집중률·운영시간을 모르면 붐비거나 휴무인 장소가 "문제없음"으로 대안에 나온다
    lookups = fake_lookups(
        crowd={"haeundae-beach": 70, "songjeong-beach": 99},
        hours={"busan-museum-of-art": {"opens": "10:30", "closes": "20:00", "closed_weekdays": [], "closed_dates": []}},
    )
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)
    assert "songjeong-beach" not in ctx.crowd
    ctx = with_repair_travel(ctx, PLAN, ["s4"], lookups=lookups)
    assert ctx.crowd["songjeong-beach"] == 99.0  # 같은 beach 후보
    assert ctx.crowd["haeundae-beach"] == 70.0  # 일정 장소 값은 그대로
    assert ctx.hours["busan-museum-of-art"].opens == dt.time(10, 30)  # 실내 후보


def test_run_check_skips_equally_crowded_candidate():
    # 토요일 해운대 99(high). 송정도 99 라 바꿔도 high 가 남아 대안이 아니다. 광안리(80)만 남는다
    lookups = fake_lookups(
        crowd={"haeundae-beach": 99, "songjeong-beach": 99, "gwangalli-beach": 80},
        travel=TRAVEL | {("busan-tower", "gwangalli-beach"): 30, ("busan-tower", "songjeong-beach"): 45},
    )
    response = run_check(PLAN, DemoOverride(now=at(9)), lookups=lookups)
    targets = [next(c.after.place_id for c in o.changes if c.after) for o in response.repairs["s4-crowded"]
               if o.action == "replace"]
    assert targets == ["gwangalli-beach"]


def test_resolve_now_priority(monkeypatch):
    monkeypatch.setattr(config, "DEMO_NOW", "2026-11-21T13:40:00")
    assert resolve_now(at(9)) == at(9)  # demo.now 가 먼저
    assert resolve_now() == at(13, 40)  # 시간대가 없으면 KST
    monkeypatch.setattr(config, "DEMO_NOW", None)
    assert resolve_now().tzinfo == KST


def test_weather_preset(tmp_path, monkeypatch):
    (tmp_path / "rain-afternoon.json").write_text(json.dumps(RAIN_15_18), encoding="utf-8")
    monkeypatch.setattr(guardian_context, "WEATHER_PRESET_DIR", tmp_path)

    assert load_weather_preset("rain-afternoon")[8].pty == 1
    ctx = build_context(PLAN, demo_now=at(9), weather_preset="rain-afternoon", lookups=fake_lookups())
    assert ctx.weather is not None  # get_weather 대신 샘플 예보
    for bad in ("no-such", "../places", "Rain"):
        with pytest.raises(WeatherPresetNotFound):
            load_weather_preset(bad)


# ---------- 작업 9: run_check / run_delay ----------

def test_run_check_rain_gives_indoor_replace_and_places():
    response = run_check(PLAN, DemoOverride(now=at(9)), lookups=fake_lookups(weather=RAIN_15_18))

    assert response.checked_at == at(9)
    assert [i.issue_id for i in response.issues] == ["s4-rain", "s1-crowded", "s3-crowded"]
    assert set(response.repairs) == {"s4-rain", "s1-crowded", "s3-crowded"}
    first = response.repairs["s4-rain"][0]
    assert first.action == "replace"
    assert next(c.after.place_id for c in first.changes) == "busan-museum-of-art"
    assert (first.metrics.changed, first.metrics.extra_travel_min) == (1, 5)
    assert [p.place_id for p in response.places] == ["busan-museum-of-art"]


def test_run_check_no_issue_gives_empty_repairs():
    # 토요일 요일 규칙 장소(감천·부산타워)를 뺀 일정은 문제가 없다 → issues [], repairs {} (요구사항 2.10)
    plan = PLAN.model_copy(update={"stops": [PLAN.stops[1], PLAN.stops[3]]})
    response = run_check(plan, DemoOverride(now=at(9)), lookups=fake_lookups())
    assert (response.issues, response.repairs, response.places) == ([], {}, [])


def test_run_delay_like_contract_example():
    lookups = fake_lookups(travel=TRAVEL | {("busan-tower", "haeundae-beach"): 20})
    response = run_delay(PLAN, 30, DemoOverride(now=at(13, 40)), lookups=lookups)

    assert response.now == at(13, 40)
    first = response.repairs[0]
    assert first.action == "move_time"
    assert [(c.stop_id, c.after.start, c.after.end) for c in first.changes] == [("s3", at(14), at(15))]
    assert first.metrics.locked_kept is True


# ---------- handler ----------

def call(method, path, body):
    result = handler(make_event(method, path, json.dumps(body) if body is not None else None))
    return result["statusCode"], result["body"]


def test_handler_plan_check_uses_guardian(no_lookup_data):
    # 조회 데이터가 없으면 요일 규칙만 남는다 (감천 토요일 → remove 하나, 계약 예시와 같은 경우. 부산타워도 요일 규칙)
    status, body = call("POST", "/plan/check", {"plan_id": PLAN.plan_id, "demo": {"now": at(9).isoformat()}})
    assert status == 200
    response = CheckResponse.model_validate_json(body)
    assert response.checked_at == at(9)
    assert [i.issue_id for i in response.issues] == ["s1-crowded", "s3-crowded"]
    assert [o.action for o in response.repairs["s1-crowded"]] == ["remove"]


def test_handler_plan_check_with_real_lookup(monkeypatch):
    # 실제 lookup.py 를 쓴다. 실행 환경과 무관하게 예보는 건너뛰도록 USE_MOCK·키를 끈다.
    # 요일 규칙(감천 토요일)과 이동 시간 추정표(부산타워 → 해운대 약 52분, 일정 간격 60분 → 여유 8분)가 남는다.
    # 감천의 같은 village(흰여울)도 요일 규칙 대상이라 토요일엔 교체해도 혼잡이 남아 replace 는 나오지 않는다
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "DATA_GO_KR_KEY", "")
    status, body = call("POST", "/plan/check", {"plan_id": PLAN.plan_id, "demo": {"now": at(9).isoformat()}})
    assert status == 200
    response = CheckResponse.model_validate_json(body)
    assert response.checked_at == at(9)
    # 집중률(congestion.json, 11/21 토): s4 해운대 97.18 → medium(98 미만), s2 자갈치 94.56 → 95 미만이라 문제 없음
    # 부산타워는 집중률에 없어 요일 규칙(토 medium)
    assert [i.issue_id for i in response.issues] == ["s1-crowded", "s3-crowded", "s4-crowded", "s4-tight_transfer"]
    assert "replace" not in {o.action for o in response.repairs["s1-crowded"]}


def test_handler_plan_check_with_mock_samples(monkeypatch):
    # USE_MOCK=1: B 의 data/weather/2026-11-21.json(15~18시 비) → 해운대 rain high 가 맨 앞
    monkeypatch.setattr(config, "USE_MOCK", True)
    status, body = call("POST", "/plan/check", {"plan_id": PLAN.plan_id, "demo": {"now": at(9).isoformat()}})
    assert status == 200
    response = CheckResponse.model_validate_json(body)
    assert [(i.issue_id, i.severity) for i in response.issues][0] == ("s4-rain", "high")
    assert set(response.repairs) == {i.issue_id for i in response.issues}


def test_handler_delay_route(no_lookup_data):
    status, body = call("POST", f"/plan/{PLAN.plan_id}/delay",
                        {"plan_id": PLAN.plan_id, "delay_min": 30, "demo": {"now": at(13, 40).isoformat()}})
    assert status == 200
    response = DelayResponse.model_validate_json(body)
    assert response.now == at(13, 40)
    assert response.repairs[0].action == "move_time"
    assert all(c.stop_id != "s2" for o in response.repairs for c in o.changes)


@pytest.mark.parametrize(
    "path, body, status, code",
    [
        ("/plan/plan-1/delay", {"plan_id": "plan-1", "delay_min": 0}, 422, "validation_error"),
        ("/plan/plan-1/delay", {"plan_id": "other", "delay_min": 30}, 422, "validation_error"),
        ("/plan/no-such/delay", {"plan_id": "no-such", "delay_min": 30}, 404, "plan_not_found"),
        ("/plan/check", {"plan_id": "plan-1", "demo": {"weather_preset": "no-such"}}, 422, "validation_error"),
    ],
)
def test_handler_guardian_errors(path, body, status, code):
    got_status, got_body = call("POST", path, body)
    assert got_status == status
    assert ErrorResponse.model_validate_json(got_body).error.code == code
