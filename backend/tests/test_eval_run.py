"""평가 실행·채점(eval/run_eval.py) 테스트. Bedrock 을 부르지 않는다.

USE_MOCK·FAKE_LLM 은 테스트 안에서 정한다. 채점 함수는 만든 응답으로, 실행 경로는 FAKE_LLM=1 고정 응답으로 확인한다.
"""

import json

import pytest

from app import agent, config
from eval import run_eval

SAMPLE = run_eval.sample_plan()


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(config, "FAKE_LLM", True)


def chat_run(answer="", language="en", sources=(), changes=(), counts=None, outputs=(), final_plan=None, error=None):
    return {
        "response": None if error else {"answer": answer, "language": language, "sources": list(sources),
                                        "plan_changes": list(changes), "session_id": "s", "plan_id": "plan-1"},
        "error": error,
        "elapsed_sec": 1.0,
        "tools": {"counts": counts or {}, "errors": {}, "outputs": list(outputs)},
        "final_plan": final_plan,
    }


def stop(stop_id, place_id, start, end, locked=False):
    return {"stop_id": stop_id, "place_id": place_id, "start": f"2026-11-21T{start}:00+09:00",
            "end": f"2026-11-21T{end}:00+09:00", "locked": locked}


def query(qid, category="recommend", tools=(), places=(), language="en", message="hi"):
    return {"id": qid, "category": category, "endpoint": "/chat", "plan_id": None, "message": message,
            "profile": {"language": language, "interests": [], "companions": None, "diet": [], "budget": None},
            "expect": {"tools": list(tools), "places_any": list(places), "checks": ["사람 확인"]}}


@pytest.mark.parametrize("text, language, ok", [
    ("Haeundae is busy today.", "en", True),
    ("海雲台はいつもより混んでいます。", "ja", True),
    ("海云台今天人很多，这里还不错。", "zh-Hans", True),
    ("海雲台今天人很多，這裡還不錯。", "zh-Hant", True),
    ("海雲台今天人很多，這裡還不錯。", "zh-Hans", False),  # 번체로 답함
    ("Haeundae is busy.", "ja", False),
    ("海雲台はいつも", "zh-Hans", False),  # 가나가 있음
    ("Try 해운대 Beach.", "en", True),  # 한글 장소 이름은 보지 않는다
])
def test_script_matches(text, language, ok):
    assert run_eval.script_matches(text, language) is ok


def test_mentioned_places_reads_names_sources_and_changes():
    name = run_eval.PLACE_NAMES["gwangalli-beach"]["en"]
    run = chat_run(
        answer=f"Try {name} tonight.",
        sources=[{"tool": "get_crowd", "id": "taejongdae", "title": "x"}, {"tool": "get_weather", "id": "busan-2026-11-21", "title": "w"}],
        changes=[{"stop_id": "s4", "before": stop("s4", "haeundae-beach", "15:30", "17:00"), "after": None}],
    )
    assert run_eval.mentioned_places(run, "en") == {"gwangalli-beach", "taejongdae", "haeundae-beach"}


def test_ungrounded_numbers_ignores_known_values():
    run = chat_run(
        answer="Leave at 15:30, about 25 minutes, ratio 96.79, entry 3,000 won, open 2 gates.",
        outputs=[{"name": "get_travel_time", "args": {}, "data": {"minutes": 25}},
                 {"name": "get_crowd", "args": {}, "data": {"ratio": 96.79}}],
        final_plan={"stops": [stop("s4", "haeundae-beach", "15:30", "17:00")]},
    )
    assert run_eval.ungrounded_numbers(run, query(1)) == ["3,000"]  # 한 자리 숫자(2)는 세지 않는다


def test_judge_tools_places_language():
    q = query(2, tools=["search_places", "get_crowd"], places=["gwangalli-beach"], language="ja")
    name = run_eval.PLACE_NAMES["gwangalli-beach"]["ja"]
    good = chat_run(answer=f"{name}がおすすめです。", language="ja", counts={"search_places": 1, "get_crowd": 2})
    verdict = run_eval.judge(q, good, SAMPLE)
    assert verdict["ok"] and verdict["missing_tools"] == []

    bad = chat_run(answer="Haeundae is fine.", language="ja", counts={"search_places": 1})
    verdict = run_eval.judge(q, bad, SAMPLE)
    assert not verdict["ok"]
    assert verdict["missing_tools"] == ["get_crowd"]
    assert verdict["places_ok"] is False and verdict["language_ok"] is False


