# HTTPS API Lambda + Function URL 배포 (스택 busan-guide-api): zip 빌드 -> S3 업로드 -> sam deploy
# 실행 (infra/ 에서): .\scripts\deploy_api.ps1 [-ReviewOnly] [-FakeLlm 0|1] [-UseMock 0|1] [-ModelId <id>]
#                     [-AllowedOrigins <오리진,...>] [-AllowLocalhost] [-ReservedConcurrency <n>] [-DataGoKrKey <키>] [-DemoNow <ISO 시각>]
# -ReviewOnly: zip 업로드와 변경 세트 생성까지만 하고 스택은 바꾸지 않는다. Replacement·Remove 가 있는지 본 뒤 옵션 없이 다시 실행한다.
# -FakeLlm 1: Bedrock 을 부르지 않는 고정 응답 (배포 경로만 확인). -UseMock 1: 날씨·음성 샘플 (저장소는 항상 DynamoDB).
# -AllowedOrigins: CORS 허용 오리진. 기본값은 공용 스택(busan-guide-base)의 CloudFront 도메인 https://<도메인>.
# -AllowLocalhost: Vite 개발 서버(http://localhost:5173, http://127.0.0.1:5173)도 허용한다.
# -DataGoKrKey: 공공데이터포털 Decoding 키. 기본값은 환경 변수 DATA_GO_KR_KEY_DECODING. NoEcho 라 다시 읽을 수 없어서
#               배포할 때마다 넘겨야 한다. 비어 있으면 날씨 도구가 missing_key 오류를 돌려준다 (대화는 계속된다).
# 필요: uv, AWS CLI, SAM CLI, 자격 증명(ap-northeast-2 에 배포 권한). 공용 스택 busan-guide-base 가 있어야 한다.
param(
    [ValidateSet("0", "1")] [string]$FakeLlm = "0",
    [ValidateSet("0", "1")] [string]$UseMock = "0",
    [string]$ModelId = $(if ($env:BEDROCK_MODEL_ID) { $env:BEDROCK_MODEL_ID } else { "global.anthropic.claude-haiku-5-5" }),
    [string]$AllowedOrigins = "",
    [switch]$AllowLocalhost,
    [ValidateRange(0, 1000)] [int]$ReservedConcurrency = 0,
    [string]$DataGoKrKey = $env:DATA_GO_KR_KEY_DECODING,
    [string]$DemoNow = "",
    [string]$StackName = "busan-guide-api",
    [switch]$ReviewOnly
)
$ErrorActionPreference = "Stop"
$Region = "ap-northeast-2"
Set-Location (Split-Path $PSScriptRoot -Parent)
function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what 실패 (종료 코드 $LASTEXITCODE)" }
}
$Account = aws sts get-caller-identity --query Account --output text --region $Region
Assert-Ok "자격 증명 확인"
$Bucket = "busan-guide-agentcore-code-$Account-$Region"   # AgentCore 배포가 만든 코드 버킷을 같이 쓴다

# 공용 스택(busan-guide-base)의 출력. 값은 코드에 두지 않고 매번 조회한다
function Get-BaseOutput($key) {
    $value = aws cloudformation describe-stacks --stack-name busan-guide-base --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text
    Assert-Ok "busan-guide-base 출력 $key 조회"
    if (-not $value -or $value -eq "None") { throw "busan-guide-base 스택에 $key 출력이 없습니다." }
    return $value.Trim()
}
$TableName = Get-BaseOutput "SessionsTableName"
$UploadsBucket = Get-BaseOutput "UploadsBucketName"   # 사진 인식이 쓰는 업로드 버킷 (공용 스택이 만든다. 새로 만들지 않는다)
if (-not $AllowedOrigins) { $AllowedOrigins = "https://" + (Get-BaseOutput "CloudFrontDomain") }
$Origins = @($AllowedOrigins -split "," | ForEach-Object { $_.Trim().TrimEnd("/") } | Where-Object { $_ })
if ($AllowLocalhost) { $Origins += "http://localhost:5173", "http://127.0.0.1:5173" }
foreach ($origin in $Origins) {
    if ($origin -eq "*") { throw "AllowedOrigins 에 * 는 쓰지 않습니다. 프론트엔드 오리진을 적어 주세요." }
    if ($origin -notmatch '^https?://[^/\s,]+$') { throw "오리진 형식이 아닙니다: $origin (예: https://d123.cloudfront.net)" }
}
$OriginList = ($Origins | Select-Object -Unique) -join ","

