"""run_chat 의 실제 모델 경로(작업 4·5). 스텁 모델로 에이전트 루프를 돌리므로 Bedrock·AWS·네트워크가 필요 없다.

저장소는 conftest.py 의 api_storage(샘플 일정 plan-1 이 든 메모리 저장소)를 쓴다. 장소와 일정 계산은 B 의 실제
places.json·build_plan 이다.
"""

import json
import logging
from collections import Counter

import pytest
from chat_stubs import ScriptedModel, text_turn, tool_turn
from strands import tool

from app import agent, config, prompts, storage
from app.chat import tools as chat_tools
from app.chat.messages import BUILD_ERROR_KEYS, LANGUAGES, message
from app.chat.plan_rules import load_places, place_name
from app.handler import handler
from app.models.api import ChatRequest, ChatResponse, CheckResponse, DelayResponse, PlanResponse
from app.models.plan import Plan, Profile, StopChange
from app.tools.schedule import PlanBuildError, build_plan
from scripts.local_invoke import make_event

PLAN_ID = "plan-1"  # 샘플 일정(conftest): s1 감천 · s2 자갈치(고정) · s3 부산타워 · s4 해운대
LOOKUP = {"search_places", "get_place_info", "get_crowd", "get_weather", "get_hours", "get_travel_time", "get_events"}
EDITING = {"replace_stop", "add_stop", "remove_stop", "move_stop"}
IDS = ["gamcheon-village", "jagalchi-market", "busan-tower", "haeundae-beach"]
NOW_1128 = {"now": "2026-11-28T09:00:00+09:00"}
CREATE_TEXT = "I planned it: [place:gamcheon-village], [place:jagalchi-market], [place:busan-tower], [place:haeundae-beach]."


def create_script(ids=IDS, text=CREATE_TEXT, **create_args):
    return [
        tool_turn(("search_places", {"query": ""})),
        tool_turn(("create_plan", {"place_ids": ids, **create_args})),
        text_turn(text),
    ]


def edit_script(*tool_calls, text="Nothing else changes."):
    return [tool_turn(("search_places", {"query": "gwangalli"})), *[tool_turn(c) for c in tool_calls], text_turn(text)]


@pytest.fixture
def chat(monkeypatch):
    """실제 모델 경로를 스텁 모델로 돌린다. FAKE_LLM 은 꺼진다."""
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def run(model, message="hello", language="en", session_id=None, plan_id=None, demo=None) -> ChatResponse:
        monkeypatch.setattr(agent, "get_model", lambda: model)
        request = ChatRequest(
            message=message, profile={"language": language}, session_id=session_id, plan_id=plan_id, demo=demo
        )
        return agent.run_chat(request)

    return run


def linked_session(api_storage, language="en") -> str:
    """샘플 일정(plan-1)에 연결된 세션."""
    return api_storage.create_session(Profile(language=language), plan_id=PLAN_ID).session_id


def sample(api_storage) -> Plan:
    return api_storage.get_plan(PLAN_ID)


# ---- FAKE_LLM 경로 유지 ----


