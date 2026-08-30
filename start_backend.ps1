# Starts the FastAPI backend (School AI) on http://127.0.0.1:8000
Set-Location "$PSScriptRoot\backend"
python -m uvicorn app.main:app --reload --port 8000
