# AgentCore Runtime(Hello) 배포: zip 빌드 -> S3 업로드 -> sam deploy
# 실행 (infra/ 에서): .\scripts\deploy.ps1 [-FakeLlm 1] [-ModelId <id>] [-DataGoKrKey <키>] [-ReviewOnly]
# -DataGoKrKey: 공공데이터포털 Decoding 키. 기본값은 환경 변수 DATA_GO_KR_KEY_DECODING. NoEcho 파라미터라 sam·CloudFormation 출력에
#               보이지 않고 런타임 환경 변수로만 들어간다. 다시 읽을 수 없어서 배포할 때마다 넘겨야 한다(빠뜨리면 빈 값이 된다).
# -ReviewOnly: zip 업로드와 변경 세트 생성까지만 하고 스택은 바꾸지 않는다. 교체(Replacement)·삭제(Remove)가 있는지 본 뒤 옵션 없이 다시 실행한다
# 필요: uv, AWS CLI, SAM CLI, 자격 증명(ap-northeast-2 에 배포 권한)
param(
    [ValidateSet("0", "1")] [string]$FakeLlm = "0",
    [string]$ModelId = $(if ($env:BEDROCK_MODEL_ID) { $env:BEDROCK_MODEL_ID } else { "global.anthropic.claude-haiku-5-5" }),
    [string]$DataGoKrKey = $env:DATA_GO_KR_KEY_DECODING,
    [string]$StackName = "busan-guide-agent",
    [switch]$ReviewOnly   # 변경 세트만 만들어 보여 주고 적용하지 않는다
)

$ErrorActionPreference = "Stop"
$Region = "ap-northeast-2"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what 실패 (종료 코드 $LASTEXITCODE)" }
}

$Account = aws sts get-caller-identity --query Account --output text --region $Region
Assert-Ok "자격 증명 확인"
$Bucket = "busan-guide-agentcore-code-$Account-$Region"

# 공용 스택(busan-guide-base)이 만든 데이터 접근 정책 ARN 과 세션 테이블 이름. 값은 코드에 두지 않고 매번 조회한다
function Get-BaseOutput($key) {
    $value = aws cloudformation describe-stacks --stack-name busan-guide-base --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text
    Assert-Ok "busan-guide-base 출력 $key 조회"
    if (-not $value -or $value -eq "None") { throw "busan-guide-base 스택에 $key 출력이 없습니다." }
    return $value.Trim()
}
$PolicyArn = Get-BaseOutput "DataAccessPolicyArn"
$TableName = Get-BaseOutput "SessionsTableName"
Write-Host "데이터 접근 정책: $PolicyArn"
Write-Host "DynamoDB 테이블: $TableName"
if (-not $DataGoKrKey) { Write-Warning "DATA_GO_KR_KEY_DECODING 이 비어 있어 런타임의 날씨 도구가 missing_key 오류를 돌려줍니다." }

# 1) zip 빌드
$buildOut = uv run --no-project python scripts/build_zip.py
Assert-Ok "zip 빌드"
$buildOut | ForEach-Object { Write-Host $_ }
$last = ($buildOut | Select-Object -Last 1)
if ($last -notmatch '^ZIP=(.+) SHA=([0-9a-f]+)$') { throw "build_zip.py 출력 형식이 예상과 다릅니다: $last" }
$ZipPath = $Matches[1]; $Sha = $Matches[2]
$Key = "agent/$Sha.zip"   # 코드가 바뀌면 키도 바뀌어야 CloudFormation 이 Runtime 을 업데이트한다

# 2) 버킷 확인·생성 후 업로드
# 버킷이 없으면 head-bucket 이 실패하는 게 정상이다. PowerShell 5.1 은 Stop 상태에서 stderr 를 종료 오류로 보므로 이 호출만 풀어 둔다
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

# 3) 배포 (template.yaml 은 51,200 바이트 미만이라 버킷 없이도 되지만, 같은 버킷을 재사용한다)
$Overrides = @(
    "CodeBucket=$Bucket", "CodeKey=$Key", "BedrockModelId=$ModelId", "FakeLlm=$FakeLlm",
    "DataAccessPolicyArn=$PolicyArn", "DynamoDbTable=$TableName"
)
if ($DataGoKrKey) { $Overrides += "DataGoKrKey=$DataGoKrKey" }   # 키 값은 화면에 쓰지 않는다 (sam 도 NoEcho 값은 가려서 보여 준다)
$ExtraArgs = @()
if ($ReviewOnly) { $ExtraArgs += "--no-execute-changeset" }
sam deploy `
    @ExtraArgs `
    --template-file template.yaml `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM `
    --s3-bucket $Bucket --s3-prefix sam `
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

$Arn = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text
Assert-Ok "출력 조회"
Write-Host ""
Write-Host "AgentRuntimeArn = $Arn"
Write-Host "확인: uv run --no-project --with boto3 --with "botocore[crt]" python scripts/invoke_hello.py $Arn"
