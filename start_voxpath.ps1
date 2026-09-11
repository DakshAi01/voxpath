# VoxPath Unified Launch Script
$ErrorActionPreference = "Stop"

Write-Host "--- VoxPath Startup ---" -ForegroundColor Cyan

# 1. Backend dependencies, in a dedicated venv.
# The venv is deliberate: VoxPath previously ran out of a shared environment,
# where an unrelated package (arize-phoenix) pulled in fastmcp-slim 3.x over
# fastmcp 2.x and silently broke the chat agent. Isolation prevents a repeat.
Write-Host "[1/3] Checking backend dependencies..." -ForegroundColor Yellow
$venvPython = "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "      creating backend/.venv ..." -ForegroundColor DarkGray
    python -m venv backend/.venv
}
& $venvPython -m pip install -r backend/requirements.txt --quiet

# 2. Frontend dependencies
Write-Host "[2/3] Checking frontend dependencies..." -ForegroundColor Yellow
if (Test-Path "frontend/package.json") {
    Push-Location frontend
    npm install --silent
    Pop-Location
}

# 3. Start both services
Write-Host "[3/3] Launching frontend and backend..." -ForegroundColor Green
if (-not (Test-Path "node_modules")) {
    npm install --silent
}
npm run dev
