# Launches the Student Analytics & Report Generator dashboard (port 8502).
# The original School AI app stays on 8501, so both can run side by side.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\student_analytics\data\student_summary.csv")) {
    Write-Host "No dataset found - generating it now (this takes about a minute)..." -ForegroundColor Yellow
    python -m student_analytics.generate_dataset
}

Write-Host "Starting the Student Analytics dashboard on http://localhost:8502 ..." -ForegroundColor Cyan
python -m streamlit run student_analytics/dashboard/Home.py --server.port 8502
