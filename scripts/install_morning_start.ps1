# Install a Windows Scheduled Task that runs every day at 5:00 AM.
# Mirrors androidautomationig tools/install_morning_start.sh (macOS LaunchAgent @ 5:00).
#
# Run once (elevated recommended so the task can run whether you're logged in or not):
#   powershell -ExecutionPolicy Bypass -File scripts\install_morning_start.ps1
#
# Test immediately:
#   powershell -ExecutionPolicy Bypass -File scripts\morning_start_bots.ps1
#   schtasks /Run /TN "iMouseFarm\MorningStart"

param(
    [string]$TaskName = "iMouseFarm\MorningStart",
    [string]$Time = "05:00",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $ProjectRoot "scripts\morning_start_bots.ps1"
$SupportDir = Join-Path $env:LOCALAPPDATA "iMouseFarm"
$LogDir = Join-Path $SupportDir "logs"
$InstalledRunner = Join-Path $SupportDir "morning_start_bots.ps1"

if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    Write-Host "Removed scheduled task $TaskName (if it existed)."
    exit 0
}

if (-not (Test-Path $Runner)) {
    throw "Missing runner: $Runner"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
# UTF-8 with BOM so Windows PowerShell 5.1 parses the installed copy correctly.
$runnerText = Get-Content -Path $Runner -Raw -Encoding UTF8
$utf8Bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($InstalledRunner, $runnerText, $utf8Bom)
# Remember project root for the installed copy (Desktop-safe pattern from android repo).
Set-Content -Path (Join-Path $SupportDir "project_root.txt") -Value $ProjectRoot -Encoding UTF8

# Copy telegram.yml so Task Scheduler can notify without relying only on Desktop paths
# (same idea as androidautomationig copying accounts/*/telegram.yml into Application Support).
$tgSrc = Join-Path $ProjectRoot "config\telegram.yml"
$tgDst = Join-Path $SupportDir "telegram.yml"
if (Test-Path $tgSrc) {
    Copy-Item -Path $tgSrc -Destination $tgDst -Force
    Write-Host "Copied telegram.yml -> $tgDst"
} else {
    Write-Host "No config\telegram.yml yet - copy from config\telegram.yml.example and re-run install to enable alerts."
}

# Wrap so Task Scheduler always has ExecutionPolicy Bypass + absolute paths.
$wrapper = Join-Path $SupportDir "morning_start_wrapper.cmd"
@"
@echo off
cd /d "$ProjectRoot"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstalledRunner" >> "$LogDir\morning_start.task.log" 2>&1
"@ | Set-Content -Path $wrapper -Encoding ASCII

# /SC DAILY /ST 05:00 — local machine time
schtasks /Create /F /TN $TaskName `
    /TR "`"$wrapper`"" `
    /SC DAILY `
    /ST $Time `
    /RL LIMITED `
    /RU "$env:USERNAME"

if ($LASTEXITCODE -ne 0) {
    throw "schtasks /Create failed (exit $LASTEXITCODE). Try running this script as Administrator."
}

Write-Host ""
Write-Host "Installed daily $Time starter (Windows Task Scheduler)."
Write-Host "  Task:    $TaskName"
Write-Host "  Runner:  $InstalledRunner"
Write-Host "  Wrapper: $wrapper"
Write-Host "  Logs:    $LogDir\morning_start.log"
Write-Host ""
Write-Host "Same idea as androidautomationig:"
Write-Host "  tools/install_morning_start.sh  ->  LaunchAgent at 5:00 AM"
Write-Host "  tools/morning_start_bots.sh     ->  hits dashboard API to start farm"
Write-Host ""
Write-Host "Test now:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$InstalledRunner`""
Write-Host "  schtasks /Run /TN `"$TaskName`""
Write-Host ""
Write-Host "Keep the PC awake (or set BIOS/Windows to wake for the task)."
Write-Host "Farm server will auto-start via run.ps1 if it is not already up."
