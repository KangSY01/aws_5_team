"""음식점 ID(kto-…)의 검증. 답변 표식과 일정 장소 ID 를 따로 본다. AWS·Bedrock 없이 돈다.

D 의 프롬프트는 "도구 결과에 나온 ID 를 [place:ID] 로 쓰라" 고 하므로 모델이 음식점도 [place:kto-…] 로 쓴다.
- 답변: 이번 요청의 get_restaurants 결과에 실제로 나온 restaurant_id 만 음식점 이름으로 바꾼다. 아니면 검증 실패.
- 일정: 기존 계약 그대로 places.json 의 place_id 만 들어간다. kto-… 는 일정 도구가 거부한다.
음식점 데이터는 B 의 실제 restaurants.json 을 쓴다.
"""

import pytest

from app import agent, config
from app.chat import answer as chat_answer
from app.chat.plan_rules import load_places, place_name
from app.chat.tools import ToolOutput, grounded_place_ids
from app.models.api import ChatRequest
from app.models.plan import Profile
from app.tools.restaurants import get_restaurants
from chat_stubs import ScriptedModel, text_turn, tool_turn

PLAN_ID = "plan-1"
MULTI = "kto-4095461"  # 해운대해수욕장 주변. 영어·일본어·중국어 이름이 있다
KO_ONLY = "kto-133313"  # 자갈치시장 주변. 한국어 이름만 있다


def restaurant(rid: str, near: str) -> dict:
    data = get_restaurants(place_id=near, limit=20)
    return next(r for r in data["restaurants"] if r["restaurant_id"] == rid)


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def run(model, message="Where should I eat near Haeundae Beach?", language="en", **ids):
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=message, profile={"language": language}, **ids))

    return run


# ---- 데이터 전제 ----


def test_fixture_restaurants_exist_in_the_real_data():
    assert restaurant(MULTI, "haeundae-beach")["names"].get("en")
    assert restaurant(KO_ONLY, "jagalchi-market")["names"] == {}
    assert MULTI not in load_places() and KO_ONLY not in load_places()  # 장소 ID 가 아니다


# ---- 답변 표식 ----


def test_restaurant_markers_from_this_turn_render_as_restaurant_names(chat, api_storage):
    model = ScriptedModel([
        tool_turn(("get_restaurants", {"place_id": "haeundae-beach"})),
        text_turn(f"Near [place:haeundae-beach], try [place:{MULTI}]. Ask about dietary needs."),
    ])

    response = chat(model)

    assert "[place:" not in response.answer
    assert restaurant(MULTI, "haeundae-beach")["names"]["en"] in response.answer
    assert place_name(load_places()["haeundae-beach"], "en") in response.answer
    assert ("get_restaurants", "haeundae-beach") in [(s.tool, s.id) for s in response.sources]  # 출처는 그대로
    assert response.plan_changes == [] and api_storage.get_plan(response.plan_id).stops == []


@pytest.mark.parametrize("language", ["ja", "zh-Hant"])
def test_restaurant_without_a_name_in_the_language_uses_the_korean_name(chat, language):
    model = ScriptedModel([
        tool_turn(("get_restaurants", {"place_id": "jagalchi-market"})),
        text_turn(f"[place:{KO_ONLY}]"),
    ])

    response = chat(model, language=language)

    assert response.answer == restaurant(KO_ONLY, "jagalchi-market")["name_ko"]


@pytest.mark.parametrize("marker, tools", [
    (KO_ONLY, [("get_restaurants", {"place_id": "haeundae-beach"})]),  # 이번 결과에 없는 음식점 (다른 장소 주변)
    (MULTI, [("search_places", {"query": "haeundae"})]),  # 음식점 도구를 부르지 않았다
    ("kto-999999999", [("get_restaurants", {"place_id": "haeundae-beach"})]),  # 지어낸 ID
])
def test_restaurant_markers_not_returned_this_turn_are_rejected(chat, marker, tools):
    model = ScriptedModel([tool_turn(*tools), text_turn(f"Try [place:{marker}].")])

    with pytest.raises(agent.ChatError) as error:
        chat(model)

    assert error.value.code == "invalid_model_output"


