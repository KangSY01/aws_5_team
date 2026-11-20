"""HTTPS API 배포 구성(infra/api) 점검. AWS 자격 증명·네트워크 없이 돈다.

- 템플릿(infra/api/template.yaml)이 실제 진입점·환경 변수·DynamoDB 테이블·CORS·IAM 을 코드와 맞게 가리키는지 본다.
- Lambda Function URL 이 보내는 이벤트(payload v2.0) 모양으로 handler 의 모든 경로를 다시 확인한다 (회귀).
- 저장소 종류 분리(STORAGE_BACKEND): 배포는 USE_MOCK 과 무관하게 DynamoDB 를 쓴다.
"""

import base64
import importlib.util
import inspect
import json
import re
from pathlib import Path

import pytest

from app import agent, config
from app import handler as handler_module
from app.models.api import AlertsResponse, ChatResponse, CheckResponse, DelayResponse, ErrorResponse, PlanResponse
from app.storage import service as storage_service
from chat_stubs import ScriptedModel, text_turn, tool_turn

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
API_TEMPLATE = ROOT / "infra" / "api" / "template.yaml"
BASE_TEMPLATE = ROOT / "infra" / "base" / "template.yaml"
DEPLOY_SCRIPT = ROOT / "infra" / "scripts" / "deploy_api.ps1"
PLAN_ID = "plan-1"


class _CfnLoader(yaml.SafeLoader):
    """!Ref, !Sub 같은 CloudFormation 단축 태그를 {"Ref": 값} 형태로 읽는다."""


def _cfn_tag(loader, suffix, node):
    name = "Ref" if suffix == "Ref" else f"Fn::{suffix}"
    if isinstance(node, yaml.ScalarNode):
        return {name: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {name: loader.construct_sequence(node, deep=True)}
    return {name: loader.construct_mapping(node, deep=True)}


_CfnLoader.add_multi_constructor("!", _cfn_tag)


def load_template(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_CfnLoader)


@pytest.fixture(scope="module")
def template() -> dict:
    return load_template(API_TEMPLATE)


@pytest.fixture(scope="module")
def function(template) -> dict:
    return template["Resources"]["ApiFunction"]["Properties"]


def statements(template) -> dict[str, dict]:
    policy = template["Resources"]["ApiRole"]["Properties"]["Policies"][0]["PolicyDocument"]
    return {s["Sid"]: s for s in policy["Statement"]}


def url_event(method, path, body=None, query=None, base64_body=False) -> dict:
    """Function URL 이 Lambda 에 넘기는 이벤트 (payload v2.0). 헤더는 소문자로 온다."""
    event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "&".join(f"{k}={v}" for k, v in (query or {}).items()),
        "headers": {"content-type": "application/json", "origin": "https://d123.cloudfront.net"},
        "requestContext": {"http": {"method": method, "path": path, "protocol": "HTTP/1.1"}, "stage": "$default"},
        "isBase64Encoded": base64_body,
    }
    if query:
        event["queryStringParameters"] = dict(query)
    if body is not None:
        event["body"] = base64.b64encode(body.encode()).decode() if base64_body else body
    return event


def call(method, path, body=None, query=None, base64_body=False):
    result = handler_module.handler(url_event(method, path, body, query, base64_body), context=None)
    assert result["headers"]["content-type"].startswith("application/json")
    return result["statusCode"], json.loads(result["body"]), result["headers"]


# ---- 1. 실행 진입점 ----


def test_lambda_entry_point_is_the_shared_handler(function):
    module, name = function["Handler"].rsplit(".", 1)
    assert (module, name) == ("app.handler", "handler")  # handler.py 를 바꾸지 않고 그대로 쓴다
    assert list(inspect.signature(handler_module.handler).parameters) == ["event", "context"]
    assert function["Runtime"] == "python3.13" and function["Architectures"] == ["arm64"]


