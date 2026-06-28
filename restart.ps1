# Graceful restart — avoids dropping AirPlay by stopping cleanly first
# Run: powershell -ExecutionPolicy Bypass -File restart.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

try {
    $health = Invoke-RestMethod -Uri "http://localhost:8080/api/health" -TimeoutSec 2
    if ($health.status -eq "ok") {
        Write-Host "Stopping existing server gracefully..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "No healthy server detected, cleaning stale processes..." -ForegroundColor Gray
}

function Stop-FarmProcesses {
    Get-CimInstance Win32_Process -Filter "name='python.exe'" |
        Where-Object {
            $_.CommandLine -like '*imouse_farm*' -or
            $_.CommandLine -like '*watch_restart*'
        } |
        ForEach-Object {
            Write-Host "Stopping PID $($_.ProcessId)..." -ForegroundColor DarkGray
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

Stop-FarmProcesses
Start-Sleep -Seconds 3
Stop-FarmProcesses

$lockFile = Join-Path $ProjectRoot "data\watch_restart.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}

for ($i = 0; $i -lt 20; $i++) {
    $listen = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    if (-not $listen) { break }
    Start-Sleep -Seconds 1
}

Write-Host "Starting server..." -ForegroundColor Cyan
Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ProjectRoot "run.ps1") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

for ($i = 0; $i -lt 45; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8080/api/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            Write-Host "Server is up: http://localhost:8080" -ForegroundColor Green
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
Write-Host "Server did not become healthy in time - check data/logs" -ForegroundColor Red
exit 1
