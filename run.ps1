# Run the LERNA Voice AI service on Windows (PowerShell / VS Code terminal).
#   .\run.ps1
# It creates a venv, installs deps, prepares .env and starts the service on :3000.
# No activation-policy gymnastics: it calls the venv python directly.
$ErrorActionPreference = "stop"
Set-Location $PSScriptRoot

$PY = ".venv\Scripts\python.exe"

# 1) virtualenv (created once)
if (-not (Test-Path $PY)) {
    Write-Host ">> creating .venv ..."
    python -m venv .venv
}

# 2) dependencies
Write-Host ">> installing requirements ..."
& $PY -m pip install --quiet --upgrade pip
& $PY -m pip install --quiet -r requirements.txt

# 3) env (runs with ZERO keys on the offline mock; add real keys to go live)
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host ">> copied .env.example -> .env  (it runs without keys; edit .env to add them)"
}

# 4) run (standalone; set LERNA_INTEGRATION_MODE to auto/inprocess when wired to LERNA)
$env:LERNA_INTEGRATION_MODE = "disabled"
Write-Host ">> starting on http://localhost:3000 ..."
& $PY -m uvicorn app.main:app --host 0.0.0.0 --port 3000
