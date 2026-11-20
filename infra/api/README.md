# HTTPS API (infra/api, 스택 `busan-guide-api`)

Lambda 하나가 `app.handler.handler` 로 모든 경로를 처리하고 Lambda Function URL(HTTPS)로 공개한다.
`/chat` 은 같은 Lambda 안에서 Strands `run_chat()` 이 Bedrock 을 부른다. `tech.md` 의 대안 경로(Lambda 하나 + Function URL)다.

| 경로 | 처리 |
|---|---|
| `POST /chat` | `run_chat()` (D 프롬프트, B 도구, 일정 생성·부분 수정, 장소 ID·일정 검증, DynamoDB 저장). **ChatResponse JSON 을 한 번에 돌려준다. SSE 스트리밍은 아직 없다** |
| `GET`·`PUT /plan/{plan_id}` | DynamoDB 읽기·저장 |
| `POST /plan/check`, `POST /plan/{plan_id}/delay` | Guardian. 해결안을 저장하지 않는다 |
| `GET /alerts?plan_id=` | 예약 점검(`busan-guide-alerts`)이 저장한 결과 읽기 |
| `POST /speak` | B 의 Polly 음성 출력 (이미 `handler.py` 에 연결되어 있어 함께 배포된다) |

다른 스택과 관계:
- `busan-guide-base`(공용): `SessionsTableName`, `CloudFrontDomain` 출력만 읽는다. 수정하지 않는다.
- `busan-guide-agent`(AgentCore, `infra/template.yaml`): 건드리지 않는다. 코드 버킷 `busan-guide-agentcore-code-<계정>-ap-northeast-2` 만 같이 쓴다(접두사 `api/`, `sam-api`).
- `busan-guide-alerts`(예약 점검): 별개 스택. 같은 테이블을 쓴다.

## 리소스
| 리소스 | 내용 |
|---|---|
| `ApiFunction` | Python 3.13, arm64, 1024MB, 제한 시간 30초(파라미터), 핸들러 `app.handler.handler` |
| `ApiFunctionUrl` (SAM 이 생성) | `AuthType: NONE`, `InvokeMode: BUFFERED`, CORS 는 `AllowedOrigins` 만 |
| 공개 호출 권한 2개 (SAM 이 생성) | `lambda:InvokeFunctionUrl`(`FunctionUrlAuthType=NONE`), `lambda:InvokeFunction`(`InvokedViaFunctionUrl=true`) |
| `ApiRole` | 로그(이 스택 로그 그룹), DynamoDB `GetItem`·`PutItem`·`UpdateItem`(세션 테이블만), 날씨 캐시 `GetItem`·`PutItem`(`busan-guide-cache`만), Bedrock `InvokeModel`·`InvokeModelWithResponseStream`(이 모델·추론 프로필만), Polly `SynthesizeSpeech`, 사진 인식용 S3 `PutObject`·`GetObject`(업로드 버킷의 `photos/*`만)와 `textract:DetectDocumentText` |
| `ApiLogGroup` | `/aws/lambda/busan-guide-api-handler`, 14일 보관, JSON 형식, INFO 이상 |

환경 변수: `BEDROCK_MODEL_ID`, `FAKE_LLM`(기본 0), `USE_MOCK`(기본 0), `STORAGE_BACKEND=dynamodb`(고정), `DYNAMODB_TABLE`,
`UPLOADS_BUCKET`(공용 스택의 `UploadsBucketName`, `deploy_api.ps1` 이 조회해서 넘긴다),
`DATA_GO_KR_KEY_DECODING`(NoEcho 파라미터), `DEMO_NOW`. `AWS_REGION` 은 Lambda 예약 변수라 스택 리전(`ap-northeast-2`)이 들어간다.

- `USE_MOCK=1` 로 배포해도 저장소는 DynamoDB 다. 날씨·음성만 `app/data` 샘플을 쓴다 (실시간 공공데이터 검증 전 통제 테스트).
- `FAKE_LLM=1` 이면 `/chat` 은 `chat_response.json` 고정 응답이다. 그 `plan_id` 는 요청 값이 없으면 샘플 값(`plan-1`)이라 DynamoDB 에 없을 수 있다.

