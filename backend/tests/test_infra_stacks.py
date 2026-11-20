"""예약 점검 스택(infra/alerts)과 AgentCore 스택(infra/template.yaml)의 배포 설정 점검. AWS 자격 증명·네트워크 없이 돈다.

- 예약 점검 Lambda 가 날씨 캐시 테이블(busan-guide-cache)에 B 의 get_weather 가 쓰는 동작만 할 수 있는지
- AgentCore Runtime 에 공공데이터 키가 NoEcho 파라미터로만 들어가는지
- 배포 스크립트가 키 값을 화면에 쓰지 않는지
"""

import re
from pathlib import Path

import pytest

from app import config
from app.tools import lookup

yaml = pytest.importorskip("yaml")
from test_api_deploy import load_template  # noqa: E402  CloudFormation 태그를 읽는 로더를 같이 쓴다

ROOT = Path(__file__).resolve().parents[2]
ALERTS = ROOT / "infra" / "alerts" / "template.yaml"
AGENT = ROOT / "infra" / "template.yaml"
BASE = ROOT / "infra" / "base" / "template.yaml"
SCRIPTS = ROOT / "infra" / "scripts"
TABLE_ARN = "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/"


def alerts_statements() -> dict[str, dict]:
    role = load_template(ALERTS)["Resources"]["CheckRole"]["Properties"]
    return {s["Sid"]: s for s in role["Policies"][0]["PolicyDocument"]["Statement"]}


def config_default(name: str) -> str:
    """config.py 에 적힌 기본값 (환경 변수와 무관하게 소스에서 읽는다)."""
    source = Path(config.__file__).read_text(encoding="utf-8")
    return re.search(rf'os\.environ\.get\("{name}", "([^"]*)"\)', source).group(1)


# ---- 예약 점검 Lambda: 날씨 캐시 ----


def test_scheduled_check_can_read_and_write_the_weather_cache_only():
    cache = alerts_statements()["WeatherCache"]
    assert set(cache["Action"]) == {"dynamodb:GetItem", "dynamodb:PutItem"}
    assert cache["Resource"] == {"Fn::Sub": TABLE_ARN + "busan-guide-cache"}


def test_weather_cache_permission_matches_the_table_the_code_uses():
    base_table = load_template(BASE)["Resources"]["CacheTable"]["Properties"]["TableName"]
    assert config_default("CACHE_TABLE") == base_table == "busan-guide-cache"
    env = load_template(ALERTS)["Resources"]["CheckFunction"]["Properties"]["Environment"]["Variables"]
    assert "CACHE_TABLE" not in env  # 기본값을 그대로 쓴다. 권한의 테이블 이름과 어긋나지 않게 따로 넘기지 않는다
    used = set(re.findall(r"_cache_table\(\)\.(\w+)\(", Path(lookup.__file__).read_text(encoding="utf-8")))
    assert used == {"get_item", "put_item"}  # 권한(GetItem·PutItem)과 코드가 같다


def test_scheduled_check_keeps_its_sessions_table_permissions():
    sessions = alerts_statements()["PlansAndAlerts"]
    assert set(sessions["Action"]) == {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"}
    assert sessions["Resource"] == {"Fn::Sub": TABLE_ARN + "${DynamoDbTable}"}


# ---- AgentCore Runtime: 공공데이터 키 ----


def test_agentcore_runtime_gets_the_data_key_as_a_noecho_parameter():
    template = load_template(AGENT)
    param = template["Parameters"]["DataGoKrKey"]
    assert param["NoEcho"] is True and param["Default"] == ""
    env = template["Resources"]["AgentRuntime"]["Properties"]["EnvironmentVariables"]
    assert env["DATA_GO_KR_KEY_DECODING"] == {"Ref": "DataGoKrKey"}
    assert {"BEDROCK_MODEL_ID", "FAKE_LLM", "DYNAMODB_TABLE"} <= set(env)  # 기존 환경 변수는 그대로


def test_agentcore_role_already_covers_the_weather_cache_through_the_base_policy():
    role = load_template(AGENT)["Resources"]["AgentExecutionRole"]["Properties"]
    assert {"Ref": "DataAccessPolicyArn"} in role["ManagedPolicyArns"]
    policy = load_template(BASE)["Resources"]["DataAccessPolicy"]["Properties"]["PolicyDocument"]
    dynamo = next(s for s in policy["Statement"] if s["Sid"] == "DynamoDbReadWrite")
    assert {"dynamodb:GetItem", "dynamodb:PutItem"} <= set(dynamo["Action"])
    assert {"Fn::GetAtt": "CacheTable.Arn"} in dynamo["Resource"]


# ---- 배포 스크립트: 키 전달 ----


@pytest.mark.parametrize("script", ["deploy.ps1", "deploy_alerts.ps1", "deploy_api.ps1"])
def test_deploy_scripts_pass_the_key_only_when_set_and_never_print_it(script):
    path = SCRIPTS / script
    text = path.read_text(encoding="utf-8-sig")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # PowerShell 5.1 이 한국어를 읽으려면 BOM 이 필요하다
    assert "[string]$DataGoKrKey = $env:DATA_GO_KR_KEY_DECODING" in text
    assert 'if ($DataGoKrKey) { $Overrides += "DataGoKrKey=$DataGoKrKey" }' in text
    assert "--parameter-overrides $Overrides" in text
    printing = [line for line in text.splitlines() if re.search(r"Write-(Host|Output|Warning)|\becho\b", line, re.I)]
    assert not any("$DataGoKrKey" in line and "-not $DataGoKrKey" not in line for line in printing)


def test_no_data_key_value_is_committed_in_infra():
    for path in (ROOT / "infra").rglob("*"):
        if path.is_file() and path.suffix in {".yaml", ".toml", ".ps1", ".py", ".md"} and "build" not in path.parts:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            assert not re.search(r"DATA_GO_KR_KEY_DECODING\s*[=:]\s*['\"]?[A-Za-z0-9%+/]{20,}", text), path
