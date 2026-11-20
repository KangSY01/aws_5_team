# AgentCore Runtime(Hello) 배포: zip 빌드 -> S3 업로드 -> sam deploy
# 실행 (infra/ 에서): .\scripts\deploy.ps1 [-FakeLlm 1] [-ModelId <id>]
# 필요: uv, AWS CLI, SAM CLI, 자격 증명(ap-northeast-2 에 배포 권한)
param(
    [ValidateSet("0", "1")] [string]$FakeLlm = "0",
    [string]$ModelId = $(if ($env:BEDROCK_MODEL_ID) { $env:BEDROCK_MODEL_ID } else { "global.anthropic.claude-haiku-5-5" }),
    [string]$StackName = "busan-guide-agent"
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
sam deploy `
    --template-file template.yaml `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM `
    --s3-bucket $Bucket --s3-prefix sam `
    --no-confirm-changeset --no-fail-on-empty-changeset `
    --parameter-overrides "CodeBucket=$Bucket" "CodeKey=$Key" "BedrockModelId=$ModelId" "FakeLlm=$FakeLlm"
Assert-Ok "sam deploy"

$Arn = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text
Assert-Ok "출력 조회"
Write-Host ""
Write-Host "AgentRuntimeArn = $Arn"
Write-Host "확인: uv run --no-project --with boto3 --with "botocore[crt]" python scripts/invoke_hello.py $Arn"
