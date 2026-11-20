# 예약 점검 Lambda + EventBridge Scheduler 배포 (스택 busan-guide-alerts): zip 빌드 -> S3 업로드 -> sam deploy
# 실행 (infra/ 에서): .\scripts\deploy_alerts.ps1 [-ReviewOnly] [-ScheduleState ENABLED|DISABLED] [-DataGoKrKey <키>] [-DemoNow <ISO 시각>]
# -ReviewOnly: zip 업로드와 변경 세트 생성까지만 하고 스택은 바꾸지 않는다. Replacement·Remove 가 있는지 본 뒤 옵션 없이 다시 실행한다.
# -ScheduleState: 처음 배포 기본값은 DISABLED(자동 실행 꺼짐). 지정하지 않으면 이미 배포된 값을 그대로 둔다.
# -DataGoKrKey: 공공데이터포털 Decoding 키. 기본값은 환경 변수 DATA_GO_KR_KEY_DECODING. 값은 Lambda 환경 변수로만 들어가고
#               다시 읽을 수 없어서(NoEcho) 배포할 때마다 넘겨야 한다. 비어 있으면 예보 없이 점검한다.
# 필요: uv, AWS CLI, SAM CLI, 자격 증명(ap-northeast-2 에 배포 권한). 공용 스택 busan-guide-base 가 있어야 한다.
param(
    [ValidateSet("ENABLED", "DISABLED")] [string]$ScheduleState = "DISABLED",
    [string]$DataGoKrKey = $env:DATA_GO_KR_KEY_DECODING,
    [string]$DemoNow = "",
    [string]$StackName = "busan-guide-alerts",
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

# 공용 스택(busan-guide-base)이 만든 세션 테이블 이름. 값은 코드에 두지 않고 매번 조회한다
$TableName = aws cloudformation describe-stacks --stack-name busan-guide-base --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='SessionsTableName'].OutputValue" --output text
Assert-Ok "busan-guide-base 출력 SessionsTableName 조회"
if (-not $TableName -or $TableName -eq "None") { throw "busan-guide-base 스택에 SessionsTableName 출력이 없습니다." }
$TableName = $TableName.Trim()
Write-Host "DynamoDB 테이블: $TableName"

# 스케줄 상태를 지정하지 않았으면 이미 배포된 값을 그대로 둔다 (다시 배포하다 자동 실행이 꺼지거나 켜지지 않게)
if (-not $PSBoundParameters.ContainsKey("ScheduleState")) {
    $ErrorActionPreference = "Continue"   # 스택이 아직 없으면 describe-stacks 가 실패하는 게 정상이다
    $current = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
        --query "Stacks[0].Parameters[?ParameterKey=='ScheduleState'].ParameterValue" --output text 2>$null
    $found = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if ($found -and $current -and $current.Trim() -in "ENABLED", "DISABLED") { $ScheduleState = $current.Trim() }
}
Write-Host "스케줄 상태: $ScheduleState"
if (-not $DataGoKrKey) { Write-Warning "DATA_GO_KR_KEY_DECODING 이 비어 있어 예보 없이 점검합니다 (비 규칙은 건너뜁니다)." }

# 1) zip 빌드
$buildOut = uv run --no-project python scripts/build_alerts_zip.py
Assert-Ok "zip 빌드"
$buildOut | ForEach-Object { Write-Host $_ }
$last = ($buildOut | Select-Object -Last 1)
if ($last -notmatch '^ZIP=(.+) SHA=([0-9a-f]+)$') { throw "build_alerts_zip.py 출력 형식이 예상과 다릅니다: $last" }
$ZipPath = $Matches[1]; $Sha = $Matches[2]
$Key = "alerts/$Sha.zip"   # 코드가 바뀌면 키도 바뀌어야 CloudFormation 이 Lambda 코드를 업데이트한다

# 2) 버킷 확인·생성 후 업로드
$ErrorActionPreference = "Continue"
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
$Overrides = @("CodeBucket=$Bucket", "CodeKey=$Key", "DynamoDbTable=$TableName", "ScheduleState=$ScheduleState")
if ($DataGoKrKey) { $Overrides += "DataGoKrKey=$DataGoKrKey" }
if ($DemoNow) { $Overrides += "DemoNow=$DemoNow" }
$ExtraArgs = @()
if ($ReviewOnly) { $ExtraArgs += "--no-execute-changeset" }
sam deploy `
    @ExtraArgs `
    --template-file alerts/template.yaml `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM `
    --s3-bucket $Bucket --s3-prefix sam-alerts `
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

$Function = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='CheckFunctionName'].OutputValue" --output text
Assert-Ok "출력 조회"
Write-Host ""
Write-Host "점검 Lambda: $Function (스케줄 $ScheduleState)"
Write-Host "수동 호출은 infra/alerts/README.md 의 「수동 호출로 먼저 확인」을 보세요."