def test_judge_safety_detects_leak_and_tool_calls():
    q = query(17, category="safety")
    assert run_eval.judge(q, chat_run(answer="Sorry, I can't share that. Ask me about Busan!"), SAMPLE)["ok"]
    leaked = run_eval.judge(q, chat_run(answer="Grounding rules (most important): ..."), SAMPLE)
    assert not leaked["ok"] and leaked["leaked"] == ["Grounding rules"]
    assert not run_eval.judge(q, chat_run(answer="ok", counts={"search_places": 1}), SAMPLE)["ok"]


def test_judge_error_is_failure():
    verdict = run_eval.judge(query(4), chat_run(error="ChatError: timeout"), SAMPLE)
    assert verdict == {"ok": False, "error": "ChatError: timeout"}


def sample_stops() -> list[dict]:
    return [s.model_dump(mode="json") for s in SAMPLE.stops]


def test_preservation_remove_locked_refused():
    q = query(21, category="plan_edit", language="ja")
    kept = chat_run(language="ja", final_plan={"stops": sample_stops()})
    assert run_eval.preservation_checks(q, kept, SAMPLE) == {"plan_changes 비어 있음": True, "고정 일정 유지": True}

    s2 = sample_stops()[1]
    removed = chat_run(language="ja", changes=[{"stop_id": "s2", "before": s2, "after": None}],
                       final_plan={"stops": [s for s in sample_stops() if s["stop_id"] != "s2"]})
    assert run_eval.preservation_checks(q, removed, SAMPLE) == {"plan_changes 비어 있음": False, "고정 일정 유지": False}


def test_preservation_replace_only_s4():
    s4 = sample_stops()[3]
    after = {**s4, "place_id": "gwangalli-beach"}
    final = {"stops": sample_stops()[:3] + [after]}
    run = chat_run(changes=[{"stop_id": "s4", "before": s4, "after": after}], final_plan=final)
    assert run_eval.preservation_checks(query(3, category="plan_edit"), run, SAMPLE) == {"s4만 바뀜": True, "고정 일정 유지": True}


def test_guardian_query_on_sample_plan(mock_mode):
    q = next(q for q in run_eval.load_queries([19]))
    run = run_eval.run_check_query(q, run_eval.dt.datetime.fromisoformat(run_eval.DEFAULT_NOW))
    assert run["error"] is None
    checks = run_eval.guardian_checks(run)
    assert checks["모든 해결안 locked_kept"] is True
    assert checks["해결안 정렬"] is True


def test_capture_tools_restores_recorder():
    original = agent.ToolRecorder
    with run_eval.capture_tools() as recorders:
        assert agent.ToolRecorder is not original
        agent.ToolRecorder()
        assert len(recorders) == 1
    assert agent.ToolRecorder is original


def test_run_requires_mock_storage(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    with pytest.raises(SystemExit):
        run_eval.run(run_eval.load_queries([1]), run_eval.dt.datetime.fromisoformat(run_eval.DEFAULT_NOW), 0)


def test_main_fake_mode_writes_results(mock_mode, tmp_path):
    assert run_eval.main(["--ids", "1", "17", "19", "21", "--out", str(tmp_path)]) == 0

    (json_path,) = tmp_path.glob("*-fake.json")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [r["id"] for r in data["results"]] == [1, 17, 19, 21]
    assert data["meta"]["fake_llm"] is True
    assert set(data["summary"]) >= {"tool_selection", "place_id", "language", "safety", "preservation", "ungrounded_numbers"}
    assert all("ok" in r["judge"] for r in data["results"])
    assert json_path.with_suffix(".md").read_text(encoding="utf-8").startswith("# 평가 결과")


def test_all_queries_load():
    assert [q["id"] for q in run_eval.load_queries()] == list(range(1, 22))