def test_fake_llm_path_is_unchanged_and_touches_neither_model_nor_storage(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    monkeypatch.setattr(agent, "get_model", lambda: pytest.fail("FAKE_LLM 에서 모델을 만들면 안 된다"))
    monkeypatch.setattr(storage, "create_session", lambda *a, **k: pytest.fail("FAKE_LLM 에서 세션을 만들면 안 된다"))

    response = agent.run_chat(ChatRequest(message="hi", profile={"language": "en"}))

    assert (response.session_id, response.plan_id, response.language) == ("sess-1", "plan-1", "ja")


# ---- 도구 등록과 프롬프트 ----


def test_create_mode_registers_lookup_tools_and_create_plan(chat):
    model = ScriptedModel([text_turn("Hello!")])
    chat(model)
    assert model.tool_names == LOOKUP | {"create_plan"}
    assert "get_place_info" in model.tool_names  # B 의 PR #37 에서 추가된 Agent 전용 도구


def test_edit_mode_registers_lookup_and_editing_tools_but_not_create_plan(chat, api_storage):
    model = ScriptedModel([text_turn("Hello!")])
    chat(model, session_id=linked_session(api_storage), plan_id=PLAN_ID)
    assert model.tool_names == LOOKUP | EDITING


def test_system_prompt_carries_context_but_not_the_user_message(chat, api_storage):
    model = ScriptedModel([text_turn("ok")])
    chat(model, message="SECRET-USER-TEXT", language="ja", session_id=linked_session(api_storage, "ja"), plan_id=PLAN_ID,
         demo=NOW_1128)
    prompt = model.system_prompt
    assert "Japanese" in prompt and "TODAY: 2026-11-28" in prompt and "MODE: EDIT_ITINERARY" in prompt
    assert '"locked": true' in prompt and "jagalchi-market" in prompt  # CURRENT_PLAN
    assert "SECRET-USER-TEXT" not in prompt
    create = ScriptedModel([text_turn("ok")])
    chat(create)
    assert "MODE: NEW_ITINERARY" in create.system_prompt and "\nCURRENT_PLAN:" not in create.system_prompt  # 일정 데이터 줄이 없다


def test_the_agent_uses_the_final_system_prompt_written_by_d(chat, api_storage):
    assert agent.build_system_prompt is prompts.build_system_prompt  # 임시 프롬프트(app/chat/prompt.py)가 아니다
    create, edit = ScriptedModel([text_turn("ok")]), ScriptedModel([text_turn("ok")])

    chat(create, language="zh-Hant")
    chat(edit, language="zh-Hant", session_id=linked_session(api_storage, "zh-Hant"), plan_id=PLAN_ID, demo=NOW_1128)

    for prompt in (create.system_prompt, edit.system_prompt):  # 두 모드 모두 표식 규칙과 행사 이름 규칙이 들어 있다
        assert "Traditional Chinese" in prompt and "Write every place as [place:PLACE_ID]" in prompt
        assert 'never put a name next to the marker' in prompt
        assert "Events are not places; do not put them in a marker." in prompt
        assert "at most 5 tools" in prompt and "TODAY:" in prompt and "PROFILE:" in prompt
    assert "MODE: NEW_ITINERARY" in create.system_prompt and "\nCURRENT_PLAN:" not in create.system_prompt
    assert "MODE: EDIT_ITINERARY" in edit.system_prompt and "TODAY: 2026-11-28" in edit.system_prompt
    line = next(line for line in edit.system_prompt.splitlines() if line.startswith("CURRENT_PLAN:"))
    assert place_name(load_places()["gamcheon-village"], "zh-Hant") in line and '"locked": true' in line


def test_markers_written_by_the_final_prompt_still_render_and_events_stay_plain_text(chat):
    # D 의 프롬프트가 허용한 형태: 행사 이름은 한국어 원문 그대로, 장소는 표식으로만
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "haeundae"}), ("get_events", {"date": "2026-11-28"})),
        text_turn("The 부산불꽃축제 is on that day. For the beach, try [place:haeundae-beach]."),
    ])

    response = chat(model, demo=NOW_1128)

    assert "부산불꽃축제" in response.answer and "Haeundae Beach" in response.answer and "[place:" not in response.answer


def test_alternatives_from_get_place_info_count_as_grounded(chat):
    # D 의 프롬프트 규칙: 이번 요청의 도구 결과에 나온 place_id 는 답변에 쓸 수 있다
    model = ScriptedModel([
        tool_turn(("get_place_info", {"place_id": "haeundae-beach"})),
        text_turn("If [place:haeundae-beach] is crowded, [place:sea-life-busan] is an indoor option."),
    ])

    response = chat(model, demo=NOW_1128)

    assert "[place:" not in response.answer and ("get_place_info", "haeundae-beach") in [(s.tool, s.id) for s in response.sources]

# ---- 일정 생성 ----


