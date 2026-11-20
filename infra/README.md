# infra/ 배포 구성 (담당 A)

1단계: SAM 으로 AgentCore Runtime 에 Strands "Hello" 에이전트를 배포한다. 리전은 `ap-northeast-2`.

## 구성

| 파일 | 역할 |
|---|---|
| `template.yaml` | 실행 역할 + `AWS::BedrockAgentCore::Runtime`(코드 zip 방식, Python 3.13) |
| `agentcore/main.py` | Runtime 진입점. delta → done/error 이벤트를 yield 한다 |
| `agentcore/requirements.txt` | zip 에 넣을 의존성 |
| `scripts/build_zip.py` | arm64 wheel 로 `build/deployment_package.zip` 생성 (`backend/app` 의 `config.py`, `models/`만 포함) |
| `scripts/deploy.ps1` | zip 빌드 → S3 업로드 → `sam deploy` |
| `scripts/invoke_hello.py` | 배포한 Runtime 호출, 계약 SSE 형식으로 출력 |

`CodeKey` 에 zip 해시를 넣는다. CloudFormation 은 S3 객체 내용 변경을 감지하지 못해서, 키가 같으면 코드를 올려도 Runtime 이 업데이트되지 않는다.

## 사전 준비 (한 번)
1. SAM CLI 설치: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
2. AWS 자격 증명 설정 (`aws sts get-caller-identity` 가 되어야 한다)
3. 배포 권한: CloudFormation, IAM 역할 생성, S3, `bedrock-agentcore:*` (대회 계정에서 확인)

## 로컬 확인 (AWS 불필요)
```powershell
cd backend
$env:PYTHONPATH="."; $env:FAKE_LLM="1"
uv run --with bedrock-agentcore python ../infra/agentcore/main.py     # 포트 8080
# 다른 터미널
curl.exe -N -X POST http://localhost:8080/invocations -H "Content-Type: application/json" -d '{\"message\":\"Hello\"}'
```
`data: {"event": "delta", ...}` 줄들이 오고 `done` 으로 끝나면 정상이다.

## 배포 (AgentCore)
```powershell
cd infra
.\scripts\deploy.ps1 -FakeLlm 1    # 1) Bedrock 없이 배포 경로만 확인
uv run --no-project --with boto3 --with "botocore[crt]" python scripts/invoke_hello.py <출력된 ARN>
.\scripts\deploy.ps1               # 2) 실제 모델 (BEDROCK_MODEL_ID, 없으면 기본값)
uv run --no-project --with boto3 --with "botocore[crt]" python scripts/invoke_hello.py <ARN> "안녕"
```
기대 출력: `event: delta` 여러 개, 마지막 `event: done`(`answer` = delta 이어 붙인 문장). 종료 코드 0.

로그: CloudWatch `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`.
삭제: `aws cloudformation delete-stack --stack-name busan-guide-agent --region ap-northeast-2`

## 알아둘 점
- **SSE 형식**: AgentCore SDK 는 yield 한 값을 `data: <json>` 줄로만 내보낸다. 그래서 이벤트 이름은 JSON 의 `event` 필드에 넣었다.
  api-contract 의 `event: delta` 줄 형식으로 바꾸는 일은 브라우저 앞단이 해야 한다.
- **브라우저는 Runtime 을 직접 호출할 수 없다.** `InvokeAgentRuntime` 은 SigV4(IAM)가 필요하다. 프론트엔드가 쓰려면 앞단(Lambda 등)이나 JWT 인바운드 인증(Cognito 등)이 필요하다. 2단계에서 정한다.
- 관측성(`aws-opentelemetry-distro`)은 넣지 않았다. 필요하면 `requirements.txt` 에 추가하고 `EntryPoint` 를 `[opentelemetry-instrument, main.py]` 로 바꾼다.

## 대안 경로: Lambda + Function URL (금 12:00 점검 1 전환용)
AgentCore 가 안 될 때 `template.yaml` 에 `AWS::Serverless::Function` 을 추가해 전환한다. `AgentRuntime`, `AgentExecutionRole` 은 지운다.

