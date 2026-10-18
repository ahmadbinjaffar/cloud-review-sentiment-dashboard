<#
.SYNOPSIS
  Tear down a deployed stack (opt-in, explicit only).

.DESCRIPTION
  Empties the S3 buckets (SAM cannot delete non-empty buckets), then runs
  `sam delete` for the stack. Nothing runs unless you execute this script.

.EXAMPLE
  .\scripts\teardown.ps1 -StackName reviewpulse-dev -Region us-east-1
#>
param(
    [string]$StackName = "reviewpulse-dev",
    [string]$Region = "us-east-1"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command sam -ErrorAction SilentlyContinue)) { Write-Error "SAM CLI not found."; exit 1 }

Write-Host "[teardown] emptying stack buckets for $StackName ..."
$buckets = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?contains(OutputKey,'BucketName')].OutputValue" --output text
foreach ($bucket in ($buckets -split "\s+")) {
    if ($bucket -and $bucket -ne "None") {
        Write-Host "[teardown] emptying s3://$bucket"
        aws s3 rm "s3://$bucket" --recursive
    }
}

Write-Host "[teardown] deleting stack $StackName ..."
sam delete --stack-name $StackName --region $Region --no-prompts
Write-Host "[teardown] done."