def test_function_url_is_https_output_and_buffered(template, function):
    url = function["FunctionUrlConfig"]
    assert url["InvokeMode"] == "BUFFERED"  # /chat 은 JSON 한 번에. 스트리밍은 아직 없다
    assert template["Outputs"]["ApiUrl"]["Value"] == {"Fn::GetAtt": "ApiFunctionUrl.FunctionUrl"}


def test_api_zip_contains_the_whole_app_package(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_api_zip", ROOT / "infra" / "scripts" / "build_api_zip.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(build, "PACKAGE", tmp_path)

    build.copy_sources()

    app = tmp_path / "app"
    for name in ("handler.py", "agent.py", "prompts.py", "tools/lookup.py", "tools/schedule.py", "guardian/service.py",
                 "storage/dynamodb.py", "chat/tools.py", "data/places.json", "data/chat_response.json"):
        assert (app / name).is_file(), name
    assert not list(app.rglob("__pycache__")) and not list(app.rglob("*.pyc"))
    assert not (app / ".env").exists()


# ---- 2·3. POST /chat (Function URL 이벤트) ----


def test_chat_through_function_url_event_runs_the_real_agent(monkeypatch, api_storage):
    monkeypatch.setattr(config, "FAKE_LLM", False)
    model = ScriptedModel([
        tool_turn(("search_places", {"query": ""})),
        tool_turn(("create_plan", {"place_ids": ["gamcheon-village", "jagalchi-market", "busan-tower"], "date": "2026-11-28"})),
        text_turn("Here is your day: [place:gamcheon-village] first."),
    ])
    monkeypatch.setattr(agent, "get_model", lambda: model)
    body = json.dumps({"message": "Plan a day", "profile": {"language": "en"}})

    status, response, headers = call("POST", "/chat", body, base64_body=True)  # Function URL 은 본문을 base64 로 줄 수 있다

    assert status == 200 and len(model.requests) == 3
    assert set(response) == set(ChatResponse.model_fields)
    assert api_storage.get_plan(response["plan_id"]).stops  # 일정이 저장소에 남았다
    assert not any(h.lower().startswith("access-control-") for h in headers)  # CORS 는 Function URL 이 붙인다


def test_fake_llm_chat_still_returns_the_fixed_sample(monkeypatch):
    monkeypatch.setattr(config, "FAKE_LLM", True)
    monkeypatch.setattr(agent, "get_model", lambda: pytest.fail("FAKE_LLM 에서 모델을 만들면 안 된다"))

    status, response, _ = call("POST", "/chat", json.dumps({"message": "hi", "profile": {"language": "ja"}}))

    sample = ChatResponse.model_validate_json(agent._FAKE_RESPONSE_PATH.read_text(encoding="utf-8"))
    assert status == 200 and ChatResponse.model_validate(response).answer == sample.answer


# ---- 4~7, 9, 12. 다른 경로 회귀 (Function URL 이벤트) ----


def test_plan_guardian_delay_and_alerts_routes_through_function_url_events(api_storage):
    stored = api_storage.get_plan(PLAN_ID)

    status, body, _ = call("GET", f"/plan/{PLAN_ID}")
    assert status == 200 and PlanResponse.model_validate(body).plan == stored
    status, body, _ = call("PUT", f"/plan/{PLAN_ID}", stored.model_dump_json(), base64_body=True)
    assert status == 200 and PlanResponse.model_validate(body).plan == stored

    status, body, _ = call("POST", "/plan/check", json.dumps({"plan_id": PLAN_ID}))
    assert status == 200 and CheckResponse.model_validate(body).plan_id == PLAN_ID
    status, body, _ = call("POST", f"/plan/{PLAN_ID}/delay", json.dumps({"plan_id": PLAN_ID, "delay_min": 30}))
    assert status == 200 and DelayResponse.model_validate(body).plan_id == PLAN_ID
    assert api_storage.get_plan(PLAN_ID) == stored  # 해결안은 저장하지 않는다

    status, body, _ = call("GET", "/alerts", query={"plan_id": PLAN_ID})
    assert status == 200 and AlertsResponse.model_validate(body).checked_at is None


@pytest.mark.parametrize(
    "method, path, body, query, status, code",
    [
        ("GET", "/nope", None, None, 404, "not_found"),
        ("OPTIONS", "/chat", None, None, 404, "not_found"),  # 사전 요청은 Function URL 이 답한다. Lambda 까지 오면 없는 경로다
        ("POST", "/chat", "{bad", None, 400, "bad_request"),
        ("POST", "/chat", '{"message": "hi"}', None, 422, "validation_error"),
        ("GET", "/plan/plan-nope", None, None, 404, "plan_not_found"),
        ("GET", "/alerts", None, None, 422, "validation_error"),
        ("GET", "/alerts", None, {"plan_id": "plan-nope"}, 404, "plan_not_found"),
    ],
)
def test_error_responses_keep_the_contract(method, path, body, query, status, code):
    got_status, got, _ = call(method, path, body, query)
    assert got_status == status and got["error"]["code"] == code
    ErrorResponse.model_validate(got)


# ---- 8. CORS ----


def test_cors_allows_only_configured_origins_and_the_methods_the_api_uses(template, function):
    cors = function["FunctionUrlConfig"]["Cors"]
    assert cors["AllowOrigins"] == {"Ref": "AllowedOrigins"}
    origins = template["Parameters"]["AllowedOrigins"]
    assert origins["Type"] == "CommaDelimitedList" and "Default" not in origins  # 배포할 때 반드시 정한다
    assert set(cors["AllowMethods"]) == {"GET", "POST", "PUT"}
    assert {"content-type", "accept"} <= {h.lower() for h in cors["AllowHeaders"]}
    assert "AllowCredentials" not in cors  # 쿠키 인증을 쓰지 않는다
    assert function["FunctionUrlConfig"]["AuthType"] == "NONE"  # 계약에 인증이 없다 (위험 요소는 README)


def test_handler_source_never_adds_cors_headers():
    # Function URL 의 CORS 와 겹치면 브라우저가 거부한다 (Access-Control-Allow-Origin 이 두 번)
    assert "access-control" not in Path(handler_module.__file__).read_text(encoding="utf-8").lower()


def test_deploy_script_rejects_wildcard_origin_and_defaults_to_cloudfront():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8-sig")
    assert 'if ($origin -eq "*") { throw' in script
    assert 'Get-BaseOutput "CloudFrontDomain"' in script
    assert DEPLOY_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")  # PowerShell 5.1 이 한국어를 읽으려면 BOM 이 필요하다


# ---- 10. 환경 변수 ----


def test_template_env_vars_are_the_ones_config_reads(function):
    env = function["Environment"]["Variables"]
    read_by_config = set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', Path(config.__file__).read_text(encoding="utf-8")))
    read_by_config |= set(re.findall(r'_flag\("([A-Z_]+)"\)', Path(config.__file__).read_text(encoding="utf-8")))
    assert set(env) <= read_by_config
    assert {"BEDROCK_MODEL_ID", "FAKE_LLM", "USE_MOCK", "STORAGE_BACKEND", "DYNAMODB_TABLE", "UPLOADS_BUCKET"} <= set(env)
    assert "AWS_REGION" not in env  # Lambda 예약 변수. 스택 리전(ap-northeast-2)이 들어간다
    assert env["STORAGE_BACKEND"] == "dynamodb"


def test_deploy_defaults_are_real_mode(template):
    params = template["Parameters"]
    assert params["FakeLlm"]["Default"] == "0" and params["UseMock"]["Default"] == "0"
    assert params["DataGoKrKey"].get("NoEcho") is True  # 키 값은 콘솔·출력에 보이지 않는다


def test_function_timeout_leaves_room_for_the_chat_time_limit(template, function):
    assert function["Timeout"] == {"Ref": "FunctionTimeout"}
    assert template["Parameters"]["FunctionTimeout"]["Default"] >= agent.CHAT_TIMEOUT_SEC + 10


@pytest.mark.parametrize(
    "use_mock, backend, memory",
    [(True, "", True), (False, "", False), (True, "dynamodb", False), (False, "memory", True)],
)
def test_storage_backend_overrides_use_mock(monkeypatch, use_mock, backend, memory):
    monkeypatch.setattr(config, "USE_MOCK", use_mock)
    monkeypatch.setattr(config, "STORAGE_BACKEND", backend)
    assert config.use_memory_storage() is memory


def test_unknown_storage_backend_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "sqlite")
    with pytest.raises(ValueError):
        config.use_memory_storage()


