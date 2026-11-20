"""POST /chat 응답의 score_breakdown (계약 v0.3). AWS·Bedrock 없이 돈다.

- PlaceRanker 가 search_places 결과에 매긴 점수를 그대로 옮긴다. rank_places 를 다시 부르지 않는다.
- 순서는 점수 높은 순, 항목은 계약 필드(place_id, total, breakdown, notes)만.
- 랭킹을 안 했거나(검색 없음·FAKE_LLM·데모 캐시) 실패·빈 결과면 키가 없다 (v0.2 와 같은 응답).
"""

import json

import pytest

from app import agent, config
from app.chat import demo_cache, ranking
from app.handler import handler
from app.models.api import ChatRequest, PlaceScoreBreakdown
from app.models.plan import Profile
from chat_stubs import ScriptedModel, text_turn, tool_turn
from scripts.local_invoke import make_event

NOW_1128 = {"now": "2026-11-28T09:00:00+09:00"}
KEYS = {"place_id", "total", "breakdown", "notes"}
IDS = ["gwangalli-beach", "jagalchi-market", "gukje-market"]


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def run(model, message="Plan a day by the sea", language="ja", **ids):
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=message, profile={"language": language, "interests": ["sea", "food"]},
                                          demo=NOW_1128, **ids))

    return run


def create_script(query="", text="[place:gwangalli-beach] is less crowded."):
    return [
        tool_turn(("search_places", {"query": query})),
        tool_turn(("create_plan", {"place_ids": IDS, "date": "2026-11-28"})),
        text_turn(text),
    ]


def ranked_in_tool_result(model, index=0) -> list[dict]:
    """모델이 받은 search_places 결과에 붙은 순위 (PlaceRanker 가 계산한 값)."""
    _, text = model.tool_results()[index]
    return [{"place_id": p["place_id"], **{k: p["ranking"][k] for k in ("total", "breakdown", "notes")}}
            for p in json.loads(text) if "ranking" in p]


# ---- 정상 ----


def test_scores_shown_to_the_model_become_score_breakdown(chat):
    model = ScriptedModel(create_script())

    response = chat(model)

    shown = ranked_in_tool_result(model)
    assert shown and [s.model_dump() for s in response.score_breakdown] == shown  # 같은 값, 같은 순서
    totals = [s.total for s in response.score_breakdown]
    assert totals == sorted(totals, reverse=True)
    data = json.loads(response.model_dump_json())
    assert all(set(item) == KEYS for item in data["score_breakdown"])  # 계약 필드만
    assert all(PlaceScoreBreakdown.model_validate(item) for item in data["score_breakdown"])


def test_rank_places_is_not_called_again_for_the_response(chat, monkeypatch):
    calls = []
    real = ranking.rank_places

    def counting(*args, **kwargs):
        calls.append(args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(ranking.rank_search_results, "__defaults__", (None, counting, None))
    model = ScriptedModel(create_script())

    response = chat(model)

    assert len(calls) == 1 and response.score_breakdown  # search_places 한 번에 한 번만


def test_scores_from_several_searches_are_merged_and_sorted(chat):
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "beach"})),
        tool_turn(("search_places", {"query": "market"})),
        tool_turn(("create_plan", {"place_ids": IDS, "date": "2026-11-28"})),
        text_turn("ok"),
    ])

    response = chat(model)

    expected = {s["place_id"]: s for s in ranked_in_tool_result(model, 0) + ranked_in_tool_result(model, 1)}
    got = [s.model_dump() for s in response.score_breakdown]
    assert {s["place_id"] for s in got} == set(expected) and len(got) == len(expected)  # 같은 장소는 한 번
    assert got == sorted(expected.values(), key=lambda s: (-s["total"], s["place_id"]))


def test_edit_mode_scores_use_the_plan_date(chat, api_storage):
    session = api_storage.create_session(Profile(language="ja"), plan_id="plan-1").session_id
    model = ScriptedModel([tool_turn(("search_places", {"query": "beach"})), text_turn("Nothing changes.")])

    response = chat(model, session_id=session, plan_id="plan-1")

    assert [s.model_dump() for s in response.score_breakdown] == ranked_in_tool_result(model)


def test_score_breakdown_reaches_the_api_json(monkeypatch, api_storage):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    model = ScriptedModel(create_script())
    monkeypatch.setattr(agent, "get_model", lambda: model)
    body = json.dumps({"message": "Plan a day", "profile": {"language": "en", "interests": ["sea"]}, "demo": NOW_1128})

    result = handler(make_event("POST", "/chat", body))

    payload = json.loads(result["body"])
    assert result["statusCode"] == 200 and payload["score_breakdown"][0]["place_id"]
    assert all(set(item) == KEYS for item in payload["score_breakdown"])


# ---- 생략 (fallback) ----


def assert_omitted(response):
    assert response.score_breakdown == []
    assert "score_breakdown" not in json.loads(response.model_dump_json())  # v0.2 와 같은 키


def test_no_search_means_no_score_breakdown(chat):
    response = chat(ScriptedModel([tool_turn(("get_weather", {"date": "2026-11-28"})), text_turn("No rain.")]))
    assert_omitted(response)


def test_failing_ranker_means_no_score_breakdown(chat, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("ranking broke")

    monkeypatch.setattr(ranking.rank_search_results, "__defaults__", (None, boom, None))

    response = chat(ScriptedModel(create_script()))

    assert_omitted(response)
    assert response.plan_changes  # 일정 생성은 그대로 된다


@pytest.mark.parametrize("ranker", [lambda *a, **k: [], lambda *a, **k: None])
def test_empty_ranking_means_no_score_breakdown(chat, monkeypatch, ranker):
    monkeypatch.setattr(ranking.rank_search_results, "__defaults__", (None, ranker, None))
    assert_omitted(chat(ScriptedModel(create_script())))


def test_search_with_no_known_places_means_no_score_breakdown(chat):
    response = chat(ScriptedModel([tool_turn(("search_places", {"query": "zzz-no-match"})), text_turn("None found.")]))
    assert_omitted(response)


def test_fake_llm_and_demo_cache_have_no_score_breakdown(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    assert_omitted(agent.run_chat(ChatRequest(message="hi", profile={"language": "en"})))

    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    assert_omitted(agent.run_chat(ChatRequest(message=demo_cache.TRIGGER, profile={"language": "ja"})))


def test_model_error_still_raises_without_partial_scores(chat):
    model = ScriptedModel([tool_turn(("search_places", {"query": ""})), text_turn("Try [place:no-such-place].")])
    with pytest.raises(agent.ChatError):
        chat(model)