def test_search_then_create_plan_saves_a_plan_built_by_build_plan(chat, api_storage):
    model = ScriptedModel(create_script())

    response = chat(model, demo=NOW_1128)

    stored = api_storage.get_plan(response.plan_id)
    # 방문 순서와 시각은 모델이 아니라 build_plan 이 정한다
    assert stored == build_plan(IDS, "2026-11-28", None, Profile(language="en"), plan_id=response.plan_id)
    assert stored.date.isoformat() == "2026-11-28"  # 날짜를 안 주면 오늘(데모 시각 기준)
    assert 3 <= len(stored.stops) <= 5
    assert response.plan_id.startswith("plan-") and len(response.plan_id) == len("plan-") + 32  # 서버가 발급한 ID
    assert [c.stop_id for c in response.plan_changes] == [s.stop_id for s in stored.stops]
    assert all(c.before is None for c in response.plan_changes)
    assert [c.after for c in response.plan_changes] == stored.stops
    assert "[place:" not in response.answer and "Gamcheon" in response.answer  # 표식은 이름으로 바뀐다
    in_search_order = [pid for pid in load_places() if pid in IDS]  # sources 는 도구 결과에 나온 순서다 (요구사항 4.6)
    assert [(s.tool, s.id) for s in response.sources] == [("search_places", pid) for pid in in_search_order]
    assert response.sources[0].title == load_places()[in_search_order[0]].names["en"]
    assert len(model.requests) == 3  # 검색 → 일정 생성 → 답변


def test_plan_id_is_issued_by_the_store_and_passed_to_build_plan_explicitly(chat, api_storage, monkeypatch):
    # build_plan 의 기본 ID 생성 방식(B 담당, 바뀔 수 있다)에 의존하지 않는다
    monkeypatch.setattr(storage, "new_plan_id", lambda: "plan-issued-by-the-store")
    seen = []

    def spy(place_ids, date, start, profile, plan_id=None):
        seen.append(plan_id)
        return build_plan(place_ids, date, start, profile, plan_id=plan_id)

    monkeypatch.setattr(chat_tools, "build_plan", spy)

    response = chat(ScriptedModel(create_script()))

    assert seen == ["plan-issued-by-the-store"]  # 명시적으로 넘겼다
    assert response.plan_id == "plan-issued-by-the-store"
    assert api_storage.get_plan("plan-issued-by-the-store").plan_id == "plan-issued-by-the-store"


def test_the_same_trip_requested_from_two_sessions_never_shares_a_plan_id(chat, api_storage):
    first = chat(ScriptedModel(create_script(date="2026-11-28")))
    second = chat(ScriptedModel(create_script(date="2026-11-28")))  # 같은 장소·날짜·프로필

    assert first.plan_id != second.plan_id and first.session_id != second.session_id
    assert api_storage.get_plan(first.plan_id).stops == api_storage.get_plan(second.plan_id).stops  # 내용은 같아도
    assert api_storage.get_session(first.session_id).plan_id == first.plan_id
    assert api_storage.get_session(second.session_id).plan_id == second.plan_id
    with pytest.raises(storage.PlanAccessDeniedError):  # 서로의 일정에는 접근할 수 없다
        api_storage.get_plan_for_session(first.session_id, second.plan_id)


def test_the_empty_plan_of_a_question_only_chat_works_with_the_plan_endpoints(chat, api_storage):
    plan_id = chat(ScriptedModel([text_turn("Hello!")])).plan_id

    def call(method, path, body=None):
        result = handler(make_event(method, path, body))
        return result["statusCode"], result["body"]

    status, body = call("GET", f"/plan/{plan_id}")
    assert status == 200 and PlanResponse.model_validate_json(body).plan.stops == []
    status, body = call("POST", "/plan/check", json.dumps({"plan_id": plan_id}))
    assert status == 200 and CheckResponse.model_validate_json(body).issues == []
    status, body = call("POST", f"/plan/{plan_id}/delay", json.dumps({"plan_id": plan_id, "delay_min": 30}))
    assert status == 200 and DelayResponse.model_validate_json(body).repairs == []


def test_new_session_is_created_and_linked_to_the_new_plan(chat, api_storage):
    response = chat(ScriptedModel(create_script()))

    session = api_storage.get_session(response.session_id)
    assert session.plan_id == response.plan_id and session.profile.language == "en"


