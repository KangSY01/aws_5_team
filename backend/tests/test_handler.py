"""handler 응답이 docs/api-contract.md 형식(Pydantic 모델)과 맞는지만 확인한다."""

import json

import pytest

from app import config
from app.handler import PLACES, SAMPLE_PLAN, handler
from app.models.api import ChatResponse, CheckResponse, ErrorResponse, PlanResponse
from scripts.local_invoke import make_event

PLAN_ID = SAMPLE_PLAN.plan_id
CHAT_BODY = json.dumps({"plan_id": PLAN_ID, "message": "hi", "profile": {"language": "en"}})


def call(method, path, body=None):
    result = handler(make_event(method, path, body))
    assert result["headers"]["content-type"].startswith("application/json")
    return result["statusCode"], result["body"]


def test_sample_data():
    assert len(PLACES) >= 8  # 공공데이터로 30곳 이상으로 늘렸다 (상한 없음)
    assert any(stop.locked for stop in SAMPLE_PLAN.stops)


def test_chat(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)  # 형식만 본다. 실제 대화 경로는 test_api_chat.py
    status, body = call("POST", "/chat", CHAT_BODY)
    assert status == 200
    ChatResponse.model_validate_json(body)


@pytest.mark.parametrize(
    "method, body", [("GET", None), ("PUT", SAMPLE_PLAN.model_dump_json())]
)
def test_plan(method, body):
    status, body = call(method, f"/plan/{PLAN_ID}", body)
    assert status == 200
    response = PlanResponse.model_validate_json(body)
    # 일정이 참조하는 장소가 빠짐없이 함께 온다
    assert {s.place_id for s in response.plan.stops} == {p.place_id for p in response.places}


def test_plan_check():
    status, body = call("POST", "/plan/check", json.dumps({"plan_id": PLAN_ID}))
    assert status == 200
    response = CheckResponse.model_validate_json(body)
    assert set(response.repairs) <= {issue.issue_id for issue in response.issues}


@pytest.mark.parametrize(
    "method, path, body, status, code",
    [
        ("POST", "/chat", "{not json", 400, "bad_request"),
        ("POST", "/chat", '{"message": "hi"}', 422, "validation_error"),
        ("GET", "/plan/no-such-plan", None, 404, "plan_not_found"),
        ("POST", "/plan/check", '{"plan_id": "no-such-plan"}', 404, "plan_not_found"),
        ("PUT", "/plan/other-id", SAMPLE_PLAN.model_dump_json(), 422, "validation_error"),
        ("GET", "/nope", None, 404, "not_found"),
    ],
)
def test_errors(method, path, body, status, code):
    got_status, got_body = call(method, path, body)
    assert got_status == status
    assert ErrorResponse.model_validate_json(got_body).error.code == code
