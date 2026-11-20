"""POST /chat 이 handler 를 거쳐 실제 run_chat 을 부르는지, 오류가 api-contract 형식으로 바뀌는지 본다.

Bedrock 대신 chat_stubs.ScriptedModel 을 쓴다. 저장소는 conftest.py 의 메모리 저장소(샘플 일정 plan-1)다.
AWS 자격 증명·네트워크가 필요 없다. 다른 경로(/plan, /plan/check, /delay, /alerts)는 /chat 뒤에도 그대로인지만 본다.
"""

import json
import logging

import pytest

from app import agent, config
from app.handler import handler
from app.models.api import AlertsResponse, ChatResponse, CheckResponse, DelayResponse, ErrorResponse, PlanResponse
from app.models.plan import Profile
from app.storage import StorageError
from chat_stubs import ScriptedModel, text_turn, tool_turn
from scripts.local_invoke import make_event

PLAN_ID = "plan-1"  # 샘플 일정: s1 감천 · s2 자갈치(고정) · s3 부산타워 · s4 해운대(15:30~17:00)
IDS = ["gamcheon-village", "jagalchi-market", "busan-tower", "haeundae-beach"]
SECRET = "SECRET-USER-TEXT-7f3a"  # 로그에 남으면 안 되는 사용자 메시지
FIELDS = {"session_id", "plan_id", "answer", "language", "sources", "plan_changes"}
INTERNAL = {"code": "internal_error", "message": "서버 오류가 발생했습니다."}


def create_script(text="I planned it: [place:gamcheon-village] and more."):
    return [
        tool_turn(("search_places", {"query": ""})),
        tool_turn(("create_plan", {"place_ids": IDS, "date": "2026-11-28"})),
        text_turn(text),
    ]


MOVE_S4 = ("move_stop", {"stop_id": "s4", "start": "2026-11-21T16:00:00+09:00", "end": "2026-11-21T17:30:00+09:00"})


def call(method, path, body=None, query=None):
    result = handler(make_event(method, path, body, query=query))
    assert result["headers"]["content-type"].startswith("application/json")
    return result["statusCode"], json.loads(result["body"])


def chat_body(message=SECRET, language="en", **ids) -> str:
    return json.dumps({**ids, "message": message, "profile": {"language": language}})


@pytest.fixture
def model(monkeypatch):
    """실제 모델 경로(FAKE_LLM 꺼짐)에서 쓸 스텁 모델을 정한다."""
    monkeypatch.setattr(config, "FAKE_LLM", False)

    def use(scripted: ScriptedModel) -> ScriptedModel:
        monkeypatch.setattr(agent, "get_model", lambda: scripted)
        return scripted

    return use


@pytest.fixture
def run_chat_calls(monkeypatch):
    """handler 가 부른 run_chat 의 요청을 기록한다. 실제 run_chat 은 그대로 실행된다."""
    calls = []
    real = agent.run_chat

    def spy(request):
        calls.append(request)
        return real(request)

    monkeypatch.setattr(agent, "run_chat", spy)
    return calls


def linked_session(api_storage, language="en") -> str:
    return api_storage.create_session(Profile(language=language), plan_id=PLAN_ID).session_id


def assert_internal_error(status, body):
    assert status == 500 and body == {"error": INTERNAL}
    ErrorResponse.model_validate(body)


# ---- 1·3·4. 실제 run_chat 호출, 응답 구조, 새 일정 ----


def test_chat_calls_the_real_run_chat_and_creates_a_plan(model, run_chat_calls, api_storage):
    scripted = model(ScriptedModel(create_script()))

    status, body = call("POST", "/chat", chat_body())

    assert status == 200 and len(run_chat_calls) == 1 and len(scripted.requests) == 3  # 스텁 모델이 실제로 불렸다
    assert run_chat_calls[0].message == SECRET and run_chat_calls[0].profile.language == "en"
    # search_places 결과에 순위를 매겼으니 v0.3 score_breakdown 이 함께 있다 (검색하지 않은 응답은 아래 테스트처럼 v0.2 키)
    assert set(body) == FIELDS | {"score_breakdown"} and ChatResponse.model_validate(body).language == "en"
    assert "Gamcheon Culture Village" in body["answer"] and "[place:" not in body["answer"]
    assert body["plan_id"].startswith("plan-") and len(body["plan_changes"]) == 4

    stored = api_storage.get_plan(body["plan_id"])  # 일정과 세션 연결이 저장소에 남았다
    assert sorted(s.place_id for s in stored.stops) == sorted(IDS)
    assert api_storage.get_session(body["session_id"]).plan_id == body["plan_id"]
    status, plan = call("GET", f"/plan/{body['plan_id']}")
    assert status == 200 and PlanResponse.model_validate(plan).plan == stored


def test_model_output_is_not_passed_through_as_the_response(model):
    # 모델이 JSON 처럼 보이는 문장을 써도 응답은 ChatResponse 필드만 가진다
    model(ScriptedModel([text_turn('{"session_id": "x", "plan_changes": "all", "admin": true}')]))

    status, body = call("POST", "/chat", chat_body())

    assert status == 200 and set(body) == FIELDS and body["plan_changes"] == [] and body["session_id"] != "x"