- 핸들러 `app.handler.handler`, 런타임 `python3.13`, `CodeUri: ../backend`, `FunctionUrlConfig: AuthType NONE` + CORS(`AllowOrigins` 에 프론트 도메인). 환경 변수 `BEDROCK_MODEL_ID`, `FAKE_LLM`, `USE_MOCK`. 정책 `bedrock:InvokeModel*`.
- 이 경로의 `/chat` 은 `Accept: text/event-stream` 이 없는 한 계약상 `ChatResponse` JSON 한 번에 응답이라 **스트리밍 없이 먼저 동작**한다.
- Python 관리형 런타임은 응답 스트리밍을 기본 지원하지 않는다(Node.js 만). SSE 가 꼭 필요하면 Lambda Web Adapter + 별도 HTTP 서버가 필요하고, 이는 `backend/` 변경이므로 담당자와 정한다.
- 이후 API Gateway HTTP API(payload v2.0)로 옮길 때도 같은 핸들러를 쓴다.
- 두 경로가 같은 스택에서 공존할 수 없는 것은 아니므로, 전환 전까지 AgentCore 리소스는 그대로 두고 Lambda 만 추가해 비교해도 된다.

## DynamoDB 연결 (busan-guide-base)
일정·세션은 `busan-guide-base` 스택의 테이블 `busan-guide-sessions`(키 `pk`, `sk`)에 저장한다. 이 스택은 수정하지 않는다.
- `deploy.ps1` 이 `busan-guide-base` Outputs 에서 `DataAccessPolicyArn`, `SessionsTableName` 을 조회해 `template.yaml` 파라미터로 넘긴다.
- 실행 역할(`AgentExecutionRole`)에 `ManagedPolicyArns` 로 `busan-guide-data-access` 가 붙고, 런타임 환경 변수 `DYNAMODB_TABLE` 이 들어간다.
- 이 정책은 base 스택의 S3·DynamoDB 3개 테이블 전체 권한을 포함한다. 저장소 코드는 `busan-guide-sessions` 에 `GetItem`, `PutItem`, `UpdateItem` 만 쓴다.
- 런타임 zip 에 `app/storage` 는 아직 넣지 않았다(`build_zip.py` 의 `APP_ALLOWLIST`). Hello 에이전트가 저장소를 쓰기 시작할 때 추가한다.

읽기 전용 확인:
```powershell
aws sts get-caller-identity --region ap-northeast-2
aws cloudformation describe-stacks --stack-name busan-guide-base --region ap-northeast-2 --query "Stacks[0].Outputs[?OutputKey=='DataAccessPolicyArn'||OutputKey=='SessionsTableName'].[OutputKey,OutputValue]" --output text
aws cloudformation describe-stack-resources --stack-name busan-guide-agent --region ap-northeast-2 --query "StackResources[?ResourceType=='AWS::IAM::Role'].PhysicalResourceId" --output text
aws iam list-attached-role-policies --role-name <위에서 나온 역할 이름>
```
실제 DynamoDB 저장소 테스트(매번 새 ID `plan-itest-*` 를 쓰고 끝나면 지운다): `backend/tests/test_storage_aws.py` 머리말 참고.

## HTTPS API (infra/api)
프론트엔드가 부르는 API 는 별도 스택 `busan-guide-api` 다. Lambda 하나(`app.handler.handler`)가 모든 경로를 처리하고 Function URL 로 공개한다.
`/chat` 은 같은 Lambda 안에서 `run_chat()` 이 Bedrock 을 부르며, JSON 을 한 번에 돌려준다(스트리밍 없음). 위 AgentCore 스택은 Hello 그대로 둔다.
- 배포: `.\scripts\deploy_api.ps1 -ReviewOnly` 로 변경 세트를 확인한 뒤 `.\scripts\deploy_api.ps1`. 자세한 내용은 `infra/api/README.md`.

## 예약 점검 (infra/alerts)
Guardian 예약 점검(EventBridge Scheduler → Lambda → DynamoDB sk=ALERTS → `GET /alerts`)은 별도 스택 `busan-guide-alerts` 다. 템플릿·배포 순서·수동 호출 확인은 `infra/alerts/README.md` 를 본다.
- AgentCore 스택, 공용 스택과 따로 배포하므로 서로 영향을 주지 않는다. 스케줄은 기본 DISABLED 다.
- 배포: `.\scripts\deploy_alerts.ps1 -ReviewOnly` 로 변경 세트를 확인한 뒤 `.\scripts\deploy_alerts.ps1`.