def test_followup_request_with_the_returned_ids_edits_that_plan(chat, api_storage):
    first = chat(ScriptedModel(create_script()))
    model = ScriptedModel([text_turn("ok")])

    second = chat(model, session_id=first.session_id, plan_id=first.plan_id)

    assert model.tool_names == LOOKUP | EDITING and (second.session_id, second.plan_id) == (first.session_id, first.plan_id)
    third = chat(ScriptedModel([text_turn("ok")]), session_id=first.session_id)  # plan_id 를 잃어도 세션이 알고 있다
    assert third.plan_id == first.plan_id


@pytest.mark.parametrize("language", LANGUAGES)
def test_answers_and_sources_use_the_profile_language(chat, language):
    response = chat(ScriptedModel(create_script()), language=language)

    assert response.language == language
    expected = place_name(load_places()["haeundae-beach"], language)
    assert expected in response.answer
    assert {s.title for s in response.sources} == {place_name(load_places()[p], language) for p in IDS}
    assert ChatResponse.model_validate_json(response.model_dump_json()) == response  # 계약 모델 round-trip


def test_place_name_falls_back_when_the_profile_language_has_none(chat):
    # the-bay-101 은 일본어 이름이 없다 → 다른 언어 이름으로 대체하고 오류가 아니다
    ids = ["the-bay-101", "haeundae-beach", "busan-tower"]
    text = "[place:the-bay-101] [place:haeundae-beach] [place:busan-tower]"
    response = chat(ScriptedModel(create_script(ids, text)), language="ja")
    assert load_places()["the-bay-101"].names["en"] in response.answer
    assert all(s.title.strip() for s in response.sources)


def test_lookup_tools_become_sources_only_when_they_returned_data(chat, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)  # 실제 예보는 키가 없거나 범위 밖이라 데이터가 없다. 환경 변수와 무관하게 고정
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "haeundae"}), ("get_crowd", {"place_id": "haeundae-beach", "date": "2026-11-28"}),
                  ("get_travel_time", {"from_place_id": "haeundae-beach", "to_place_id": "busan-tower"})),
        tool_turn(("get_hours", {"place_id": "haeundae-beach"}), ("get_weather", {"date": "2026-11-28"})),
        text_turn("[place:haeundae-beach] has no crowd number today; the trip to the tower is about 30 minutes."),
    ])

    response = chat(model, demo=NOW_1128)

    assert [(s.tool, s.id) for s in response.sources] == [
        ("search_places", "haeundae-beach"),
        ("get_crowd", "haeundae-beach"),
        ("get_travel_time", "haeundae-beach>busan-tower"),
        ("get_hours", "haeundae-beach"),  # opens/closes 는 null 이어도 raw_text(원문)가 있으면 근거다 (PR #37)
    ]  # get_weather 는 예보가 없다 → 근거가 아니다
    assert all(s.title.strip() for s in response.sources)


def test_weather_with_forecast_data_is_a_source(chat, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)  # 샘플 예보(app/data/weather/2026-11-28.json)
    model = ScriptedModel([tool_turn(("get_weather", {"date": "2026-11-28"})), text_turn("No rain is expected.")])

    response = chat(model, language="zh-Hans", demo=NOW_1128)

    assert [(s.tool, s.id) for s in response.sources] == [("get_weather", "busan-2026-11-28")]
    assert response.sources[0].title == message("source_weather", "zh-Hans")


# ---- 일정 생성 실패 안내 ----


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("code", sorted(BUILD_ERROR_KEYS))
def test_plan_build_error_is_explained_in_the_user_language_and_nothing_is_saved(chat, api_storage, monkeypatch, code, language):
    def boom(*args, **kwargs):
        raise PlanBuildError(code, "internal detail")

    monkeypatch.setattr(chat_tools, "build_plan", boom)

    response = chat(ScriptedModel(create_script(text="Your plan is ready!")), language=language)

    assert response.answer == message(code, language)  # 모델의 문장은 쓰지 않는다
    assert response.plan_changes == [] and "internal detail" not in response.answer
    assert api_storage.get_plan(response.plan_id).stops == []  # 일정을 저장하지 않았다. plan_id 만 있는 빈 일정