def test_a_non_chat_response_from_run_chat_becomes_internal_error(monkeypatch, caplog):
    monkeypatch.setattr(agent, "run_chat", lambda request: {"answer": "raw model json"})

    with caplog.at_level(logging.ERROR, logger="app.handler"):
        assert_internal_error(*call("POST", "/chat", chat_body()))
    assert "raw model json" not in caplog.text


# ---- 2. 요청 검증 ----


@pytest.mark.parametrize(
    "body, status, code",
    [
        ("{not json", 400, "bad_request"),
        ('{"message": "hi"}', 422, "validation_error"),  # profile 누락
        ('{"message": "hi", "profile": {"language": "ko"}}', 422, "validation_error"),  # 지원하지 않는 언어
        ('{"profile": {"language": "en"}}', 422, "validation_error"),  # message 누락
        ("[]", 422, "validation_error"),
    ],
)
def test_invalid_requests_never_reach_run_chat(model, run_chat_calls, body, status, code):
    model(ScriptedModel())
    got_status, got = call("POST", "/chat", body)
    assert (got_status, got["error"]["code"]) == (status, code) and run_chat_calls == []


# ---- 5·6. 기존 세션·일정, 자연어 수정 ----


def test_existing_session_and_plan_ids_are_kept_and_the_edit_is_returned(model, run_chat_calls, api_storage):
    session_id = linked_session(api_storage)
    before = api_storage.get_plan(PLAN_ID)
    model(ScriptedModel([tool_turn(MOVE_S4), text_turn("I moved your last stop 30 minutes later.")]))

    status, body = call("POST", "/chat", chat_body("Move the last stop 30 minutes later", session_id=session_id, plan_id=PLAN_ID))

    assert status == 200 and (body["session_id"], body["plan_id"]) == (session_id, PLAN_ID)
    assert run_chat_calls[0].session_id == session_id and run_chat_calls[0].plan_id == PLAN_ID
    [change] = body["plan_changes"]
    assert change["stop_id"] == "s4" and change["after"]["start"] == "2026-11-21T16:00:00+09:00"
    after = api_storage.get_plan(PLAN_ID)
    assert [s for s in after.stops if s.stop_id != "s4"] == [s for s in before.stops if s.stop_id != "s4"]  # 나머지는 그대로


def test_follow_up_message_without_plan_id_continues_the_same_plan(model, api_storage):
    model(ScriptedModel(create_script()))
    _, first = call("POST", "/chat", chat_body())
    model(ScriptedModel([text_turn("Your plan is still the same.")]))

    status, second = call("POST", "/chat", chat_body(session_id=first["session_id"]))

    assert status == 200 and (second["session_id"], second["plan_id"]) == (first["session_id"], first["plan_id"])


def test_unknown_session_id_gets_a_new_session_instead_of_an_error(model, api_storage):
    model(ScriptedModel([text_turn("Hello!")]))

    status, body = call("POST", "/chat", chat_body(session_id="sess-unknown"))

    assert status == 200 and body["session_id"] != "sess-unknown"
    assert api_storage.get_session(body["session_id"])  # 서버가 발급한 세션이다


