param([switch]$SamplePolicies)
$ErrorActionPreference = "Stop"
$previousDataDir = $env:STAFFDESK_DATA_DIR
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Run .\setup.ps1 first." }
    if ($SamplePolicies) {
        $env:STAFFDESK_DATA_DIR = Join-Path $PSScriptRoot "sample_test_data"
        & ".\.venv\Scripts\python.exe" verify_sample.py --prepare-only --workspace $env:STAFFDESK_DATA_DIR
        if ($LASTEXITCODE -ne 0) { throw "Sample PDF indexing failed; existing workspaces were not changed." }
    }
    $env:LANGSMITH_TRACING = "false"
    $env:LANGCHAIN_TRACING_V2 = "false"
    & ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503 --server.maxUploadSize 25 --browser.gatherUsageStats false
}
finally {
    if ($SamplePolicies) { $env:STAFFDESK_DATA_DIR = $previousDataDir }
    Pop-Location
}
