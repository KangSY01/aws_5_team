"""search_places 결과의 순위 반영 (app/chat/ranking.py, D 의 rank_places 연결). AWS·Bedrock 없이 돈다.

- 정상: 상위 5곳이 순위대로 앞에 오고 ranking(total·breakdown·notes)이 붙는다. 다른 장소는 빠지지 않는다.
- 빈 결과·예외: 검색 결과를 바꾸지 않는다 (기존 방식).
- 장소 ID 검증·ChatResponse 형식·데모 캐시는 그대로다.
"""

import datetime as dt
import json
import logging

import pytest

from app import agent, config
from app.chat import ranking
from app.chat.plan_rules import load_places
from app.models.api import ChatRequest, ChatResponse
from app.models.plan import Profile
from app.ranking import rank_places
from app.tools.lookup import search_places
from chat_stubs import ScriptedModel, text_turn, tool_turn

PROFILE = Profile(language="ja", interests=["sea", "food"])
DAY = dt.date(2026, 11, 28)  # 데모일 (해운대 빛축제 개막일)
NOW_1128 = {"now": "2026-11-28T09:00:00+09:00"}
FIELDS = set(ChatResponse.model_fields)  # v0.3: score_breakdown 포함
V02_FIELDS = FIELDS - {"score_breakdown"}  # 랭킹을 쓰지 않은 응답 (FAKE_LLM·데모 캐시) 은 v0.2 와 같은 키


@pytest.fixture
def chat(monkeypatch):
    """실제 모델 경로를 스텁 모델로 돌린다."""
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def run(model, message="Plan a day by the sea", language="ja", demo=NOW_1128, **ids) -> ChatResponse:
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=message, profile={"language": language, "interests": ["sea", "food"]},
                                          demo=demo, **ids))

    return run


# ---- rank_search_results ----


def test_ranked_places_come_first_with_scores_and_nothing_is_dropped():
    results = search_places(query="")

    ranked = ranking.rank_search_results(results, PROFILE, DAY)

    assert sorted(p["place_id"] for p in ranked) == sorted(p["place_id"] for p in results)  # 빠지는 장소가 없다
    top = [p for p in ranked if "ranking" in p]
    assert len(top) == ranking.RANK_LIMIT and ranked[:len(top)] == top  # 순위가 붙은 장소가 앞에 있다
    assert [p["ranking"]["rank"] for p in top] == [1, 2, 3, 4, 5]
    totals = [p["ranking"]["total"] for p in top]
    assert totals == sorted(totals, reverse=True)
    for item in top:
        assert set(item["ranking"]) == {"rank", "total", "breakdown", "notes", "about"}
        assert {k: v for k, v in item.items() if k != "ranking"} == next(r for r in results if r["place_id"] == item["place_id"])
    # 나머지는 원래 순서 그대로
    rest_ids = [p["place_id"] for p in ranked if "ranking" not in p]
    assert rest_ids == [p["place_id"] for p in results if p["place_id"] in set(rest_ids)]


def test_ranking_matches_rank_places_itself():
    results = search_places(query="")
    ids = [p["place_id"] for p in results]
    ctx = ranking.build_context(ranking._probe_plan(ids, PROFILE, DAY), lookups=ranking._lookups())

    expected = rank_places(ids, PROFILE, ctx, day=DAY, limit=5)
    ranked = ranking.rank_search_results(results, PROFILE, DAY)

    assert [(p["place_id"], p["ranking"]["total"], p["ranking"]["breakdown"], p["ranking"]["notes"])
            for p in ranked if "ranking" in p] == [(s.place_id, s.total, s.breakdown, s.notes) for s in expected]


def test_demo_day_crowding_lowers_haeundae():
    # 11/28 해운대는 집중률 + 행사일 가중으로 혼잡 high. 같은 바다 관심이어도 광안리가 앞선다 (Guardian 과 같은 판단)
    ranked = ranking.rank_search_results(search_places(query="beach"), PROFILE, DAY)
    order = [p["place_id"] for p in ranked if "ranking" in p]
    assert order.index("gwangalli-beach") < order.index("haeundae-beach")
    haeundae = next(p for p in ranked if p["place_id"] == "haeundae-beach")
    assert "crowd:high" in haeundae["ranking"]["notes"]


def test_unknown_or_bad_items_are_not_candidates():
    results = [{"place_id": "no-such-place"}, "junk", {"name": "x"}, *search_places(query="haeundae-beach")]
    ranked = ranking.rank_search_results(results, PROFILE, DAY)
    assert [p.get("place_id") for p in ranked if isinstance(p, dict) and "ranking" in p] == ["haeundae-beach"]
    assert ranking.rank_search_results({"error": {"code": "x"}}, PROFILE, DAY) is None
    assert ranking.rank_search_results([{"place_id": "no-such-place"}], PROFILE, DAY) is None


def test_scores_for_places_outside_the_candidates_are_ignored():
    class Fake:
        def __init__(self, pid):
            self.place_id, self.total, self.breakdown, self.notes = pid, 99.0, {}, []

    results = search_places(query="haeundae-beach")
    assert ranking.rank_search_results(results, PROFILE, DAY, ranker=lambda *a, **k: [Fake("no-such-place")]) is None


@pytest.mark.parametrize("ranker", [lambda *a, **k: [], lambda *a, **k: None])
def test_empty_ranking_keeps_the_original_results(ranker):
    assert ranking.rank_search_results(search_places(query=""), PROFILE, DAY, ranker=ranker) is None


