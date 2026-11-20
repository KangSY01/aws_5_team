"""채팅 일정 수정의 안정성: 출력 토큰 한도(max_tokens)와 대화 시간 한도(CHAT_TIMEOUT_SEC). AWS·Bedrock 없이 돈다.

평가 질의 11·20(지각 → move_stop 여러 개)은 1024 토큰에서 도구 입력 JSON 이 잘려 MaxTokensReachedException 이 났고,
질의 3(장소 교체)은 14초를 넘어 중단됐다. 여기서는 그 두 실패를 스텁 모델로 재현하고,
- 어느 경우든 저장된 일정이 바뀌지 않는지 (중간에 적용한 수정도 저장하지 않는다)
- edit 모드만 출력 상한이 큰 모델을 쓰는지
- 종료 로그에 모델·도구 시간이 남는지 (14초 초과 원인 구분용)
를 확인한다.
"""

import json
import logging

import pytest

from app import agent, config
from app.handler import handler
from app.models.api import ChatRequest
from app.models.plan import Profile
from chat_stubs import ScriptedModel, text_turn, tool_turn
from scripts.local_invoke import make_event

PLAN_ID = "plan-1"  # 샘플 일정: s1 감천 10:00 · s2 자갈치(고정) 12:00 · s3 부산타워 13:30 · s4 해운대 15:30
MOVE_S3 = ("move_stop", {"stop_id": "s3", "start": "2026-11-21T14:10:00+09:00", "end": "2026-11-21T15:10:00+09:00"})
MOVE_S4 = ("move_stop", {"stop_id": "s4", "start": "2026-11-21T16:10:00+09:00", "end": "2026-11-21T17:40:00+09:00"})


def truncated_tool_turn(name: str, partial_json: str) -> list[dict]:
    """도구 입력 JSON 을 쓰다가 출력 한도에서 끊긴 응답 (stopReason=max_tokens). Bedrock 이 실제로 보내는 모양이다."""
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "tool-cut", "name": name}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": partial_json}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "max_tokens"}},
    ]


@pytest.fixture
def edit_chat(monkeypatch, api_storage):
    """plan-1 에 연결된 세션으로 실제 모델 경로(스텁 모델)를 돌린다."""
    monkeypatch.setattr(config, "FAKE_LLM", False)
    session_id = api_storage.create_session(Profile(language="en"), plan_id=PLAN_ID).session_id

    def run(model, message="I'm 40 minutes late."):
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=message, profile={"language": "en"}, session_id=session_id,
                                          plan_id=PLAN_ID))

    return run, session_id


# ---- max_tokens: 질의 11·20 재현 ----


def test_cut_off_tool_input_is_a_chat_error_and_the_plan_is_untouched(edit_chat, api_storage, caplog):
    run, _ = edit_chat
    before = api_storage.get_plan(PLAN_ID)
    model = ScriptedModel([
        tool_turn(MOVE_S3),  # 첫 수정은 성공한다
        truncated_tool_turn("move_stop", '{"stop_id": "s4", "start": "2026-11-21T16:'),  # 두 번째 입력이 잘린다
    ])

    with caplog.at_level(logging.INFO, logger="app.agent"), pytest.raises(agent.ChatError) as error:
        run(model)

    assert error.value.code == "model_error"
    assert "MaxTokensReachedException" in caplog.text  # 원인은 로그에 예외 종류로 남는다
    assert api_storage.get_plan(PLAN_ID) == before  # 앞에서 옮긴 s3 도 저장하지 않는다


def test_cut_off_output_is_a_safe_500_through_the_api(edit_chat, api_storage):
    _, session_id = edit_chat
    before = api_storage.get_plan(PLAN_ID)
    model = ScriptedModel([truncated_tool_turn("move_stop", '{"stop_id": "s3", "start": "2026-')])
    agent_get_model = agent.get_model
    try:
        agent.get_model = lambda: model
        body = json.dumps({"session_id": session_id, "plan_id": PLAN_ID, "message": "I'm 40 minutes late.",
                           "profile": {"language": "en"}})
        result = handler(make_event("POST", "/chat", body))
    finally:
        agent.get_model = agent_get_model

    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {"error": {"code": "internal_error", "message": "서버 오류가 발생했습니다."}}
    assert api_storage.get_plan(PLAN_ID) == before