def test_deployed_settings_need_only_the_table_when_mocked(monkeypatch):
    for name, value in {"USE_MOCK": "1", "STORAGE_BACKEND": "dynamodb", "DYNAMODB_TABLE": "", "DATA_GO_KR_KEY_DECODING": ""}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "dynamodb")
    assert config.missing_keys() == ["DYNAMODB_TABLE"]  # 샘플 데이터여도 DynamoDB 테이블은 필요하다
    monkeypatch.setenv("DYNAMODB_TABLE", "busan-guide-sessions")
    assert config.missing_keys() == []


# ---- 11. DynamoDB ----


def test_api_uses_the_existing_sessions_table(template):
    base_table = load_template(BASE_TEMPLATE)["Resources"]["SessionsTable"]["Properties"]["TableName"]
    assert template["Parameters"]["DynamoDbTable"]["Default"] == base_table == "busan-guide-sessions"
    assert not any(r["Type"].startswith("AWS::DynamoDB::") for r in template["Resources"].values())  # 테이블을 만들지 않는다
    env = template["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
    assert env["DYNAMODB_TABLE"] == {"Ref": "DynamoDbTable"}


def test_dynamodb_permissions_match_what_the_api_calls(template):
    sessions = statements(template)["SessionsTable"]
    assert sessions["Resource"] == {"Fn::Sub": "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${DynamoDbTable}"}
    source = Path(storage_service.__file__).with_name("dynamodb.py").read_text(encoding="utf-8")
    used = {m.replace("_", "") for m in re.findall(r"self\._table\.(\w+)\(", source)}
    allowed = {a.split(":")[1].lower() for a in sessions["Action"]}
    assert allowed == used - {"scan"}  # Scan(일정 목록)은 예약 점검 Lambda 만 쓴다
    assert "list_plan_ids" not in Path(handler_module.__file__).read_text(encoding="utf-8")


def test_api_can_use_the_weather_cache_and_no_other_table(template, function):
    from app.tools import lookup

    found = statements(template)
    cache = found["WeatherCache"]
    assert set(cache["Action"]) == {"dynamodb:GetItem", "dynamodb:PutItem"}
    assert cache["Resource"] == {"Fn::Sub": "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/busan-guide-cache"}
    base_cache = load_template(BASE_TEMPLATE)["Resources"]["CacheTable"]["Properties"]["TableName"]
    default = re.search(r'os\.environ\.get\("CACHE_TABLE", "([^"]*)"\)', Path(config.__file__).read_text(encoding="utf-8"))
    assert default.group(1) == base_cache == "busan-guide-cache"
    assert "CACHE_TABLE" not in function["Environment"]["Variables"]  # 기본값을 쓴다. 권한의 테이블 이름과 어긋나지 않게
    used = set(re.findall(r"_cache_table\(\)\.(\w+)\(", Path(lookup.__file__).read_text(encoding="utf-8")))
    assert used == {"get_item", "put_item"}

    # DynamoDB 권한은 세션 테이블과 캐시 테이블 두 곳뿐이다
    dynamo = [s for s in found.values() if any(a.startswith("dynamodb:") for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]]))]
    assert {s["Sid"] for s in dynamo} == {"SessionsTable", "WeatherCache"}
    assert all("*" not in s["Resource"]["Fn::Sub"] for s in dynamo)
    # 다른 권한은 그대로 있다
    assert {"Logs", "SessionsTable", "BedrockModelOrProfile", "BedrockModelsBehindProfile", "PhotoUploads", "PhotoTextract",
            "PollySpeak", "WeatherCache", "TranscribeStreaming"} == set(found)