## 배포 (PowerShell, infra/ 에서)
```powershell
cd D:\Coding\aws_5_team\infra
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
.\scripts\deploy_api.ps1 -FakeLlm 1 -AllowLocalhost -ReviewOnly   # 변경 세트만 확인
.\scripts\deploy_api.ps1 -FakeLlm 1 -AllowLocalhost               # 1) Bedrock 없이 배포 경로 확인
.\scripts\deploy_api.ps1 -AllowLocalhost                          # 2) 실제 Bedrock
```
- `-AllowedOrigins` 를 주지 않으면 `https://<busan-guide-base 의 CloudFrontDomain>` 만 허용한다. `-AllowLocalhost` 는 Vite 개발 서버를 더한다.
- `-DataGoKrKey` 는 NoEcho 라 다시 배포할 때 넘기지 않으면 빈 값으로 바뀐다 (기본값은 환경 변수 `DATA_GO_KR_KEY_DECODING`).
- `-ReservedConcurrency 5` 처럼 주면 동시 실행 수를 묶는다. 계정의 예약되지 않은 동시성이 10 이상 남아야 해서 기본은 0(제한 없음)이다.
- 삭제: `aws cloudformation delete-stack --stack-name busan-guide-api --region ap-northeast-2` (테이블은 지워지지 않는다)

## 배포 후 확인
요청 본문은 `docs/api-contract.md` 의 `ChatRequest` 형식이다. PowerShell 5.1 에서 한국어·일본어가 깨지지 않게 본문을 UTF-8 바이트로 보낸다.

```powershell
$Region = "ap-northeast-2"
$Api = (aws cloudformation describe-stacks --stack-name busan-guide-api --region $Region --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text).Trim().TrimEnd("/")
function Invoke-Api($Method, $Path, $Body) {
    $req = @{ Method = $Method; Uri = "$Api$Path"; ContentType = "application/json; charset=utf-8"; TimeoutSec = 60 }
    if ($Body) { $req.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 20 -Compress)) }
    try { Invoke-RestMethod @req } catch {
        $r = $_.Exception.Response
        if ($r) { "HTTP $([int]$r.StatusCode) $($_.ErrorDetails.Message)" } else { throw }
    }
}
$chat = Invoke-Api POST "/chat" @{ message = "Plan a one-day trip in Busan for tomorrow. We like food and the sea."; profile = @{ language = "en"; interests = @("food", "sea"); companions = "couple"; diet = @(); budget = "mid" } }
$chat | ConvertTo-Json -Depth 20
```

로그:
```powershell
aws logs tail /aws/lambda/busan-guide-api-handler --since 30m --region ap-northeast-2
aws logs filter-log-events --log-group-name /aws/lambda/busan-guide-api-handler --region ap-northeast-2 --start-time ([DateTimeOffset]::UtcNow.AddHours(-1).ToUnixTimeMilliseconds()) --filter-pattern '{ $.level = "ERROR" }' --query "events[].message" --output text
```
`대화 처리 실패: code=...`(timeout, model_error, invalid_model_output), `모델 호출 실패: <예외 종류>`, `저장소 오류` 를 찾는다. 사용자 메시지는 로그에 남지 않는다.

## 알아둘 점
- **인증 없음**: 계약에 인증이 없어 Function URL 은 공개(`NONE`)다. CORS 는 브라우저만 막고 curl 같은 직접 호출은 막지 못한다. `/chat` 남용은 Bedrock 비용이 되므로 데모 기간에만 켜 두거나 `-ReservedConcurrency` 로 묶는다. 계정 SCP 가 공개 Function URL 을 막으면 배포 후 403 이 난다.
- **시간**: `/chat` 은 대화 한도 14초(`agent.CHAT_TIMEOUT_SEC`) 뒤 500 `internal_error` 다. Lambda 제한 시간은 30초. 프론트엔드 기본 요청 제한 시간(10초)보다 길 수 있다.
- **스트리밍**: Python 관리형 런타임은 Lambda 응답 스트리밍을 지원하지 않는다. `Accept: text/event-stream` 을 보내도 JSON 이 온다.
- **API Gateway 로 옮길 때**: HTTP API 통합 제한 시간은 최대 30초라 `/chat` 한도와 여유가 작다. 지금은 Function URL 을 쓴다.
