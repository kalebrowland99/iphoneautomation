# Graceful restart — avoids dropping AirPlay by stopping cleanly first
# Run: powershell -ExecutionPolicy Bypass -File restart.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

try {
    $health = Invoke-RestMethod -Uri "http://localhost:8080/api/health" -TimeoutSec 2
    if ($health.status -eq "ok") {
        Write-Host "Stopping existing server gracefully..." -ForegroundColor Yellow
        Get-CimInstance Win32_Process -Filter "name='python.exe'" |
            Where-Object {
                $_.CommandLine -like '*imouse_farm*' -or
                $_.CommandLine -like '*watch_restart*'
            } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 3
    }
} catch {
    Write-Host "No running server detected, starting fresh..." -ForegroundColor Gray
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "run.ps1")
