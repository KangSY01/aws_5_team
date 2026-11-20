"""데모 장면 1 일정 캐시 (app/chat/demo_cache.py, agent._demo_response). AWS·Bedrock 없이 돈다.

- DEMO_CACHE_ENABLED 가 켜져 있고 대본 문장이 그대로 들어왔을 때만 대본 일정을 돌려준다.
- 일정은 평소 저장 경로로 저장되고, /plan·/plan/check·PUT(적용·되돌리기)가 그대로 동작한다.
- Guardian 배지·대안은 실제 Guardian 점검 결과다 (이 테스트는 Guardian 을 대신하지 않는다).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import agent, config
from app.chat import demo_cache
from app.chat.plan_rules import load_places, place_name
from app.handler import handler
from app.models.api import ChatResponse, CheckResponse, PlanResponse
from app.models.plan import Plan
from app.tools import lookup
from chat_stubs import ScriptedModel, text_turn
from scripts.local_invoke import make_event

TRIGGER = "11月28日(土)に釜山で一日過ごしたいです。海が見える所と、夜は光の祭りに行きたいです。辛いものは苦手です。"
PROFILE = {"language": "ja", "interests": ["sea"], "companions": "couple", "diet": []}
EXPECTED_STOPS = [
    ("s1", "dongbaekseom", "2026-11-28T10:00:00+09:00", "2026-11-28T11:30:00+09:00"),
    ("s2", "haeundae-rodeo-street", "2026-11-28T12:00:00+09:00", "2026-11-28T13:00:00+09:00"),
    ("s3", "haeundae-beach", "2026-11-28T14:30:00+09:00", "2026-11-28T16:00:00+09:00"),
    ("s4", "haeundae-beach", "2026-11-28T17:30:00+09:00", "2026-11-28T19:30:00+09:00"),
]
DEMO_NOW = {"now": "2026-11-28T09:00:00+09:00"}  # 시연 기준 시각 (11/28 빛축제 개막일 아침)
FIELDS = {"session_id", "plan_id", "answer", "language", "sources", "plan_changes"}


def call(method, path, body=None):
    result = handler(make_event(method, path, None if body is None else json.dumps(body, ensure_ascii=False)))
    return result["statusCode"], json.loads(result["body"])


def chat(message=TRIGGER, profile=PROFILE, **ids):
    return call("POST", "/chat", {**ids, "message": message, "profile": profile})


@pytest.fixture
def demo_on(monkeypatch):
    """실제 모델 경로(FAKE_LLM 꺼짐) + 데모 캐시 켜짐. 모델이 불리면 실패한다."""
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    monkeypatch.setattr(agent, "get_model", lambda: pytest.fail("데모 캐시 요청에서 모델을 부르면 안 된다"))


def stops_of(plan: dict) -> list[tuple]:
    return [(s["stop_id"], s["place_id"], s["start"], s["end"]) for s in plan["stops"]]


# ---- 스위치 ----


@pytest.mark.parametrize("value, enabled", [(None, False), ("", False), ("false", False), ("0", False),
                                            ("true", True), ("TRUE", True), ("1", True), (" yes ", True)])
def test_demo_cache_switch_defaults_to_off(value, enabled):
    env = {k: v for k, v in os.environ.items() if k != "DEMO_CACHE_ENABLED"}
    if value is not None:
        env["DEMO_CACHE_ENABLED"] = value
    out = subprocess.run([sys.executable, "-c", "from app import config; print(config.DEMO_CACHE_ENABLED)"],
                         cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == str(enabled)


def test_the_switch_is_off_in_tests_by_default():
    assert config.DEMO_CACHE_ENABLED is False


# ---- 문장 비교 ----


@pytest.mark.parametrize("message", [
    TRIGGER,
    f"  {TRIGGER}\n",
    TRIGGER.replace("。", "。 "),
    TRIGGER.replace("(土)", "（土）").replace("11月28日", "１１月２８日"),  # 전각 괄호·숫자
])
def test_trigger_matches_with_minimal_normalization(monkeypatch, message):
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    assert demo_cache.matches(message)


@pytest.mark.parametrize("message", [
    TRIGGER.rstrip("。"),  # 마지막 마침표 없음
    TRIGGER.replace("11月28日", "11月29日"),
    TRIGGER.replace("辛いものは苦手です。", ""),
    "11月28日(土)に釜山で一日過ごしたいです。海が見える場所と、夜は光の祭りに行きたいです。辛いものは苦手です。",
    "I want to spend a day in Busan on Nov 28. Sea views, and the light festival at night. No spicy food.",
    "",
])
def test_similar_but_different_requests_do_not_match(monkeypatch, message):
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    assert not demo_cache.matches(message)


def test_trigger_does_not_match_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", False)
    assert not demo_cache.matches(TRIGGER)


# ---- 데이터 근거 ----


def test_demo_places_and_festival_come_from_the_real_data():
    places = load_places()
    assert all(pid in places for _, pid, _, _ in demo_cache.STOPS)  # 새 장소 ID 를 만들지 않는다
    events = lookup.get_events(date="2026-11-28")["events"]
    festival = next(e for e in events if e["name"] == demo_cache.FESTIVAL_NAME)
    assert "haeundae-beach" in festival["place_ids"]  # 빛축제 자리는 행사 장소 해운대해수욕장이다


# ---- /chat 응답과 저장 ----


def test_trigger_returns_the_script_plan_and_saves_it(demo_on, api_storage):
    status, body = chat()

    assert status == 200 and set(body) == FIELDS
    response = ChatResponse.model_validate(body)
    stored = api_storage.get_plan(response.plan_id)
    assert stops_of(stored.model_dump(mode="json")) == EXPECTED_STOPS
    assert all(stop.locked is False for stop in stored.stops)  # 빛축제도 처음에는 고정하지 않는다
    assert stored.profile.language == "ja" and stored.date.isoformat() == "2026-11-28"
    assert api_storage.get_session(response.session_id).plan_id == response.plan_id  # 세션에 연결된다

    assert [(c.stop_id, c.before) for c in response.plan_changes] == [(s, None) for s, *_ in EXPECTED_STOPS]
    assert [c.after for c in response.plan_changes] == stored.stops
    names = [place_name(load_places()[pid], "ja") for _, pid, _, _ in EXPECTED_STOPS[:3]]
    assert response.language == "ja" and all(name in response.answer for name in names)
    assert "해운대 빛축제" in response.answer and "[place:" not in response.answer
    assert [(s.tool, s.id) for s in response.sources] == [("get_events", "2026-11-28")]


def test_answer_follows_the_profile_language(demo_on):
    _, body = chat(profile={"language": "en"})
    assert body["language"] == "en" and "4-stop plan for 2026-11-28" in body["answer"]
    assert "Haeundae Beach (해운대 빛축제)" in body["answer"]


def test_each_demo_run_gets_a_fresh_plan(demo_on, api_storage):
    _, first = chat()
    plan = Plan.model_validate(call("GET", f"/plan/{first['plan_id']}")[1]["plan"])
    edited = plan.model_copy(update={"stops": plan.stops[:3]})  # 지난 시연에서 일정을 바꿨다
    assert call("PUT", f"/plan/{first['plan_id']}", json.loads(edited.model_dump_json()))[0] == 200

    _, again = chat(session_id=first["session_id"], plan_id=first["plan_id"])  # 같은 세션에서 다시 시연

    assert again["plan_id"] != first["plan_id"] and again["session_id"] == first["session_id"]
    assert stops_of(call("GET", f"/plan/{again['plan_id']}")[1]["plan"]) == EXPECTED_STOPS
    assert len(api_storage.get_plan(first["plan_id"]).stops) == 3  # 지난 일정은 건드리지 않는다
    assert api_storage.get_session(first["session_id"]).plan_id == again["plan_id"]


# ---- Guardian: 실제 점검 결과, 적용, 되돌리기 ----


def test_guardian_badges_alternatives_apply_and_undo_on_the_demo_plan(demo_on):
    _, body = chat()
    plan_id = body["plan_id"]
    original = call("GET", f"/plan/{plan_id}")[1]["plan"]

    status, check = call("POST", "/plan/check", {"plan_id": plan_id, "demo": DEMO_NOW})
    assert status == 200
    check = CheckResponse.model_validate(check)
    issues = {i.issue_id: i for i in check.issues}
    assert issues["s3-crowded"].severity == "high"  # 해운대 🔴 (집중률 + 행사일 가중)
    replaced = [c.after.place_id for o in check.repairs["s3-crowded"] if o.action == "replace" for c in o.changes if c.after]
    # 해운대 혼잡 대안: 도보권 상권(시장·거리)이 먼저 오고, 첫 대안은 걸어서 6분 해운대시장 (장면 2)
    assert replaced[0] == "haeundae-market"
    places = load_places()
    commerce = [places[place_id].category in ("market", "street") for place_id in replaced]
    assert commerce[0] and commerce == sorted(commerce, reverse=True)

    # 발표자가 화면에서 빛축제를 잠근다 (PUT) → 빛축제 배지는 고정 일정으로 낮아진다
    locked = json.loads(json.dumps(original))
    locked["stops"][3]["locked"] = True
    assert call("PUT", f"/plan/{plan_id}", locked)[0] == 200
    after_lock = CheckResponse.model_validate(call("POST", "/plan/check", {"plan_id": plan_id, "demo": DEMO_NOW})[1])
    s4 = next(i for i in after_lock.issues if i.issue_id == "s4-crowded")
    assert s4.severity != "high" and not after_lock.repairs.get("s4-crowded")

    # 해운대시장 대안 적용 → 해운대 🔴 가 낮아진다 → 되돌리기
    option = next(o for o in after_lock.repairs["s3-crowded"]
                  if any(c.after and c.after.place_id == "haeundae-market" for c in o.changes))
    applied = json.loads(json.dumps(locked))
    for change in option.changes:
        index = next(i for i, s in enumerate(applied["stops"]) if s["stop_id"] == change.stop_id)
        applied["stops"][index] = json.loads(change.after.model_dump_json())
    assert call("PUT", f"/plan/{plan_id}", applied)[0] == 200
    rechecked = CheckResponse.model_validate(call("POST", "/plan/check", {"plan_id": plan_id, "demo": DEMO_NOW})[1])
    # 해운대 🔴 high 가 해운대시장으로 바뀌면 low 로 내려간다 (빛축제 근처라 행사일 가중은 남는다)
    after = {i.issue_id: i.severity for i in rechecked.issues}
    assert after.get("s3-crowded") in (None, "low")

    assert call("PUT", f"/plan/{plan_id}", locked)[0] == 200  # 되돌리기
    assert PlanResponse.model_validate(call("GET", f"/plan/{plan_id}")[1]).plan == Plan.model_validate(locked)


# ---- 일반 요청은 그대로 ----


@pytest.mark.parametrize("enabled, message", [
    (True, "11月28日に釜山で海と光の祭りを楽しみたいです。"),  # 비슷한 다른 문장
    (False, TRIGGER),  # 대본 문장이어도 스위치가 꺼져 있으면
])
def test_other_requests_still_use_the_real_model(monkeypatch, api_storage, enabled, message):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", enabled)
    model = ScriptedModel([text_turn("こんにちは。")])
    monkeypatch.setattr(agent, "get_model", lambda: model)

    status, body = chat(message)

    assert status == 200 and len(model.requests) == 1 and body["answer"] == "こんにちは。"
    assert api_storage.get_plan(body["plan_id"]).stops == []


def test_fake_llm_still_answers_non_trigger_messages(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    sample = ChatResponse.model_validate_json(agent._FAKE_RESPONSE_PATH.read_text(encoding="utf-8"))

    _, body = chat("hello")

    assert body["answer"] == sample.answer


# ---- 배포 설정 ----


def test_lambda_template_and_deploy_script_can_switch_the_demo_cache():
    pytest.importorskip("yaml")
    from test_api_deploy import API_TEMPLATE, DEPLOY_SCRIPT, load_template

    template = load_template(API_TEMPLATE)
    param = template["Parameters"]["DemoCacheEnabled"]
    assert param["Default"] == "false" and set(param["AllowedValues"]) == {"true", "false"}
    env = template["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
    assert env["DEMO_CACHE_ENABLED"] == {"Ref": "DemoCacheEnabled"}
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8-sig")
    assert '[ValidateSet("true", "false")] [string]$DemoCache = "false"' in script
    assert '"DemoCacheEnabled=$DemoCache"' in script