def test_deployed_storage_is_dynamodb_even_with_sample_data(monkeypatch):
    sentinel = object()
    built = []

    class FakeDynamo:
        @classmethod
        def from_config(cls):
            built.append(True)
            return sentinel

    import app.storage.dynamodb as dynamodb

    monkeypatch.setattr(dynamodb, "DynamoBackend", FakeDynamo)
    monkeypatch.setattr(storage_service, "_storage", None)
    monkeypatch.setattr(storage_service, "_storage_is_mock", None)
    monkeypatch.setattr(config, "USE_MOCK", True)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "dynamodb")

    store = storage_service.get_storage()

    assert built == [True] and store._backend is sentinel


# ---- 사진 인식 (D 의 app/photo) ----


def test_photo_uses_the_existing_uploads_bucket(template, function):
    param = template["Parameters"]["UploadsBucket"]
    assert "Default" not in param  # 배포할 때 공용 스택 출력값을 반드시 넘긴다
    assert function["Environment"]["Variables"]["UPLOADS_BUCKET"] == {"Ref": "UploadsBucket"}
    assert not any(r["Type"] == "AWS::S3::Bucket" for r in template["Resources"].values())  # 버킷을 새로 만들지 않는다
    base_outputs = load_template(BASE_TEMPLATE)["Outputs"]
    assert base_outputs["UploadsBucketName"]["Value"] == {"Ref": "UploadsBucket"}
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8-sig")
    assert 'Get-BaseOutput "UploadsBucketName"' in script and '"UploadsBucket=$UploadsBucket"' in script


