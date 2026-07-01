# Start local autoslideshow Next.js app (slideshow-ui/)
param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$UiRoot = Join-Path $ProjectRoot "slideshow-ui"
$LockFile = Join-Path $ProjectRoot "data\slideshow_ui.lock"
$LogFile = Join-Path $ProjectRoot "data\logs\slideshow_ui.log"

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Test-Path $UiRoot)) {
    Write-Error "slideshow-ui/ not found at $UiRoot"
}

function Sync-SlideshowEnv {
    $farmEnv = Join-Path $ProjectRoot ".env"
    $localEnv = Join-Path $UiRoot ".env.local"
    $keys = @(
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "BRAVE_SEARCH_API_KEY",
        "BRAVE_SEARCH_MONTHLY_LIMIT",
        "NUMISTA_API_KEY",
        "FARM_SECRET"
    )
    $lines = @("# Synced from farm .env by scripts/start_slideshow_ui.ps1")
    if (Test-Path $farmEnv) {
        $map = @{}
        Get-Content $farmEnv | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
            $parts = $line -split "=", 2
            $name = $parts[0].Trim()
            $value = $parts[1].Trim().Trim('"').Trim("'")
            if ($name) { $map[$name] = $value }
        }
        foreach ($key in $keys) {
            if ($map.ContainsKey($key) -and $map[$key]) {
                $lines += "$key=$($map[$key])"
            }
        }
    }
    $lines += "PORT=$Port"
    $lines | Set-Content -Path $localEnv -Encoding UTF8
}

function Test-PortListening([int]$ListenPort) {
    $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Stop-SlideshowUi {
    if (Test-Path $LockFile) {
        try {
            $pid = [int](Get-Content $LockFile -ErrorAction Stop)
            if ($pid -gt 0) {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*slideshow-ui*" -and $_.CommandLine -like "*next dev*" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

if (Test-PortListening $Port) {
    Write-Host "Slideshow UI already listening on http://localhost:$Port" -ForegroundColor Green
    exit 0
}

$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) {
    Write-Host "Node.js/npm not found - install Node 20+ for slideshow generation." -ForegroundColor Yellow
    exit 0
}

$logDir = Split-Path $LogFile -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Sync-SlideshowEnv

$nodeModules = Join-Path $UiRoot "node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "Installing slideshow-ui dependencies (first run)..." -ForegroundColor Yellow
    Push-Location $UiRoot
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    } finally {
        Pop-Location
    }
}

Stop-SlideshowUi

Write-Host "Starting slideshow UI on http://localhost:$Port ..." -ForegroundColor Cyan
$logOut = Join-Path $logDir "slideshow_ui.out.log"
$logErr = Join-Path $logDir "slideshow_ui.err.log"
$proc = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev", "--", "-p", "$Port" `
    -WorkingDirectory $UiRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -PassThru

$proc.Id | Set-Content -Path $LockFile -Encoding ASCII

for ($i = 0; $i -lt 90; $i++) {
    if (Test-PortListening $Port) {
        Write-Host "Slideshow UI ready: http://localhost:$Port" -ForegroundColor Green
        exit 0
    }
    if ($proc.HasExited) {
        Write-Host "Slideshow UI exited early - see $logOut and $logErr" -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 1
}

Write-Host "Slideshow UI did not start in time - see $logOut" -ForegroundColor Red
exit 1