def test_unknown_build_error_code_falls_back_to_the_generic_notice(chat, monkeypatch):
    def boom(*args, **kwargs):
        raise PlanBuildError("brand_new_code", "x")

    monkeypatch.setattr(chat_tools, "build_plan", boom)
    assert chat(ScriptedModel(create_script())).answer == message("incomplete", "en")


def test_create_plan_with_places_that_were_not_searched_is_blocked(chat, api_storage):
    model = ScriptedModel([tool_turn(("create_plan", {"place_ids": IDS})), text_turn("Your plan is ready!")])

    response = chat(model)

    assert any("place_not_searched" in text for _, text in model.tool_results())
    assert response.answer == message("no_valid_places", "en") and response.plan_changes == []
    assert api_storage.get_plan(response.plan_id).stops == []


def test_a_question_without_a_plan_still_returns_a_real_plan_id(chat, api_storage):
    first = chat(ScriptedModel([text_turn("Hello! Tell me what you like.")]))

    assert first.plan_changes == [] and first.sources == []
    empty = api_storage.get_plan(first.plan_id)  # 프론트엔드가 plan_id 를 필수로 쓰므로 빈 일정이라도 실제로 있다
    assert empty.stops == [] and api_storage.get_session(first.session_id).plan_id == first.plan_id

    model = ScriptedModel(create_script())
    second = chat(model, session_id=first.session_id, plan_id=first.plan_id)  # 빈 일정은 새 일정 모드다
    assert "create_plan" in model.tool_names
    assert second.plan_id == first.plan_id and len(api_storage.get_plan(first.plan_id).stops) == 4


# ---- 기존 일정 수정 ----


def test_edit_replaces_only_the_changed_stop_and_saves_it(chat, api_storage):
    original = sample(api_storage)
    session_id = linked_session(api_storage)
    model = ScriptedModel(edit_script(
        ("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"}),
        text="[place:jagalchi-market] stays; [place:haeundae-beach] is replaced by [place:gwangalli-beach].",
    ))

    response = chat(model, session_id=session_id, plan_id=PLAN_ID)

    saved = api_storage.get_plan(PLAN_ID)
    assert [s.place_id for s in saved.stops] == ["gamcheon-village", "jagalchi-market", "busan-tower", "gwangalli-beach"]
    assert saved.stops[3].start == original.stops[3].start  # 시간은 그대로
    (change,) = response.plan_changes
    assert change == StopChange(stop_id="s4", before=original.stops[3], after=saved.stops[3])
    assert (response.session_id, response.plan_id) == (session_id, PLAN_ID)
    assert [(s.tool, s.id) for s in response.sources] == [("search_places", "gwangalli-beach")]
    assert "Gwangalli" in response.answer and "[place:" not in response.answer


def test_each_request_saves_at_most_once_so_it_never_doubles_up_with_put(chat, api_storage, monkeypatch):
    writes = Counter()
    for name in ("create_plan", "update_plan", "link_plan"):
        original = getattr(api_storage, name)
        monkeypatch.setattr(api_storage, name, lambda *a, _name=name, _fn=original, **k: (writes.update([_name]), _fn(*a, **k))[1])
    session_id = linked_session(api_storage)  # 이 호출의 link_plan 은 세지 않는다
    writes.clear()

    chat(ScriptedModel(edit_script(  # 두 곳을 바꿔도 저장은 한 번
        ("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"}),
        ("move_stop", {"stop_id": "s1", "start": "2026-11-21T09:00:00+09:00", "end": "2026-11-21T10:30:00+09:00"}),
        text="[place:gwangalli-beach] and [place:gamcheon-village] changed.",
    )), session_id=session_id, plan_id=PLAN_ID)
    assert writes == {"update_plan": 1}

    writes.clear()
    chat(ScriptedModel([text_turn("Nothing to change.")]), session_id=session_id, plan_id=PLAN_ID)  # 바꾼 것이 없으면 저장하지 않는다
    assert writes == {}

    writes.clear()
    chat(ScriptedModel(create_script()))  # 새 일정: 만들어 저장하고 세션에 연결한다. 수정(update)은 없다
    assert writes == {"create_plan": 1, "link_plan": 1}