def test_photo_permissions_cover_presign_textract_and_only_photo_keys(template):
    found = statements(template)
    s3 = found["PhotoUploads"]
    assert set(s3["Action"]) == {"s3:PutObject", "s3:GetObject"}  # presigned PUT 서명, Textract 의 S3 읽기
    assert s3["Resource"] == {"Fn::Sub": "arn:${AWS::Partition}:s3:::${UploadsBucket}/photos/*"}
    from app.photo import upload

    assert upload.KEY_PREFIX == "photos/"  # 권한 범위가 D 가 발급하는 키 접두사와 같다
    assert found["PhotoTextract"]["Action"] == "textract:DetectDocumentText"
    assert "BedrockModelOrProfile" in found and "BedrockModelsBehindProfile" in found  # 사진 번역도 같은 Bedrock 권한을 쓴다


def test_photo_service_reads_the_bucket_from_config(monkeypatch):
    from app.photo import service

    monkeypatch.setattr(config, "UPLOADS_BUCKET", "busan-guide-uploads-123456789012")
    assert service._bucket() == "busan-guide-uploads-123456789012"


# ---- IAM: Bedrock·로그 ----


def test_bedrock_permissions_cover_the_profile_and_streaming(template):
    found = statements(template)
    direct, behind = found["BedrockModelOrProfile"], found["BedrockModelsBehindProfile"]
    for statement in (direct, behind):
        assert set(statement["Action"]) == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}
    assert any("inference-profile/${BedrockModelId}" in r["Fn::Sub"] for r in direct["Resource"])
    assert {"Fn::Sub": "arn:${AWS::Partition}:bedrock:::foundation-model/*"} in behind["Resource"]  # 전역 모델 ARN
    assert "bedrock:InferenceProfileArn" in behind["Condition"]["StringEquals"]


def test_logs_go_to_the_stack_log_group_with_retention(template, function):
    group = template["Resources"]["ApiLogGroup"]["Properties"]
    assert "RetentionInDays" in group
    assert function["LoggingConfig"]["LogGroup"] == {"Ref": "ApiLogGroup"}
    assert statements(template)["Logs"]["Resource"] == {"Fn::GetAtt": "ApiLogGroup.Arn"}
