# Run all Part-4 experiments in order; one log per script in experiments/_logs/.
# Usage:  .\scripts\run_experiments.ps1     (from Cloud_Project/)
$ErrorActionPreference = "Continue"
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$root = Join-Path $PSScriptRoot ".."
$logDir = Join-Path $root "experiments\_logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

$order = @(
    @("a_model_comparison", "run_model_comparison.py"),
    @("e_ablation",         "run_ablation.py"),
    @("b_latency",          "run_latency.py"),
    @("c_throughput",       "run_throughput.py"),
    @("d_cost_model",       "run_cost_model.py")
)

$failed = @()
foreach ($entry in $order) {
    $name, $script = $entry
    Write-Host "=== $script ===" -ForegroundColor Cyan
    & $py (Join-Path $root "experiments\$script") 2>&1 | Tee-Object -FilePath (Join-Path $logDir "$name.log")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $script (exit $LASTEXITCODE)" -ForegroundColor Red
        $failed += $script
    }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "All experiments completed. See experiments/RESULTS_SUMMARY.md" -ForegroundColor Green
} else {
    Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