def test_locked_stop_cannot_be_changed(chat, api_storage):
    original = sample(api_storage)
    model = ScriptedModel(edit_script(
        ("replace_stop", {"stop_id": "s2", "new_place_id": "gwangalli-beach"}),
        ("remove_stop", {"stop_id": "s2"}),
        ("move_stop", {"stop_id": "s2", "start": "2026-11-21T09:00:00+09:00", "end": "2026-11-21T10:00:00+09:00"}),
        text="[place:jagalchi-market] is locked, so unlock it in the app first.",
    ))

    response = chat(model, session_id=linked_session(api_storage), plan_id=PLAN_ID)

    assert sum("stop_locked" in text for _, text in model.tool_results()) == 3
    assert response.plan_changes == [] and api_storage.get_plan(PLAN_ID) == original


def test_unknown_or_unsearched_place_ids_are_rejected_when_editing(chat, api_storage):
    original = sample(api_storage)
    model = ScriptedModel(edit_script(
        ("replace_stop", {"stop_id": "s4", "new_place_id": "no-such-place"}),
        ("replace_stop", {"stop_id": "s4", "new_place_id": "taejongdae"}),  # places.json 에는 있지만 이번 요청에서 검색하지 않았다
        text="I could not change it.",
    ))

    response = chat(model, session_id=linked_session(api_storage), plan_id=PLAN_ID)

    texts = " ".join(text for _, text in model.tool_results())
    assert "unknown_place" in texts and "place_not_searched" in texts
    assert response.plan_changes == [] and api_storage.get_plan(PLAN_ID) == original


def test_edit_that_would_overlap_is_not_saved_and_the_user_is_told(chat, api_storage):
    original = sample(api_storage)
    model = ScriptedModel(edit_script(
        ("move_stop", {"stop_id": "s3", "start": "2026-11-21T12:30:00+09:00", "end": "2026-11-21T13:30:00+09:00"}),  # 고정 s2 와 겹침
        text="Moved it!",
    ))

    response = chat(model, language="ja", session_id=linked_session(api_storage, "ja"), plan_id=PLAN_ID)

    assert response.answer == message("plan_invalid", "ja") and response.plan_changes == []
    assert api_storage.get_plan(PLAN_ID) == original


def test_several_edits_to_one_stop_are_merged_into_one_change(chat, api_storage):
    original = sample(api_storage)
    model = ScriptedModel(edit_script(
        ("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"}),
        ("move_stop", {"stop_id": "s4", "start": "2026-11-21T16:00:00+09:00", "end": "2026-11-21T17:30:00+09:00"}),
        text="[place:gwangalli-beach] later in the day.",
    ))

    response = chat(model, session_id=linked_session(api_storage), plan_id=PLAN_ID)

    (change,) = response.plan_changes
    assert change.before == original.stops[3] and change.after == api_storage.get_plan(PLAN_ID).stops[3]


# ---- 세션과 접근 제어 ----


def test_unknown_session_id_gets_a_new_session(chat, api_storage):
    response = chat(ScriptedModel([text_turn("hi")]), session_id="sess-from-the-client")
    assert response.session_id != "sess-from-the-client" and api_storage.get_session(response.session_id)


def test_existing_session_is_reused(chat, api_storage):
    first = chat(ScriptedModel([text_turn("hi")]))
    assert chat(ScriptedModel([text_turn("hi")]), session_id=first.session_id).session_id == first.session_id


def test_a_session_cannot_use_another_sessions_plan(chat, api_storage):
    mine = chat(ScriptedModel(create_script()))
    model = ScriptedModel([text_turn("hi")])

    with pytest.raises(storage.PlanAccessDeniedError):
        chat(model, plan_id=mine.plan_id)  # 새 세션으로 남의 plan_id 를 보냄
    with pytest.raises(storage.PlanAccessDeniedError):
        chat(model, session_id=chat(ScriptedModel([text_turn("hi")])).session_id, plan_id=mine.plan_id)
    assert model.requests == []  # 모델을 부르기 전에 막는다