def test_several_moves_in_one_turn_still_work(edit_chat, api_storage):
    # 지각 응답의 정상 모양: 한 응답에서 비고정 Stop 두 개를 옮기고, 고정 일정(s2)은 그대로
    run, _ = edit_chat
    model = ScriptedModel([tool_turn(MOVE_S3, MOVE_S4), text_turn("Your locked lunch stays. I moved the later stops.")])

    response = run(model)

    assert [c.stop_id for c in response.plan_changes] == ["s3", "s4"]
    stored = {s.stop_id: s for s in api_storage.get_plan(PLAN_ID).stops}
    assert stored["s3"].start.isoformat() == MOVE_S3[1]["start"] and stored["s2"].locked


# ---- 시간 한도: 질의 3 재현 ----


def test_timeout_after_a_partial_edit_keeps_the_stored_plan(edit_chat, api_storage, monkeypatch, caplog):
    run, _ = edit_chat
    before = api_storage.get_plan(PLAN_ID)
    monkeypatch.setattr(agent, "CHAT_TIMEOUT_SEC", 0.5)
    # 모델 응답마다 0.3초: 검색·교체를 하는 사이에 한도를 넘는다 (실제로는 모델 응답 3~4번 × 몇 초)
    model = ScriptedModel([
        tool_turn(("search_places", {"query": "beach"})),
        tool_turn(("replace_stop", {"stop_id": "s4", "new_place_id": "gwangalli-beach"})),
        tool_turn(MOVE_S3),
        text_turn("done"),
    ], delay=0.3)

    with caplog.at_level(logging.INFO, logger="app.agent"), pytest.raises(agent.ChatError) as error:
        run(model, message="海云台人太多了，换一个类似的地方吧。")

    assert error.value.code == "timeout"
    assert api_storage.get_plan(PLAN_ID) == before  # 교체를 적용했어도 저장하지 않는다
    assert "초를 넘어 중단했습니다" in caplog.text  # agent._converse 의 시간 초과 로그
    summary = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("대화 처리 종료"))
    assert "모델 호출=" in summary and "도구 시간=" in summary  # 어디서 시간이 갔는지 남는다


def test_summary_log_separates_model_time_from_tool_time(edit_chat, caplog):
    run, _ = edit_chat
    model = ScriptedModel([tool_turn(MOVE_S3), text_turn("Moved.")], delay=0.05)

    with caplog.at_level(logging.INFO, logger="app.agent"):
        run(model)

    summary = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("대화 처리 종료"))
    assert "모델 호출=2회" in summary and "모델 시간=" in summary and "도구 시간=" in summary
    assert "모델 오류={}" in summary


def test_failed_model_calls_are_counted_by_type():
    from app.chat.tools import ToolRecorder

    class Throttled(Exception):
        pass

    class Event:
        exception = Throttled("slow down, request text here")

    recorder = ToolRecorder()
    recorder._before_model(object())
    recorder._after_model(Event())

    assert len(recorder.model_seconds) == 1 and dict(recorder.model_errors) == {"Throttled": 1}


# ---- edit 모드 출력 상한 ----


class FakeBedrockModel:
    built: list[int] = []

    def __init__(self, **kwargs):
        type(self).built.append(kwargs["max_tokens"])


@pytest.fixture
def fake_bedrock(monkeypatch):
    FakeBedrockModel.built = []
    monkeypatch.setattr(agent, "BedrockModel", FakeBedrockModel)
    monkeypatch.setattr(agent, "_model", None)
    monkeypatch.setattr(agent, "_edit_model", None)
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "BEDROCK_REGION", "ap-northeast-2")
    return FakeBedrockModel


class _Mode:
    def __init__(self, mode):
        self.mode = mode


def test_only_edit_mode_uses_the_larger_output_budget(fake_bedrock):
    base = agent.get_model()

    assert agent._model_for(_Mode("create"), base) is base
    edit = agent._model_for(_Mode("edit"), base)
    assert edit is not base and agent._model_for(_Mode("edit"), base) is edit  # 컨테이너당 한 번만 만든다
    assert fake_bedrock.built == [agent.MAX_TOKENS, agent.EDIT_MAX_TOKENS]
    assert (agent.MAX_TOKENS, agent.EDIT_MAX_TOKENS) == (1024, 2048)


def test_stub_models_and_fake_llm_are_not_replaced(fake_bedrock):
    stub = ScriptedModel([text_turn("ok")])
    assert agent._model_for(_Mode("edit"), stub) is stub
    assert agent._model_for(_Mode("edit"), None) is None  # FAKE_LLM 은 모델이 없다
    assert fake_bedrock.built == []


def test_chat_timeout_is_unchanged():
    assert agent.CHAT_TIMEOUT_SEC == 14  # 바꾸려면 먼저 보고한다 (Lambda 30초, 프론트 요청 시간)
