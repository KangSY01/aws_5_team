"""agent.py 작업 1: 모델 생성과 FAKE_LLM 고정 응답. AWS 자격 증명·네트워크 없이 돈다."""

import logging

import pytest

from app import agent, config
from app.models.api import ChatRequest, ChatResponse


def make_request(**kwargs) -> ChatRequest:
    return ChatRequest(message="hi", profile={"language": "en"}, **kwargs)


class FakeBedrockModel:
    """BedrockModel 대역. 실제 boto 클라이언트를 만들지 않고 받은 인자만 기록한다."""

    calls: list[dict] = []

    def __init__(self, **kwargs):
        type(self).calls.append(kwargs)


@pytest.fixture
def fake_bedrock(monkeypatch):
    FakeBedrockModel.calls = []
    monkeypatch.setattr(agent, "BedrockModel", FakeBedrockModel)
    return FakeBedrockModel


def test_fake_llm_does_not_build_model(monkeypatch, fake_bedrock):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    assert agent.build_model() is None
    agent.run_chat(make_request())
    assert fake_bedrock.calls == []


def test_fake_llm_response_is_valid_chat_response(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    response = agent.run_chat(make_request())
    # 직렬화 후 다시 검증해도 같아야 한다
    assert ChatResponse.model_validate_json(response.model_dump_json()) == response


def test_fake_llm_uses_request_ids_or_sample_ids(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    given = agent.run_chat(make_request(session_id="s-9", plan_id="plan-9"))
    assert (given.session_id, given.plan_id) == ("s-9", "plan-9")
    default = agent.run_chat(make_request())
    assert (default.session_id, default.plan_id) == ("sess-1", "plan-1")


def test_fake_llm_is_deterministic_and_not_shared(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    first = agent.run_chat(make_request())
    expected = first.model_dump()
    first.sources.clear()  # 호출자가 결과를 고쳐도
    first.plan_changes.clear()
    assert agent.run_chat(make_request()).model_dump() == expected


def test_build_model_passes_config(monkeypatch, fake_bedrock):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "BEDROCK_REGION", "ap-northeast-2")
    monkeypatch.setattr(config, "MODEL_ID", "test-model-id")

    assert isinstance(agent.build_model(), FakeBedrockModel)

    (kwargs,) = fake_bedrock.calls
    assert kwargs["model_id"] == "test-model-id"
    assert kwargs["region_name"] == "ap-northeast-2"
    assert kwargs["max_tokens"] == agent.MAX_TOKENS
    assert kwargs["streaming"] is True
    client_config = kwargs["boto_client_config"]
    assert client_config.connect_timeout == 5
    assert client_config.read_timeout == 5
    assert client_config.retries["max_attempts"] == 1  # 최초 호출을 뺀 재시도 1회


def test_build_model_rejects_other_region(monkeypatch, fake_bedrock, caplog):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    monkeypatch.setattr(config, "BEDROCK_REGION", "us-east-1")

    with caplog.at_level(logging.ERROR, logger=agent.logger.name):
        with pytest.raises(RuntimeError):
            agent.build_model()

    assert fake_bedrock.calls == []
    assert "리전" in caplog.text and "us-east-1" in caplog.text
