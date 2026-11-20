# infra/base: 공용 AWS 리소스 스택

스택 이름 `busan-guide-base`, 리전 `ap-northeast-2`. A의 AgentCore 스택(`infra/template.yaml`)과 별개이며 서로 수정하지 않는다.

## 만들어지는 리소스

| 종류 | 이름 | 설명 |
|---|---|---|
| S3 | `busan-guide-web-<계정ID>` | 프론트 정적 파일. CloudFront OAC로만 읽기 |
| S3 | `busan-guide-uploads-<계정ID>` | 사진·녹음·Polly 음성. presigned PUT용 CORS, 1일 후 삭제 |
| S3 | `busan-guide-data-<계정ID>` | 사전 수집 공공데이터 |
| DynamoDB | `busan-guide-sessions`, `busan-guide-cache` | 온디맨드, 키 `pk`(S) + `sk`(S), TTL 속성 `ttl`. sessions 는 A 의 단일 테이블(`pk`=`PLAN#`/`SESSION#`)로 쓴다 |
| Bedrock | `busan-guide-guardrail` + 버전 | 근거 검사(GROUNDING 0.7, RELEVANCE 0.5), 이메일·전화·카드번호 익명화 |
| CloudFront | 배포 1개 | web 버킷 오리진(OAC), 루트 `index.html`, 403·404는 `/index.html`(200), PriceClass_200 |
| IAM | `busan-guide-data-access` | 관리형 정책. 역할에는 붙이지 않고 ARN만 내보낸다 |

모든 버킷은 퍼블릭 액세스 차단, SSE-S3, HTTPS 외 요청 거부 정책이 적용된다. 액세스 키는 만들지 않는다.

## 파라미터

| 이름 | 기본값 | 설명 |
|---|---|---|
| `AllowedOrigin` | `*` | uploads 버킷 CORS 허용 오리진 |

## 배포

```powershell
cd infra/base
sam validate --lint
sam deploy
# 오리진을 지정할 때
sam deploy --parameter-overrides AllowedOrigin=https://<CloudFront 도메인>
```

`samconfig.toml`에 스택 이름, 리전, `CAPABILITY_NAMED_IAM`이 들어 있다. 첫 배포는 변경 세트 확인(`confirm_changeset`)이 나온다.

## 프론트 배포 예시

```powershell
aws s3 sync frontend/dist s3://<WebBucketName> --delete
aws cloudfront create-invalidation --distribution-id <DistributionId> --paths "/*"
```

## 삭제

S3 버킷은 비어 있어야 삭제된다. 먼저 비운 뒤 스택을 지운다.

```powershell
aws s3 rm s3://<WebBucketName> --recursive
aws s3 rm s3://<UploadsBucketName> --recursive
aws s3 rm s3://<DataBucketName> --recursive
sam delete --stack-name busan-guide-base --region ap-northeast-2
```

다른 스택이 Export 값을 가져다 쓰고 있으면 삭제가 거부된다. 그 스택부터 지운다.

## Outputs

모든 Output은 Export 이름이 `busan-guide-base-<키>`이다. 다른 템플릿에서는 `!ImportValue busan-guide-base-<키>`로 가져온다.

| 키 | 설명 |
|---|---|
| `WebBucketName` | 프론트 정적 파일 버킷 이름 |
| `UploadsBucketName` | 업로드 버킷 이름 |
| `DataBucketName` | 공공데이터 버킷 이름 |
| `SessionsTableName` | sessions 테이블 이름 |
| `CacheTableName` | cache 테이블 이름 |
| `GuardrailId` | Bedrock Guardrail ID |
| `GuardrailVersion` | Guardrail 고정 버전 |
| `CloudFrontDomain` | CloudFront 도메인 (`dxxxx.cloudfront.net`) |
| `DistributionId` | CloudFront 배포 ID (캐시 무효화용) |
| `DataAccessPolicyArn` | `busan-guide-data-access` 정책 ARN. 각 Lambda 역할에 직접 붙인다 |

환경 변수 매핑 예: `GuardrailId` → Bedrock 호출의 `guardrailIdentifier`, `GuardrailVersion` → `guardrailVersion`.

## 참고

- Guardrail은 Bedrock 콘솔에서 해당 리전의 접근 권한이 필요할 수 있다.
- uploads 버킷의 `AllowedOrigin=*`는 개발용이다. 운영에서는 CloudFront 도메인으로 좁힌다.