<#
.SYNOPSIS
  Build and deploy the serverless review-sentiment pipeline to AWS (opt-in).

.DESCRIPTION
  NOT run automatically — only executes when you run it explicitly with AWS
  credentials configured. Steps:
    1. sanity-checks AWS CLI + SAM CLI
    2. stages a clean Lambda bundle (src/ + lambda-requirements.txt) in .build/
    3. sam build + sam deploy (CAPABILITY_IAM, free-tier-friendly defaults)
    4. syncs the static dashboard to the S3 website bucket
    5. prints API + dashboard URLs

.EXAMPLE
  .\scripts\deploy.ps1 -StackName reviewpulse-dev -Region us-east-1
  .\scripts\deploy.ps1 -SentimentEngine huggingface -HfToken hf_xxx
  .\scripts\deploy.ps1 -SkipDashboardSync
#>
param(
    [string]$StackName = "reviewpulse-dev",
    [string]$Region = "us-east-1",
    [string]$ProjectName = "reviewpulse",
    [ValidateSet("vader", "textblob", "huggingface")]
    [string]$SentimentEngine = "vader",
    [string]$HfToken = "",
    [switch]$SkipDashboardSync
)
$ErrorActionPreference = "Stop"
$infra = Join-Path $PSScriptRoot "..\infrastructure"
Set-Location $infra

# 1. prerequisites
foreach ($tool in @("aws", "sam")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Error "'$tool' CLI not found. See docs/DEPLOYMENT_GUIDE.md (install AWS SAM CLI)."
        exit 1
    }
}
$AccountId = aws sts get-caller-identity --query Account --output text
if (-not $AccountId) { Write-Error "No AWS credentials configured - aborting."; exit 1 }
Write-Host "[deploy] AWS account: $AccountId, region: $Region, stack: $StackName"

# 2. stage a clean Lambda bundle (never packages .venv/data/logs)
$build = Join-Path $infra ".build"
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$build\src" | Out-Null
robocopy (Join-Path $PSScriptRoot "..\src") "$build\src" /E /XD __pycache__ .venv | Out-Null
Copy-Item (Join-Path $infra "lambda-requirements.txt") "$build\requirements.txt"
Write-Host "[deploy] staged bundle at $build (src + requirements.txt only)"

# 3. build + deploy
sam build --template-file template.yaml
$params = @(
    "ProjectName=$ProjectName", "Environment=dev",
    "SentimentEngine=$SentimentEngine", "NeutralThreshold=0.15",
    "LogRetentionDays=14"
)
if ($HfToken) { $params += "HfToken=$HfToken" }
sam deploy --stack-name $StackName --region $Region --resolve-s3 `
    --capabilities CAPABILITY_IAM --no-confirm-changeset `
    --parameter-overrides ($params -join " ")

# 4. dashboard to S3 website bucket
if (-not $SkipDashboardSync) {
    $dashBucket = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='DashboardBucketName'].OutputValue" --output text
    if ($dashBucket) {
        aws s3 sync (Join-Path $PSScriptRoot "..\dashboard") "s3://$dashBucket" --delete
        Write-Host "[deploy] dashboard synced to s3://$dashBucket"
    }
}

# 5. print endpoints
aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?contains(OutputKey,'Url')||contains(OutputKey,'BucketName')].[OutputKey,OutputValue]" `
    --output table
Write-Host "[deploy] done. Everything above stays inside the AWS free tier at this scale."
