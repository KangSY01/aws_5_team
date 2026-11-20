# infra/alerts: 예약 점검 스택

스택 이름 `busan-guide-alerts`, 리전 `ap-northeast-2`. AgentCore 스택(`infra/template.yaml`), 공용 스택(`infra/base`)과 별개이며 서로 수정하지 않는다.
**이 폴더는 아직 AWS에 배포하지 않았다.** 아래 순서로 수동 호출 확인을 먼저 하고, 그 뒤에 스케줄을 켠다.

## 흐름

```
EventBridge Scheduler (cron, Asia/Seoul)
  → Lambda busan-guide-alerts-check   (app.scheduled_handler.handler, LLM 미사용)
      저장된 일정 읽기 (DynamoDB sk=META) → guardian.scheduled.run_scheduled_check (D) → 결과 저장 (sk=ALERTS)
  → GET /alerts?plan_id=<plan_id>      (handler.py, 저장된 결과를 읽기만 한다)
```

해결안은 만들지 않는다. 배지를 누르면 프론트엔드가 `POST /plan/check` 로 해결안을 받는다.
방문일이 예보 범위(오늘~3일 뒤) 밖인 일정은 D 의 `run_scheduled_check` 가 건너뛴다. 이 스택은 날짜를 거르지 않는다.

## 만들어지는 리소스

| 종류 | 이름 | 설명 |
|---|---|---|
| Lambda | `busan-guide-alerts-check` | Python 3.13, arm64, 512MB, 제한 시간 300초. 코드는 S3 zip |
| Logs | `/aws/lambda/busan-guide-alerts-check` | 보관 14일(파라미터) |
| IAM 역할 | `...-CheckRole-...` | Lambda 실행 역할. 아래 최소 권한만 가진다 |
| IAM 역할 | `...-SchedulerRole-...` | EventBridge Scheduler 가 이 Lambda 한 개만 호출하는 역할 |
| Scheduler | `busan-guide-alerts-check` | `cron(15 2,5,8,11,14,17,20,23 * * ? *)`, 타임존 Asia/Seoul, 기본 **DISABLED** |

DynamoDB 테이블은 공용 스택의 `busan-guide-sessions` 를 그대로 쓴다. 이 스택은 테이블을 만들지도 바꾸지도 않는다.

### Lambda 실행 역할 권한 (최소)

| 권한 | 대상 | 용도 |
|---|---|---|
| `dynamodb:GetItem` | `busan-guide-sessions` | 일정 읽기, 일정이 있는지 확인 |
| `dynamodb:Scan` | `busan-guide-sessions` | 점검할 일정 ID 목록 (이벤트에 `plan_ids` 가 없을 때) |
| `dynamodb:PutItem` | `busan-guide-sessions` | 점검 결과(sk=ALERTS) 덮어쓰기 |
| `logs:CreateLogStream`, `logs:PutLogEvents` | 위 로그 그룹 | 로그 |

공용 스택의 `busan-guide-data-access` 정책은 쓰지 않는다 (S3·다른 테이블까지 열려 있어 과하다).

## 파라미터

| 이름 | 기본값 | 설명 |
|---|---|---|
| `CodeBucket`, `CodeKey` | (스크립트가 넣음) | `build_alerts_zip.py` 결과 zip 위치. 키에 해시가 붙어 코드가 바뀌면 Lambda 가 업데이트된다 |
| `DynamoDbTable` | `busan-guide-sessions` | 스크립트가 공용 스택 출력 `SessionsTableName` 으로 채운다 |
| `ScheduleState` | `DISABLED` | `ENABLED` 로 바꾸면 자동 실행. 스크립트는 지정하지 않으면 현재 값을 유지한다 |
| `ScheduleExpression` | `cron(15 2,5,8,11,14,17,20,23 * * ? *)` | 기상청 단기예보 발표 15분 뒤 |
| `DataGoKrKey` | 빈 값 | 공공데이터포털 Decoding 키. Lambda 환경 변수로만 들어간다. 비면 예보 없이 점검한다 |
| `DemoNow` | 빈 값 | 시간 이동 데모용 ISO 시각 (환경 변수 `DEMO_NOW`) |
| `LogRetentionDays` | 14 | 로그 보관 일수 |

## 배포 순서

배포 전에 AWS 자격 증명(`aws sts get-caller-identity`)과 공용 스택 `busan-guide-base` 가 있어야 한다.

