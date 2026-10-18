<#
.SYNOPSIS
  Start the review-sentiment pipeline in LOCAL mode (no cloud credentials needed).

.DESCRIPTION
  - creates .venv if missing and installs requirements.txt
  - copies .env.example -> .env on first run
  - seeds data/reviews.db from data/reviews.csv (falls back to the committed
    data/sample_reviews.csv) when the DB is missing (or -Rebuild)
  - runs FastAPI (src/local_server.py); every request goes through the same
    Lambda handler functions that would run on AWS

.EXAMPLE
  .\scripts\run_local.ps1                  # vader + sqlite, seed if empty, port 8000
  .\scripts\run_local.ps1 -Engine textblob # switch sentiment engine
  .\scripts\run_local.ps1 -Rebuild         # wipe DB and reseed
  .\scripts\run_local.ps1 -Port 9000 -NoSeed
#>
param(
    [int]$Port = 8000,
    [ValidateSet("vader", "textblob", "huggingface", "comprehend")]
    [string]$Engine = "vader",
    [ValidateSet("sqlite", "dynamodb")]
    [string]$Storage = "sqlite",
    [switch]$Rebuild,
    [switch]$NoSeed
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) {
    Write-Host "[run_local] creating virtual environment..."
    python -m venv .venv
}
Write-Host "[run_local] installing/updating requirements..."
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[run_local] created .env from .env.example"
}

$env:SENTIMENT_ENGINE = $Engine
$env:STORAGE_BACKEND = $Storage
$env:PYTHONPATH      = (Get-Location).Path

$dbPath = ".\data\reviews.db"
if ($Rebuild -and (Test-Path $dbPath)) {
    Remove-Item $dbPath -Force
    Write-Host "[run_local] removed old database $dbPath"
}

if (-not $NoSeed -and -not (Test-Path $dbPath)) {
    Write-Host "[run_local] seeding database (data/reviews.csv, or sample fallback)..."
    & ".\.venv\Scripts\python.exe" scripts\seed_db.py
}

Write-Host "[run_local] starting server on http://127.0.0.1:$Port  (engine=$Engine, storage=$Storage)"
Write-Host "[run_local] API docs: http://127.0.0.1:$Port/docs   -  Ctrl+C to stop"
& ".\.venv\Scripts\python.exe" -m uvicorn src.local_server:app --host 127.0.0.1 --port $Port
