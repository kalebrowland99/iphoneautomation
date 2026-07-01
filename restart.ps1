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

function Stop-Port8080Listeners {
    Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $procId = [int]$_.OwningProcess
            if ($procId -gt 0) {
                Write-Host "Stopping PID $procId (holding port 8080)..." -ForegroundColor DarkGray
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
}

function Stop-SlideshowUi {
    $uiLock = Join-Path $ProjectRoot "data\slideshow_ui.lock"
    if (Test-Path $uiLock) {
        try {
            $pid = [int](Get-Content $uiLock -ErrorAction Stop)
            if ($pid -gt 0) {
                Write-Host "Stopping slideshow UI PID $pid..." -ForegroundColor DarkGray
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        Remove-Item $uiLock -Force -ErrorAction SilentlyContinue
    }
    Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $procId = [int]$_.OwningProcess
            if ($procId -gt 0) {
                Write-Host "Stopping PID $procId (holding port 3000)..." -ForegroundColor DarkGray
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
}

Stop-FarmProcesses
Stop-Port8080Listeners
Stop-SlideshowUi
Start-Sleep -Seconds 3
Stop-FarmProcesses
Stop-Port8080Listeners
Stop-SlideshowUi

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
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ProjectRoot "run.ps1"), "-NoReload" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8080/api/health" -TimeoutSec 3
        $slideshowUp = $false
        try {
            Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 2 -UseBasicParsing | Out-Null
            $slideshowUp = $true
        } catch {}
        if ($health.status -eq "ok") {
            Write-Host "Server is up: http://localhost:8080" -ForegroundColor Green
            if ($slideshowUp) {
                Write-Host "Slideshow UI: http://localhost:3000" -ForegroundColor Green
            } else {
                Write-Host "Slideshow UI not ready yet - check data/logs/slideshow_ui.log" -ForegroundColor Yellow
            }
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
Write-Host "Server did not become healthy in time - check data/logs" -ForegroundColor Red
exit 1
