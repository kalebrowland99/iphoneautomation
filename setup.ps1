# iMouse Farm - one-click setup
# Run: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { return "py" }
    return $null
}

function Install-Python {
    Write-Host "Python not found. Downloading Python 3.12.8..." -ForegroundColor Yellow
    $installer = "$env:TEMP\python-3.12.8-amd64.exe"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" `
        -OutFile $installer -UseBasicParsing
    Write-Host "Installing Python (silent)..." -ForegroundColor Yellow
    $proc = Start-Process -Wait -PassThru -FilePath $installer -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_pip=1"
    )
    if ($proc.ExitCode -ne 0) {
        throw "Python installer exited with code $($proc.ExitCode)"
    }
    $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) {
        throw "Python install completed but python.exe not found at $py"
    }
    return $py
}

$python = Find-Python
if (-not $python) {
    $python = Install-Python
}
Write-Host "Using Python: $python" -ForegroundColor Green
& $python --version

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    & $python -m venv .venv
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e ".[dev]"
& $venvPython -m pip install imouse-xp

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run the app with:  powershell -ExecutionPolicy Bypass -File run.ps1" -ForegroundColor Green
Write-Host "Dashboard:         http://localhost:8080" -ForegroundColor Green