```powershell
cd infra
sam validate --lint --template-file alerts/template.yaml --region ap-northeast-2   # 로컬 검증 (AWS 호출 없음)

.\scripts\deploy_alerts.ps1 -ReviewOnly      # 1) 변경 세트만 만든다. 새 스택이라 Add 만 나와야 한다
.\scripts\deploy_alerts.ps1                  # 2) 배포. 스케줄은 DISABLED 로 만들어진다
```

`DATA_GO_KR_KEY_DECODING` 을 환경 변수로 두면 스크립트가 그 값을 Lambda 환경 변수로 넘긴다 (`-DataGoKrKey` 로도 줄 수 있다). 키는 파일이나 커밋에 넣지 않는다.

## 수동 호출로 먼저 확인

스케줄을 켜기 전에 아래 순서로 확인한다. PowerShell 에서 JSON 따옴표를 피하려고 파일로 넘긴다.

```powershell
# 1) 특정 일정만 점검 (수동 데모 실행). now 는 선택이며 없으면 DEMO_NOW → 현재 시각
Set-Content payload.json '{"plan_ids": ["plan-1"], "now": "2026-11-21T09:00:00+09:00"}' -Encoding ascii
aws lambda invoke --function-name busan-guide-alerts-check --region ap-northeast-2 `
    --cli-binary-format raw-in-base64-out --payload file://payload.json out.json
Get-Content out.json        # {"requested": 1, "saved": 1, "results": [...]}

# 2) 저장된 일정 전부 점검 (plan_ids 없음)
Set-Content payload.json '{}' -Encoding ascii
aws lambda invoke --function-name busan-guide-alerts-check --region ap-northeast-2 `
    --cli-binary-format raw-in-base64-out --payload file://payload.json out.json

# 3) 로그 확인
aws logs tail /aws/lambda/busan-guide-alerts-check --region ap-northeast-2 --since 10m

# 4) 저장된 점검 결과 (DynamoDB). 일정 본체(sk=META)는 그대로여야 한다
aws dynamodb get-item --table-name busan-guide-sessions --region ap-northeast-2 `
    --key '{\"pk\":{\"S\":\"PLAN#plan-1\"},\"sk\":{\"S\":\"ALERTS\"}}'
```

`saved` 가 `requested` 보다 작으면 방문일이 예보 범위 밖이라 건너뛴 일정이거나 일정 하나가 실패한 것이다. 실패한 일정 ID 는 로그에 남는다.
`FunctionError` 가 나오면 이벤트 형식 오류(`plan_ids` 가 문자열 목록이 아님 등)나 DynamoDB 접근 오류다.

점검 결과는 API 로도 읽는다: `GET /alerts?plan_id=plan-1` (점검 전이면 `checked_at: null`, `issues: []`).

## 스케줄 켜기·끄기

```powershell
.\scripts\deploy_alerts.ps1 -ScheduleState ENABLED     # 켜기 (콘솔 EventBridge Scheduler 에서도 가능)
.\scripts\deploy_alerts.ps1 -ScheduleState DISABLED    # 끄기. Lambda 와 저장된 결과는 남는다
```

켠 뒤에는 다음 실행 시각(02·05·08·11·14·17·20·23시 15분, 한국 시간)에 로그와 `GET /alerts` 를 한 번 확인한다.

## 삭제

```powershell
aws cloudformation delete-stack --stack-name busan-guide-alerts --region ap-northeast-2
```

Lambda, 스케줄, 역할, 로그 그룹만 지워진다. DynamoDB 의 점검 결과(sk=ALERTS)와 테이블은 남는다.

## 알아둘 점

- 점검 결과 항목에는 만료 시각(`ttl`)을 쓰지 않는다. 테이블에 TTL 이 켜져 있어도 이 항목은 지워지지 않고, 같은 일정을 다시 점검할 때 덮어쓴다.
- 일정 목록은 테이블 Scan 으로 읽는다(페이지 모두). 일정이 많아지면 점검 시간이 늘어난다(제한 시간 300초).
- 실패 알림용 DLQ·CloudWatch 경보는 아직 없다. Scheduler 는 실패 시 2번까지 다시 부른다.
- `DataGoKrKey` 는 CloudFormation 에서 가려지지만(NoEcho) Lambda 콘솔의 환경 변수에는 값이 보인다.
- zip 은 arm64 용이다. 로컬(Windows)에서는 `app.scheduled_handler.handler` 를 직접 불러 테스트한다 (`backend/tests/test_scheduled_handler.py`).
