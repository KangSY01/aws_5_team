"""평가 29 재현: 새 일정 요청에서 search_places 만 5번 부르고 create_plan 을 못 부른 문제. AWS·Bedrock 없이 돈다.

실제 실행(eval/results 20261120-193518, 194857)에서 모델은 query 에 따옴표 두 글자('""')를 넣고 category 를 바꿔
가며 검색했다. 따옴표를 장소 이름으로 찾으니 매번 0곳이었고, 5번째에 query="" 로 35곳을 받았지만 도구 한도 때문에
create_plan 을 부르지 못해 시간 초과·max_tokens 로 끝났다.

고친 것 (A 의 ToolRecorder, 도구 한도 5회는 그대로):
- search_places 의 따옴표·공백뿐인 query 는 빈 문자열로 바꿔 실행한다.
- create 모드에서 한도를 다 쓴 뒤에도 create_plan 은 한 번 허용한다 (찾아 둔 후보로만, 검증·build_plan 그대로).
"""

import pytest

from app import agent, config
from app.chat.plan_rules import load_places
from app.chat.tools import ToolRecorder
from app.models.api import ChatRequest
from app.models.plan import Profile
from app.tools.schedule import build_plan
from chat_stubs import ScriptedModel, text_turn, tool_turn

MESSAGE = "11月28日（星期六）我們一家人帶孩子去釜山，請安排適合孩子的一日行程。"  # 평가 29
PROFILE = {"language": "zh-Hant", "interests": ["kids", "nature"], "companions": "family_with_kids", "diet": [],
           "budget": "mid"}
NOW = {"now": "2026-11-21T09:00:00+09:00"}  # 평가 기본 기준 시각
QUOTED = '""'  # 모델이 실제로 넣은 값


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def run(model, **ids):
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=MESSAGE, profile=PROFILE, demo=NOW, **ids))

    return run


def searched(model) -> list[list[str]]:
    import json

    return [[p["place_id"] for p in json.loads(text)] for status, text in model.tool_results() if text.startswith("[")]


# ---- 원인: 따옴표 검색어 ----


def test_quoted_empty_query_finds_places_by_category(chat, api_storage):
    ids = ["sea-life-busan", "busan-citizens-park", "lotte-world-busan"]
    model = ScriptedModel([
        tool_turn(("search_places", {"query": QUOTED, "category": "aquarium"}),
                  ("search_places", {"query": QUOTED, "category": "park"}),
                  ("search_places", {"query": QUOTED, "category": "theme_park"})),
        tool_turn(("create_plan", {"place_ids": ids, "date": "2026-11-28"})),
        text_turn("[place:sea-life-busan] first."),
    ])

    response = chat(model)

    results = searched(model)
    assert [len(r) for r in results[:3]] == [1, 5, 1]  # 따옴표를 빼고 category 로 찾았다 (예전에는 모두 0곳)
    stored = api_storage.get_plan(response.plan_id)
    assert stored.stops and all(s.place_id in load_places() for s in stored.stops)
    assert [c.before for c in response.plan_changes] == [None] * len(stored.stops)


@pytest.mark.parametrize("query, expected", [
    ('""', ""), ("''", ""), (' " " ', ""), ("“”", ""), ("「」", ""),
    ("haeundae", "haeundae"), ('"haeundae"', '"haeundae"'), ("", ""),  # 실제 검색어는 건드리지 않는다
])
def test_only_quote_only_queries_are_cleared(query, expected):
    class Event:
        tool_use = {"name": "search_places", "toolUseId": "t1", "input": {"query": query, "category": "beach"}}
        cancel_tool = False

    event = Event()
    ToolRecorder()._before(event)

    assert event.tool_use["input"] == {"query": expected, "category": "beach"} and not event.cancel_tool


def test_other_tools_are_not_touched():
    class Event:
        tool_use = {"name": "get_crowd", "toolUseId": "t1", "input": {"place_id": '""', "date": "2026-11-28"}}
        cancel_tool = False

    event = Event()
    ToolRecorder()._before(event)
    assert event.tool_use["input"]["place_id"] == '""'


# ---- 안전장치: 검색으로 한도를 다 써도 create_plan 은 한 번 ----


def test_create_plan_still_runs_after_five_searches(chat, api_storage):
    ids = ["sea-life-busan", "busan-citizens-park", "lotte-world-busan"]
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "", "category": c}))
        for c in ("aquarium", "park", "theme_park", "beach", "museum")
    ] + [
        tool_turn(("create_plan", {"place_ids": ids, "date": "2026-11-28"})),
        text_turn("[place:sea-life-busan] first."),
    ])

    response = chat(model)

    stored = api_storage.get_plan(response.plan_id)
    # 시각은 B 의 build_plan 이 정한다 (모델이 아니다)
    assert stored == build_plan(ids, "2026-11-28", None, Profile.model_validate(PROFILE), plan_id=response.plan_id)
    assert len(response.plan_changes) == 3


def test_lookups_after_the_limit_are_still_blocked(chat, api_storage):
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "", "category": c}))
        for c in ("aquarium", "park", "theme_park", "beach", "museum", "temple")  # 6번째 검색
    ] + [text_turn("ok")])

    chat(model)

    statuses = [status for status, _ in model.tool_results()]
    assert statuses[:5] == ["success"] * 5 and statuses[5] == "error"  # 6번째 조회는 막는다


def test_finish_tool_is_allowed_only_once(chat, api_storage):
    ids = ["sea-life-busan", "busan-citizens-park", "lotte-world-busan"]
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "", "category": c}))
        for c in ("aquarium", "park", "theme_park", "beach", "museum")
    ] + [
        tool_turn(("create_plan", {"place_ids": ids, "date": "2026-11-28"})),
        tool_turn(("create_plan", {"place_ids": ids, "date": "2026-11-29"})),  # 두 번째는 막는다
        text_turn("ok"),
    ])

    response = chat(model)

    statuses = [status for status, _ in model.tool_results()]
    assert statuses[5] == "success" and statuses[6] == "error"
    assert api_storage.get_plan(response.plan_id).date.isoformat() == "2026-11-28"  # 첫 일정 그대로


def test_create_plan_after_the_limit_still_only_accepts_searched_places(chat, api_storage):
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "", "category": c}))
        for c in ("aquarium", "park", "theme_park", "beach", "museum")
    ] + [
        tool_turn(("create_plan", {"place_ids": ["jagalchi-market", "gukje-market", "busan-tower"], "date": "2026-11-28"})),
        text_turn("ok"),
    ])

    response = chat(model)

    _, text = model.tool_results()[5]
    assert "place_not_searched" in text  # 검색하지 않은 장소는 여전히 거부한다
    assert api_storage.get_plan(response.plan_id).stops == []


def test_edit_mode_has_no_extra_call(chat, api_storage):
    session = api_storage.create_session(Profile(language="zh-Hant"), plan_id="plan-1").session_id
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "", "category": c}))
        for c in ("aquarium", "park", "theme_park", "beach", "museum")
    ] + [
        tool_turn(("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"})),
        text_turn("ok"),
    ])

    response = chat(model, session_id=session, plan_id="plan-1")

    assert model.tool_results()[5][0] == "error" and response.plan_changes == []  # 수정 모드는 한도 그대로
