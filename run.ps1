# iMouse Farm - start the orchestrator + dashboard
# Run: powershell -ExecutionPolicy Bypass -File run.ps1
#      powershell -ExecutionPolicy Bypass -File run.ps1 -NoReload  (no auto-restart)

param(
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found. Running setup first..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "setup.ps1")
}

if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
if (-not (Test-Path "data\screenshots")) { New-Item -ItemType Directory -Path "data\screenshots" | Out-Null }
if (-not (Test-Path "data\logs")) { New-Item -ItemType Directory -Path "data\logs" | Out-Null }

$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
        $parts = $line -split "=", 2
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

if (-not $NoReload) {
    Write-Host "Starting iMouse Farm (dev mode - auto-restart on file changes)..." -ForegroundColor Cyan
    & $venvPython (Join-Path $ProjectRoot "scripts\watch_restart.py")
    exit $LASTEXITCODE
}

Write-Host "Starting iMouse Farm..." -ForegroundColor Cyan
Write-Host "Dashboard: http://localhost:8080" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

& $venvPython -m imouse_farm.main -c config\config.yaml