def test_missing_plan_is_plan_not_found_before_the_model_runs(chat):
    model = ScriptedModel([text_turn("hi")])
    with pytest.raises(storage.PlanNotFoundError):
        chat(model, plan_id="plan-none")
    assert model.requests == []


def test_mock_mode_lets_any_session_use_the_shared_demo_plan_but_the_real_store_does_not(chat, api_storage, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    response = chat(ScriptedModel([text_turn("hi")]), plan_id=PLAN_ID)
    assert response.plan_id == PLAN_ID and api_storage.get_session(response.session_id).plan_id == PLAN_ID

    monkeypatch.setattr(config, "USE_MOCK", False)
    with pytest.raises(storage.PlanAccessDeniedError):
        chat(ScriptedModel([text_turn("hi")]), plan_id=PLAN_ID)


# ---- 도구 호출 횟수·한도 ----


def test_tool_calls_are_limited_to_five_and_the_model_still_answers(chat):
    searches = [tool_turn(("search_places", {"query": q})) for q in ("a", "b", "c", "d", "e", "f", "g")]  # 7번 부르려 한다
    model = ScriptedModel([*searches, text_turn("Here is what I found.")])

    response = chat(model)

    statuses = Counter(status for status, _ in model.tool_results())
    assert statuses == {"success": 5, "error": 2}  # 5회까지만 실행하고 나머지는 막았다
    assert any("limit" in text for _, text in model.tool_results())
    assert response.answer == "Here is what I found."


def test_a_model_that_never_stops_calling_tools_gets_a_fallback_answer(chat, api_storage):
    model = ScriptedModel([tool_turn(("search_places", {"query": "a"}))], repeat_last=True)

    response = chat(model)

    assert len(model.requests) == agent.MAX_TURNS  # 반복 상한에서 멈춘다
    assert response.answer == message("incomplete", "en") and response.plan_changes == []
    assert api_storage.get_plan(response.plan_id).stops == []


def test_when_the_limit_stops_the_model_after_a_plan_was_made_the_plan_is_still_returned(chat, api_storage):
    model = ScriptedModel([*create_script(IDS, "unused", date="2026-11-28")[:2], tool_turn(("search_places", {"query": "z"}))],
                          repeat_last=True)

    response = chat(model)

    stored = api_storage.get_plan(response.plan_id)
    names = ", ".join(place_name(load_places()[s.place_id], "en") for s in stored.stops)
    assert response.answer == message("plan_created", "en", count=4, date="2026-11-28", places=names)
    assert len(response.plan_changes) == 4


# ---- 도구 실패 ----


def failing_search(result):
    @tool
    def search_places(query: str, category: str | None = None, indoor: bool | None = None) -> dict:
        """Search places (test double)."""
        return result()

    return search_places


@pytest.mark.parametrize("fail", [lambda: {"error": {"code": "data_unavailable", "message": "down"}}, lambda: 1 / 0])
def test_a_failing_tool_does_not_end_the_conversation(chat, api_storage, monkeypatch, caplog, fail):
    monkeypatch.setattr(agent, "LOOKUP_TOOLS", [failing_search(fail), *[t for t in chat_tools.LOOKUP_TOOLS if t.tool_name != "search_places"]])
    model = ScriptedModel([tool_turn(("search_places", {"query": ""})), text_turn("I could not look up places right now.")])

    with caplog.at_level(logging.INFO, logger="app.agent"):
        response = chat(model)

    assert response.answer == "I could not look up places right now."
    assert response.sources == [] and response.plan_changes == []
    assert model.tool_results()[0][1].strip() != ""  # 모델은 실패 결과를 받았다
    assert any("실패={'search_places': 1}" in r.getMessage() for r in caplog.records)  # 실패한 호출로 센다


def test_failed_tool_results_are_never_sources(chat, monkeypatch):
    @tool
    def get_crowd(place_id: str, date: str) -> dict:
        """Crowd lookup (test double that fails but still echoes the ids)."""
        return {"error": {"code": "upstream_error", "message": "down"}, "place_id": place_id, "date": date, "ratio": None}

    others = [t for t in chat_tools.LOOKUP_TOOLS if t.tool_name != "get_crowd"]
    monkeypatch.setattr(agent, "LOOKUP_TOOLS", [get_crowd, *others])
    model = ScriptedModel([tool_turn(("get_crowd", {"place_id": "haeundae-beach", "date": "2026-11-28"})), text_turn("I could not check.")])

    assert chat(model).sources == []  # 실패한 도구 호출은 sources 에 넣지 않는다 (요구사항 4.7)


def test_a_generated_plan_that_fails_the_final_check_is_not_saved(chat, api_storage, monkeypatch):
    def overlapping(place_ids, date, start, profile, plan_id=None):
        plan = build_plan(place_ids, date, start, profile, plan_id=plan_id)
        stops = [plan.stops[0], plan.stops[1].model_copy(update={"start": plan.stops[0].start})]  # 첫 두 Stop 의 시작이 같다
        return plan.model_copy(update={"stops": [*stops, *plan.stops[2:]]})

    monkeypatch.setattr(chat_tools, "build_plan", overlapping)
    monkeypatch.setattr(chat_tools, "validate_plan", lambda plan, original=None: [])  # 도구 안의 검사를 건너뛰고 run_chat 의 최종 검사만 본다

    response = chat(ScriptedModel(create_script(text="Your plan is ready!")))

    assert response.answer == message("plan_invalid", "en") and response.plan_changes == []
    assert api_storage.get_plan(response.plan_id).stops == []


# ---- 답변 검증 ----


def test_answer_with_a_place_that_has_no_grounds_is_rejected_and_nothing_is_saved(chat, api_storage):
    original = sample(api_storage)
    model = ScriptedModel(edit_script(
        ("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"}),
        text="Also try [place:taejongdae].",  # places.json 에는 있지만 이번 요청의 근거가 아니다
    ))

    with pytest.raises(agent.ChatError) as error:
        chat(model, session_id=linked_session(api_storage), plan_id=PLAN_ID)

    assert error.value.code == "invalid_model_output"
    assert api_storage.get_plan(PLAN_ID) == original  # 앞서 바꾼 내용도 저장하지 않는다


