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
    ("busan-tower", "shinsegae-centum-city"): 45,
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
    assert "shinsegae-centum-city" not in {p for pair in ctx.travel_min for p in pair}  # 교체 후보는 아직
    assert set(ctx.places) >= {"haeundae-beach", "shinsegae-centum-city"}


def test_build_context_skips_missing_or_failing_tools():
    # 도구가 없거나(get_hours 등 미구현), 예외를 던지거나, error 를 돌려줘도 점검은 계속된다 (요구사항 6.4)
    def boom(*args):
        raise NotImplementedError("TODO(도구 담당)")

    lookups = SimpleNamespace(get_weather=boom, get_crowd=lambda *a: {"error": {"code": "x", "message": "y"}})
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)
    assert (ctx.weather, ctx.crowd, ctx.hours, ctx.travel_min, ctx.events) == (None, {}, {}, {}, [])
    # 이 context 로도 check_plan 이 돈다: 요일 규칙(감천, 토요일)만 남는다
    response = run_check(PLAN, DemoOverride(now=at(9)), lookups=lookups)
    assert [i.issue_id for i in response.issues] == ["s1-crowded"]


def test_build_context_works_with_current_lookup_module():
    # 지금 main 의 app/tools/lookup.py (시그니처만 있음)로도 실패하지 않는다
    ctx = build_context(PLAN, demo_now=at(9))
    assert ctx.weather is None and ctx.crowd == {}


def test_with_repair_travel_adds_candidates_for_issue_stops_only():
    calls = []
    lookups = fake_lookups(calls=calls)
    ctx = build_context(PLAN, demo_now=at(9), lookups=lookups)
    calls.clear()
    ctx = with_repair_travel(ctx, PLAN, ["s4", "s2"], lookups=lookups)  # s2 는 고정이라 무시

    assert ctx.travel("busan-tower", "shinsegae-centum-city") == 45
    asked = {c[1:] for c in calls if c[0] == "get_travel_time"}
    assert ("busan-tower", "gwangalli-beach") in asked  # 같은 beach
    assert all("busan-tower" == a for a, _ in asked)  # s4 의 이웃(부산타워)에서만
    assert ("busan-tower", "haeundae-beach") not in asked  # 이미 아는 구간은 다시 묻지 않는다


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
    assert [i.issue_id for i in response.issues] == ["s4-rain", "s1-crowded"]
    assert set(response.repairs) == {"s4-rain", "s1-crowded"}
    first = response.repairs["s4-rain"][0]
    assert first.action == "replace"
    assert next(c.after.place_id for c in first.changes) == "shinsegae-centum-city"
    assert (first.metrics.changed, first.metrics.extra_travel_min) == (1, 5)
    assert [p.place_id for p in response.places] == ["shinsegae-centum-city"]


def test_run_check_no_issue_gives_empty_repairs():
    # 토요일 감천(요일 규칙)을 뺀 일정은 문제가 없다 → issues [], repairs {} (요구사항 2.10)
    plan = PLAN.model_copy(update={"stops": PLAN.stops[1:]})
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


def test_handler_plan_check_uses_guardian():
    # 실제 lookup.py 를 쓴다. 키가 없어 예보는 건너뛰고, 요일 규칙(감천 토요일)과
    # 이동 시간 추정표(부산타워 → 해운대 약 52분, 일정 간격 60분 → 여유 8분)가 남는다.
    # 이동 시간을 알게 되어 감천은 remove 대신 같은 분류 장소로 replace 를 제안한다
    status, body = call("POST", "/plan/check", {"plan_id": PLAN.plan_id, "demo": {"now": at(9).isoformat()}})
    assert status == 200
    response = CheckResponse.model_validate_json(body)
    assert response.checked_at == at(9)
    assert [i.issue_id for i in response.issues] == ["s1-crowded", "s4-tight_transfer"]
    assert [o.action for o in response.repairs["s1-crowded"]] == ["replace"]


def test_handler_delay_route():
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
