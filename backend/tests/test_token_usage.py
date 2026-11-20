"""Bedrock 토큰 사용량 로그 (app/chat/token_usage.py, agent._converse). AWS·Bedrock 없이 돈다.

스텁 모델이 ConverseStream 의 metadata.usage 이벤트를 내면 Strands 가 요청 하나 안의 모델 호출을 합산하고,
_converse 가 BEDROCK_TOKEN_USAGE 구조화 로그 한 줄을 남기는지 본다.
"""

import json
import logging

import pytest

from app import agent, config, storage
from app.chat import token_usage
from app.models.api import ChatRequest
from app.models.plan import Profile
from chat_stubs import ScriptedModel, text_turn, tool_turn

NOW = {"now": "2026-11-21T09:00:00+09:00"}
SECRET_MESSAGE = "my passport number is X1234567"  # 로그에 나오면 안 되는 사용자 메시지


def with_usage(turn: list[dict], input_tokens: int, output_tokens: int) -> list[dict]:
    """응답 끝에 ConverseStream metadata 이벤트(usage)를 붙인다."""
    usage = {"inputTokens": input_tokens, "outputTokens": output_tokens, "totalTokens": input_tokens + output_tokens}
    return [*turn, {"metadata": {"usage": usage, "metrics": {"latencyMs": 1}}}]


@pytest.fixture
def chat(monkeypatch, caplog):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    caplog.set_level(logging.INFO, logger=token_usage.__name__)

    def run(model, message=SECRET_MESSAGE, **ids):
        monkeypatch.setattr(agent, "get_model", lambda: model)
        return agent.run_chat(ChatRequest(message=message, profile={"language": "en"}, demo=NOW, **ids))

    return run


def usage_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == token_usage.EVENT]


def test_create_mode_sums_every_model_call_in_one_request(chat, caplog):
    model = ScriptedModel([
        with_usage(tool_turn(("search_places", {"query": "", "category": "beach"})), 1000, 50),
        with_usage(text_turn("I could not build a plan."), 1200, 30),
    ])

    chat(model)

    [record] = usage_records(caplog)
    payload = json.loads(record.getMessage())
    assert payload == {
        "event": "BEDROCK_TOKEN_USAGE", "operation": "plan_create", "input_tokens": 2200, "output_tokens": 80,
        "total_tokens": 2280, "bedrock_calls": 2, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0,
        "stop_reason": "end_turn",
    }
    assert record.total_tokens == 2280 and record.operation == "plan_create"  # CloudWatch JSON 최상위 키 (extra)


def test_edit_mode_is_logged_as_plan_edit(chat, caplog):
    model = ScriptedModel([with_usage(text_turn("Your plan stays the same."), 900, 20)])

    session = storage.create_session(Profile(language="en"), plan_id="plan-1")  # 샘플 일정이 연결된 세션

    chat(model, message="Is my plan ok?", session_id=session.session_id, plan_id="plan-1")

    [record] = usage_records(caplog)
    assert (record.operation, record.input_tokens, record.output_tokens, record.bedrock_calls) == ("plan_edit", 900, 20, 1)


def test_log_has_no_user_message_or_prompt(chat, caplog):
    chat(ScriptedModel([with_usage(text_turn("Hello."), 10, 2)]))

    [record] = usage_records(caplog)
    assert SECRET_MESSAGE not in record.getMessage()
    assert set(json.loads(record.getMessage())) == {
        "event", "operation", "input_tokens", "output_tokens", "total_tokens", "bedrock_calls",
        "cache_read_input_tokens", "cache_write_input_tokens", "stop_reason",
    }


def test_tokens_are_logged_even_when_the_model_fails(chat, caplog):
    with pytest.raises(agent.ChatError):
        chat(ScriptedModel(error=RuntimeError("boom")))

    [record] = usage_records(caplog)
    assert (record.total_tokens, record.stop_reason) == (0, "error")


def test_a_broken_metrics_object_does_not_break_the_chat(chat, caplog, monkeypatch):
    monkeypatch.setattr(agent, "usage_from_agent", lambda *a: token_usage.usage_from_agent(object(), 1))

    response = chat(ScriptedModel([text_turn("Hello.")]))

    assert response.answer == "Hello."
    assert usage_records(caplog) == []


def test_log_failure_is_swallowed(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(token_usage.logger, "info", broken)
    token_usage.log_usage("edit", token_usage.TokenUsage(1, 1, 2, 1), "end_turn")  # 예외가 나지 않아야 한다