@pytest.mark.parametrize("text", ["Also try [place:made-up-place].", "Also try Taejongdae."])
def test_invented_or_ungrounded_places_in_the_answer_are_rejected(chat, text):
    model = ScriptedModel([tool_turn(("search_places", {"query": "haeundae"})), text_turn(text)])
    with pytest.raises(agent.ChatError) as error:
        chat(model)
    assert error.value.code == "invalid_model_output"


# ---- 모델 오류와 시간 제한 ----


def test_model_errors_become_chat_errors_without_leaking_the_request(chat, caplog):
    model = ScriptedModel(error=RuntimeError("upstream said: SECRET-USER-TEXT"))
    with caplog.at_level(logging.ERROR, logger="app.agent"):
        with pytest.raises(agent.ChatError) as error:
            chat(model, message="SECRET-USER-TEXT")
    assert error.value.code == "model_error"
    assert "SECRET-USER-TEXT" not in caplog.text and "RuntimeError" in caplog.text


def test_slow_model_hits_the_time_limit(chat, monkeypatch):
    monkeypatch.setattr(agent, "CHAT_TIMEOUT_SEC", 0.2)
    with pytest.raises(agent.ChatError) as error:
        chat(ScriptedModel([text_turn("too late")], delay=0.6))
    assert error.value.code == "timeout"


# ---- 로그 ----


def test_one_korean_log_line_with_tool_counts_and_no_user_content(chat, caplog):
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "haeundae"})), tool_turn(("get_crowd", {"place_id": "haeundae-beach", "date": "2026-11-28"})),
        text_turn("[place:haeundae-beach] is quiet."),
    ])
    with caplog.at_level(logging.INFO, logger="app.agent"):
        chat(model, message="SECRET-USER-TEXT", demo=NOW_1128)

    lines = [r.getMessage() for r in caplog.records if "대화 처리 종료" in r.getMessage()]
    assert len(lines) == 1 and "'search_places': 1" in lines[0] and "'get_crowd': 1" in lines[0]
    assert "SECRET-USER-TEXT" not in caplog.text
