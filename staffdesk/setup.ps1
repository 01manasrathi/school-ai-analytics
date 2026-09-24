$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
    }
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw "Install and start Ollama, then rerun setup.ps1." }
    ollama pull qwen3.5:4b
    if ($LASTEXITCODE -ne 0) { throw "Chat model download failed. Start Ollama and rerun setup.ps1." }
    ollama pull nomic-embed-text:v1.5
    if ($LASTEXITCODE -ne 0) { throw "Embedding model download failed." }
    & ".\.venv\Scripts\python.exe" -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency verification failed." }
    Write-Host "Setup complete. Run .\start.ps1 to open StaffDesk on port 8503. No API keys are required."
}
finally { Pop-Location }