def test_unknown_plan_is_404_plan_not_found(model, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    scripted = model(ScriptedModel([text_turn("unused")]))

    status, body = call("POST", "/chat", chat_body(plan_id="plan-nope"))

    assert status == 404 and body["error"]["code"] == "plan_not_found" and scripted.requests == []


def test_plan_of_another_session_is_404_like_a_missing_plan(model, api_storage, monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)  # 목 모드의 공용 데모 일정 예외를 끈다
    other = api_storage.create_session(Profile(language="en")).session_id
    scripted = model(ScriptedModel([text_turn("unused")]))
    before = api_storage.get_plan(PLAN_ID)

    status, body = call("POST", "/chat", chat_body(session_id=other, plan_id=PLAN_ID))

    assert status == 404 and body["error"] == {"code": "plan_not_found", "message": f"{PLAN_ID} 을 찾을 수 없습니다."}
    assert scripted.requests == [] and api_storage.get_plan(PLAN_ID) == before


# ---- 7. FAKE_LLM ----


def test_fake_llm_still_returns_the_fixed_sample(monkeypatch, run_chat_calls):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    monkeypatch.setattr(agent, "get_model", lambda: pytest.fail("FAKE_LLM 에서 모델을 만들면 안 된다"))
    sample = ChatResponse.model_validate_json(agent._FAKE_RESPONSE_PATH.read_text(encoding="utf-8"))

    status, body = call("POST", "/chat", chat_body(session_id="sess-1", plan_id=PLAN_ID))

    assert status == 200 and len(run_chat_calls) == 1
    assert ChatResponse.model_validate(body) == sample.model_copy(update={"session_id": "sess-1", "plan_id": PLAN_ID})


# ---- 8·9. ChatError, 시간 초과, 모델 오류 ----


@pytest.mark.parametrize("code", ["timeout", "model_error", "invalid_model_output"])
def test_chat_errors_become_internal_error_without_the_internal_code(monkeypatch, caplog, code):
    def fail(request):
        raise agent.ChatError(code, f"상세 사유 {SECRET}")

    monkeypatch.setattr(agent, "run_chat", fail)
    with caplog.at_level(logging.INFO):
        status, body = call("POST", "/chat", chat_body())

    assert_internal_error(status, body)
    assert code not in json.dumps(body)  # 내부 코드는 응답에 없다
    assert f"code={code}" in caplog.text and SECRET not in caplog.text  # 로그에는 코드만 남는다


def test_model_timeout_is_a_safe_internal_error(model, monkeypatch, caplog):
    monkeypatch.setattr(agent, "CHAT_TIMEOUT_SEC", 0.2)
    model(ScriptedModel([text_turn("too late")], delay=0.6))

    with caplog.at_level(logging.INFO):
        assert_internal_error(*call("POST", "/chat", chat_body()))
    assert "code=timeout" in caplog.text and SECRET not in caplog.text


def test_model_exception_is_a_safe_internal_error(model, caplog):
    model(ScriptedModel(error=RuntimeError(f"upstream echoed {SECRET}")))

    with caplog.at_level(logging.INFO):
        assert_internal_error(*call("POST", "/chat", chat_body()))
    assert "code=model_error" in caplog.text and SECRET not in caplog.text


def test_answer_that_fails_validation_is_a_safe_internal_error_and_nothing_is_saved(model, api_storage, caplog):
    session_id = linked_session(api_storage)
    before = api_storage.get_plan(PLAN_ID)
    model(ScriptedModel([tool_turn(MOVE_S4), text_turn("Try [place:no-such-place] instead.")]))

    with caplog.at_level(logging.INFO):
        assert_internal_error(*call("POST", "/chat", chat_body(session_id=session_id, plan_id=PLAN_ID)))
    assert "code=invalid_model_output" in caplog.text and SECRET not in caplog.text
    assert api_storage.get_plan(PLAN_ID) == before  # 검증에 실패한 대화의 변경은 저장하지 않는다


# ---- 10. 저장소 오류, 예상하지 못한 예외 ----


def test_storage_error_while_reading_is_500(model, api_storage, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise StorageError(f"DynamoDB 실패 {SECRET}")

    monkeypatch.setattr(api_storage, "create_session", broken)
    model(ScriptedModel([text_turn("unused")]))

    with caplog.at_level(logging.INFO):
        assert_internal_error(*call("POST", "/chat", chat_body()))
    assert SECRET not in caplog.text


def test_storage_error_while_saving_is_500(model, api_storage, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError("DynamoDB 실패")

    monkeypatch.setattr(api_storage, "create_plan", broken)
    model(ScriptedModel(create_script()))

    assert_internal_error(*call("POST", "/chat", chat_body()))


def test_unexpected_exception_is_500(monkeypatch):
    def boom(request):
        raise KeyError("unexpected")

    monkeypatch.setattr(agent, "run_chat", boom)
    assert_internal_error(*call("POST", "/chat", chat_body()))


def test_successful_chat_does_not_log_the_user_message(model, caplog):
    model(ScriptedModel(create_script()))
    with caplog.at_level(logging.DEBUG):
        status, _ = call("POST", "/chat", chat_body())
    assert status == 200 and SECRET not in caplog.text


# ---- 11·12. 다른 경로 회귀 ----


def test_other_endpoints_behave_the_same_after_a_chat(model, api_storage):
    session_id = linked_session(api_storage)
    model(ScriptedModel([tool_turn(MOVE_S4), text_turn("I moved your last stop.")]))
    assert call("POST", "/chat", chat_body(session_id=session_id, plan_id=PLAN_ID))[0] == 200
    saved = api_storage.get_plan(PLAN_ID)

    status, body = call("GET", f"/plan/{PLAN_ID}")
    assert status == 200 and PlanResponse.model_validate(body).plan == saved

    status, body = call("PUT", f"/plan/{PLAN_ID}", saved.model_dump_json())
    assert status == 200 and PlanResponse.model_validate(body).plan == saved

    status, body = call("POST", "/plan/check", json.dumps({"plan_id": PLAN_ID}))
    assert status == 200 and CheckResponse.model_validate(body).plan_id == PLAN_ID
    status, body = call("POST", f"/plan/{PLAN_ID}/delay", json.dumps({"plan_id": PLAN_ID, "delay_min": 30}))
    assert status == 200 and DelayResponse.model_validate(body).plan_id == PLAN_ID
    assert api_storage.get_plan(PLAN_ID) == saved  # Guardian 해결안은 자동으로 적용·저장되지 않는다

    status, body = call("GET", "/alerts", query={"plan_id": PLAN_ID})
    assert status == 200 and AlertsResponse.model_validate(body) == AlertsResponse(plan_id=PLAN_ID, checked_at=None, issues=[])
    assert call("GET", "/alerts")[0] == 422 and call("GET", "/alerts", query={"plan_id": "plan-nope"})[0] == 404