Write-Host "DynamoDB 테이블: $TableName"
Write-Host "사진 업로드 버킷: $UploadsBucket"
Write-Host "CORS 허용 오리진: $OriginList"
Write-Host "모델: $ModelId / FAKE_LLM=$FakeLlm / USE_MOCK=$UseMock (저장소는 DynamoDB) / 예약 동시성: $ReservedConcurrency (0=제한 없음)"
if ($UseMock -eq "0" -and -not $DataGoKrKey) { Write-Warning "DATA_GO_KR_KEY_DECODING 이 비어 있어 날씨 도구가 missing_key 오류를 돌려줍니다 (대화는 계속됩니다)." }

# 1) zip 빌드
$buildOut = uv run --no-project python scripts/build_api_zip.py
Assert-Ok "zip 빌드"
$buildOut | ForEach-Object { Write-Host $_ }
$last = ($buildOut | Select-Object -Last 1)
if ($last -notmatch '^ZIP=(.+) SHA=([0-9a-f]+)$') { throw "build_api_zip.py 출력 형식이 예상과 다릅니다: $last" }
$ZipPath = $Matches[1]; $Sha = $Matches[2]
$Key = "api/$Sha.zip"   # 코드가 바뀌면 키도 바뀌어야 CloudFormation 이 Lambda 코드를 업데이트한다

# 2) 버킷 확인·생성 후 업로드
$ErrorActionPreference = "Continue"   # 버킷이 없으면 head-bucket 이 실패하는 게 정상이다
aws s3api head-bucket --bucket $Bucket --expected-bucket-owner $Account --region $Region 2>&1 | Out-Null
$bucketMissing = ($LASTEXITCODE -ne 0)
$ErrorActionPreference = "Stop"
if ($bucketMissing) {
    Write-Host "버킷 생성: $Bucket"
    aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region | Out-Null
    Assert-Ok "버킷 생성"
}
aws s3 cp $ZipPath "s3://$Bucket/$Key" --region $Region
Assert-Ok "zip 업로드"

# 3) 배포
$Overrides = @(
    "CodeBucket=$Bucket", "CodeKey=$Key", "DynamoDbTable=$TableName", "UploadsBucket=$UploadsBucket", "BedrockModelId=$ModelId",
    "FakeLlm=$FakeLlm", "UseMock=$UseMock", "AllowedOrigins=$OriginList", "ReservedConcurrency=$ReservedConcurrency"
)
if ($DataGoKrKey) { $Overrides += "DataGoKrKey=$DataGoKrKey" }
if ($DemoNow) { $Overrides += "DemoNow=$DemoNow" }
$ExtraArgs = @()
if ($ReviewOnly) { $ExtraArgs += "--no-execute-changeset" }
sam deploy `
    @ExtraArgs `
    --template-file api/template.yaml `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM `
    --s3-bucket $Bucket --s3-prefix sam-api `
    --no-confirm-changeset --no-fail-on-empty-changeset `
    --parameter-overrides $Overrides
Assert-Ok "sam deploy"

if ($ReviewOnly) {
    $ChangeSet = aws cloudformation list-change-sets --stack-name $StackName --region $Region `
        --query "reverse(sort_by(Summaries,&CreationTime))[0].ChangeSetName" --output text
    Assert-Ok "변경 세트 조회"
    Write-Host ""
    Write-Host "변경 세트: $ChangeSet (적용하지 않음)"
    aws cloudformation describe-change-set --stack-name $StackName --change-set-name $ChangeSet --region $Region `
        --query "Changes[].ResourceChange.{Action:Action,Logical:LogicalResourceId,Type:ResourceType,Replacement:Replacement}" --output table
    Assert-Ok "변경 세트 내용 조회"
    Write-Host "Action 이 Remove 이거나 Replacement 가 True/Conditional 이면 적용하지 말고 알려 주세요."
    Write-Host "적용: 같은 값으로 -ReviewOnly 없이 다시 실행. 이 변경 세트를 지우려면: aws cloudformation delete-change-set --stack-name $StackName --change-set-name $ChangeSet --region $Region"
    return
}

$Url = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
Assert-Ok "출력 조회"
Write-Host ""
Write-Host "ApiUrl = $Url"
Write-Host "프론트엔드: VITE_API_BASE_URL=$($Url.Trim().TrimEnd('/'))"
Write-Host "확인 순서는 infra/api/README.md 의 「배포 후 확인」을 보세요."
