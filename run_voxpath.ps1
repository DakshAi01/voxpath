Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Starting VoxPath frontend and backend..." -ForegroundColor Cyan
Write-Host "Workspace: $workspaceRoot" -ForegroundColor DarkGray

Push-Location $workspaceRoot
try {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "npm.cmd was not found in PATH. Please install Node.js or add npm to PATH."
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python was not found in PATH. Please install Python or add it to PATH."
    }

    npm.cmd run dev
}
finally {
    Pop-Location
}