def test_restaurant_lookup_failure_gives_no_restaurant_markers(chat):
    model = ScriptedModel([
        tool_turn(("get_restaurants", {"place_id": "busan-tower"})),  # restaurants_not_collected
        text_turn(f"Try [place:{MULTI}]."),
    ])

    with pytest.raises(agent.ChatError):
        chat(model)


def test_place_markers_are_still_checked_as_before():
    grounded = {"haeundae-beach"}
    restaurants = {MULTI: {"en": "Somewhere"}}
    assert chat_answer.render_answer("[place:haeundae-beach]", "en", grounded, restaurants) == "Haeundae Beach"
    with pytest.raises(chat_answer.InvalidAnswer):  # 근거 없는 장소는 음식점 목록이 있어도 실패
        chat_answer.render_answer("[place:busan-tower]", "en", grounded, restaurants)
    with pytest.raises(chat_answer.InvalidAnswer):  # 장소 이름을 표식 없이 쓴 것도 그대로 실패
        chat_answer.render_answer(f"[place:{MULTI}] near Busan Tower", "en", grounded, restaurants)


def test_restaurant_names_only_come_from_successful_restaurant_results():
    ok = get_restaurants(place_id="haeundae-beach", limit=3)
    outputs = [
        ToolOutput("get_restaurants", {}, ok),
        ToolOutput("get_restaurants", {}, {"error": {"code": "restaurants_not_collected", "message": "x"}}),
        ToolOutput("get_restaurants", {}, {"restaurants": [{"restaurant_id": 1}, "junk", {"name_ko": "이름만"}]}),
        ToolOutput("search_places", {}, [{"place_id": "haeundae-beach", "restaurant_id": "kto-1"}]),
    ]
    assert set(chat_answer.restaurant_names(outputs)) == {r["restaurant_id"] for r in ok["restaurants"]}


# ---- 일정 장소 ID (기존 계약) ----


def test_restaurant_ids_are_never_grounded_places():
    outputs = [ToolOutput("get_restaurants", {}, get_restaurants(place_id="haeundae-beach", limit=5))]
    assert grounded_place_ids(outputs) == {"haeundae-beach"}  # 검색 기준 장소만, kto-… 는 아니다


def test_a_restaurant_cannot_replace_a_stop(chat, api_storage):
    session = api_storage.create_session(Profile(language="en"), plan_id=PLAN_ID).session_id
    before = api_storage.get_plan(PLAN_ID)
    model = ScriptedModel([
        tool_turn(("get_restaurants", {"place_id": "haeundae-beach"})),
        tool_turn(("replace_stop", {"stop_id": "s4", "new_place_id": MULTI})),
        text_turn("I could not change the plan."),
    ])

    response = chat(model, message="Replace the beach with a restaurant", session_id=session, plan_id=PLAN_ID)

    _, result = model.tool_results()[1]
    assert "error" in result  # 일정 도구가 거부한다 (places.json·search_places 결과에 없는 ID)
    assert response.plan_changes == [] and api_storage.get_plan(PLAN_ID) == before


def test_a_restaurant_cannot_be_put_in_a_new_plan(chat, api_storage):
    model = ScriptedModel([
        tool_turn(("search_places", {"query": ""}), ("get_restaurants", {"place_id": "haeundae-beach"})),
        tool_turn(("create_plan", {"place_ids": ["haeundae-beach", "gwangalli-beach", MULTI], "date": "2026-11-28"})),
        text_turn("ok"),
    ])

    response = chat(model)

    assert MULTI not in {s.place_id for s in api_storage.get_plan(response.plan_id).stops}
    assert all(s.place_id in load_places() for s in api_storage.get_plan(response.plan_id).stops)