# ---- 에이전트 흐름 ----


def create_script(ids, text):
    return [
        tool_turn(("search_places", {"query": ""})),
        tool_turn(("create_plan", {"place_ids": ids, "date": "2026-11-28"})),
        text_turn(text),
    ]


def test_the_model_sees_the_ranking_and_the_plan_is_built_normally(chat, api_storage, caplog):
    ids = ["gwangalli-beach", "jagalchi-market", "gukje-market"]
    model = ScriptedModel(create_script(ids, "[place:gwangalli-beach] is less crowded today."))

    with caplog.at_level(logging.INFO, logger="app.chat.ranking"):
        response = chat(model)

    assert "장소 순위 반영: 상위 5곳" in caplog.text  # 배포 로그(CloudWatch)에서 찾는 문장

    status, text = model.tool_results()[0]  # 모델이 받은 search_places 결과
    seen = json.loads(text)
    assert status == "success" and "ranking" in seen[0] and seen[0]["ranking"]["rank"] == 1
    assert ranking.RANKING_NOTE in text and len(seen) == len(load_places())
    assert set(response.model_dump()) == FIELDS and "ranking" not in response.model_dump_json()  # 응답 형식 그대로
    stored = api_storage.get_plan(response.plan_id)
    assert sorted(s.place_id for s in stored.stops) == sorted(ids)  # build_plan 이 시각을 정했다
    assert [(s.tool, s.id) for s in response.sources if s.tool == "search_places"] == [
        ("search_places", pid) for pid in [p["place_id"] for p in seen] if pid in ids or pid == "gwangalli-beach"
    ][:len({*ids})]


def test_place_ids_are_still_validated(chat, api_storage):
    model = ScriptedModel(create_script(["no-such-place", "gwangalli-beach", "jagalchi-market"], "ok"))

    response = chat(model)

    assert "no-such-place" not in {s.place_id for s in api_storage.get_plan(response.plan_id).stops}


def test_a_failing_ranker_falls_back_to_the_original_search(chat, api_storage, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("ranking broke")

    monkeypatch.setattr(ranking, "rank_places", boom)
    monkeypatch.setattr(ranking.rank_search_results, "__defaults__", (None, boom, None))
    ids = ["gwangalli-beach", "jagalchi-market", "gukje-market"]
    model = ScriptedModel(create_script(ids, "[place:gwangalli-beach] it is."))

    with caplog.at_level(logging.WARNING, logger="app.chat.ranking"):
        response = chat(model)

    status, text = model.tool_results()[0]
    assert status == "success" and "ranking" not in text
    assert json.loads(text) == search_places(query="")  # B 의 결과 그대로
    assert "RuntimeError" in caplog.text and "ranking broke" not in caplog.text
    assert sorted(s.place_id for s in api_storage.get_plan(response.plan_id).stops) == sorted(ids)


def test_edit_mode_ranks_for_the_plan_date(chat, api_storage, monkeypatch):
    seen = []
    real = ranking.rank_search_results

    def spy(results, profile, day, demo_now=None, **kwargs):
        seen.append(day)
        return real(results, profile, day, demo_now, **kwargs)

    monkeypatch.setattr(ranking, "rank_search_results", spy)
    session = api_storage.create_session(Profile(language="ja"), plan_id="plan-1").session_id
    model = ScriptedModel([tool_turn(("search_places", {"query": "gwangalli"})), text_turn("Nothing changes.")])

    chat(model, session_id=session, plan_id="plan-1")

    assert seen == [api_storage.get_plan("plan-1").date]  # 샘플 일정의 방문일 (오늘이 아니라)


def test_place_ranker_is_registered_after_the_tool_recorder(chat, monkeypatch):
    captured = {}
    real_agent = agent.Agent

    def capture(*args, **kwargs):
        captured["hooks"] = kwargs.get("hooks")
        return real_agent(*args, **kwargs)

    monkeypatch.setattr(agent, "Agent", capture)
    chat(ScriptedModel([text_turn("ok")]))

    hooks = captured["hooks"]
    assert [type(h).__name__ for h in hooks] == ["ToolRecorder", "PlaceRanker"]  # AfterToolCallEvent 는 역순: 순위가 먼저


# ---- 데모 캐시·FAKE_LLM 은 순위를 거치지 않는다 ----


def test_demo_cache_response_is_unchanged(monkeypatch, api_storage):
    from app.chat import demo_cache

    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "DEMO_CACHE_ENABLED", True)
    monkeypatch.setattr(ranking, "rank_search_results", lambda *a, **k: pytest.fail("데모 캐시는 순위를 거치지 않는다"))
    response = agent.run_chat(ChatRequest(message=demo_cache.TRIGGER, profile={"language": "ja"}))
    assert [s.place_id for s in api_storage.get_plan(response.plan_id).stops] == [pid for _, pid, _, _ in demo_cache.STOPS]


def test_fake_llm_is_unchanged(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    monkeypatch.setattr(ranking, "rank_search_results", lambda *a, **k: pytest.fail("FAKE_LLM 은 순위를 거치지 않는다"))
    response = agent.run_chat(ChatRequest(message="hi", profile={"language": "en"}))
    assert set(response.model_dump()) == V02_FIELDS  # 고정 응답에는 score_breakdown 이 없다 (계약 v0.3)
