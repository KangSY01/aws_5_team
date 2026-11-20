"""GET /alerts?plan_id= (api-contract 「GET /alerts」). 저장된 예약 점검 결과를 읽기만 한다. AWS·네트워크 없음."""

import datetime as dt
import json

import pytest

import app.handler as handler_module
from app import storage
from app.handler import handler
from app.models.api import AlertsResponse, ErrorResponse
from app.models.plan import Issue
from scripts.local_invoke import make_event

KST = dt.timezone(dt.timedelta(hours=9))
RAIN = Issue(issue_id="s4-rain", type="rain", stop_id="s4", severity="high", detail="15:30-17:00 강수확률 80%, 실외 장소")


def get_alerts(query: dict | None, path: str = "/alerts") -> tuple[int, dict]:
    result = handler(make_event("GET", path, query=query))
    return result["statusCode"], json.loads(result["body"])


def test_before_any_check_the_answer_is_empty_not_an_error():
    status, body = get_alerts({"plan_id": "plan-1"})
    assert status == 200
    assert body == {"plan_id": "plan-1", "checked_at": None, "issues": []}  # 계약: 점검 전이면 checked_at null, issues []


def test_returns_the_last_stored_result():
    checked = dt.datetime(2026, 11, 21, 11, 10, tzinfo=KST)
    storage.save_alerts(AlertsResponse(plan_id="plan-1", checked_at=checked, issues=[RAIN]))

    status, body = get_alerts({"plan_id": "plan-1"})

    assert status == 200
    response = AlertsResponse.model_validate(body)
    assert response.checked_at == checked and response.issues == [RAIN]
    assert body["issues"][0] == {
        "issue_id": "s4-rain", "type": "rain", "stop_id": "s4", "severity": "high", "detail": RAIN.detail,
    }


def test_a_newer_result_replaces_the_older_one_in_the_answer():
    first = dt.datetime(2026, 11, 21, 8, 15, tzinfo=KST)
    storage.save_alerts(AlertsResponse(plan_id="plan-1", checked_at=first, issues=[RAIN]))
    storage.save_alerts(AlertsResponse(plan_id="plan-1", checked_at=first + dt.timedelta(hours=3), issues=[]))

    assert get_alerts({"plan_id": "plan-1"})[1]["issues"] == []


@pytest.mark.parametrize("query", [None, {}, {"plan_id": ""}, {"plan_id": "   "}, {"other": "plan-1"}])
def test_missing_plan_id_is_422(query):
    status, body = get_alerts(query)
    error = ErrorResponse.model_validate(body).error
    assert status == 422 and error.code == "validation_error"
    assert "쿼리 파라미터" in error.message  # 저장소 오류가 아니라 handler 가 먼저 알려 준다


def test_unknown_plan_is_404_plan_not_found():
    status, body = get_alerts({"plan_id": "plan-none"})
    assert status == 404 and ErrorResponse.model_validate(body).error.code == "plan_not_found"


def test_it_only_reads_and_never_runs_a_check(monkeypatch, api_storage):
    def fail(*args, **kwargs):
        pytest.fail("GET /alerts 가 점검을 새로 했다")

    monkeypatch.setattr(handler_module.guardian, "run_check", fail)
    monkeypatch.setattr(handler_module.guardian, "run_delay", fail)
    monkeypatch.setattr(api_storage, "update_plan", fail)
    monkeypatch.setattr(api_storage, "create_plan", fail)

    assert get_alerts({"plan_id": "plan-1"})[0] == 200


def test_storage_failure_is_500_without_details(monkeypatch):
    def down(plan_id):
        raise storage.StorageError("AccessDeniedException arn:aws:dynamodb:ap-northeast-2:060151520349:table/secret")

    monkeypatch.setattr(storage, "get_alerts", down)

    status, body = get_alerts({"plan_id": "plan-1"})

    assert status == 500 and body == {"error": {"code": "internal_error", "message": "서버 오류가 발생했습니다."}}


@pytest.mark.parametrize("method, path", [("POST", "/alerts"), ("PUT", "/alerts"), ("GET", "/alerts/plan-1")])
def test_other_methods_and_paths_stay_404(method, path):
    result = handler(make_event(method, path, query={"plan_id": "plan-1"}))
    assert result["statusCode"] == 404


def test_existing_plan_routes_are_unchanged_by_the_new_route():
    for method, path, body in (("GET", "/plan/plan-1", None), ("POST", "/plan/check", json.dumps({"plan_id": "plan-1"}))):
        assert handler(make_event(method, path, body))["statusCode"] == 200


def test_make_event_carries_query_parameters_like_a_function_url_event():
    event = make_event("GET", "/alerts", query={"plan_id": "plan-1"})
    assert event["rawPath"] == "/alerts" and event["rawQueryString"] == "plan_id=plan-1"
    assert event["queryStringParameters"] == {"plan_id": "plan-1"}
    assert "queryStringParameters" not in make_event("GET", "/plan/plan-1")  # 쿼리가 없으면 이전과 같은 이벤트
