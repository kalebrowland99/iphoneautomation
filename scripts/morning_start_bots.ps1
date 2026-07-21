# Morning start - same idea as androidautomationig tools/morning_start_bots.sh
# Ensures the farm dashboard is up, then kicks Labely generate-and-run (ValCoin chains after).
#
# Prefer installing via: scripts\install_morning_start.ps1
# Manual test: powershell -ExecutionPolicy Bypass -File scripts\morning_start_bots.ps1

param(
    [string]$FarmUrl = "http://127.0.0.1:8080",
    [ValidateSet("labely", "valcoin")]
    [string]$Brand = "labely",
    [int[]]$Slots = @(),
    [switch]$SkipEnsureServer
)

$ErrorActionPreference = "Stop"

$SupportDir = Join-Path $env:LOCALAPPDATA "iMouseFarm"
$LogDir = Join-Path $SupportDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "morning_start.log"

function Resolve-ProjectRoot {
    $candidates = @()
    $rootFile = Join-Path $SupportDir "project_root.txt"
    if (Test-Path $rootFile) {
        $candidates += (Get-Content $rootFile -Raw).Trim()
    }
    $candidates += (Split-Path -Parent $PSScriptRoot)
    $candidates += $PSScriptRoot
    foreach ($c in $candidates) {
        if ($c -and (Test-Path (Join-Path $c "run.ps1"))) {
            return $c
        }
    }
    return $null
}

$ProjectRoot = Resolve-ProjectRoot
if (-not $ProjectRoot) {
    throw "Could not resolve project root (run install_morning_start.ps1 first, or run from the repo)."
}
Set-Location $ProjectRoot

function Write-MorningLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd hh:mm:ss tt"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Get-TelegramCreds {
    # Prefer Application Support copy, then project config/.
    $candidates = @(
        (Join-Path $SupportDir "telegram.yml"),
        (Join-Path $ProjectRoot "config\telegram.yml")
    )
    foreach ($path in $candidates) {
        if (-not (Test-Path $path)) { continue }
        $token = $null
        $chat = $null
        Get-Content $path -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^#') { return }
            if ($line -match '^(telegram-api-token|bot_token)\s*:\s*(.+)$') {
                $token = $Matches[2].Trim().Trim("'").Trim('"')
            }
            elseif ($line -match '^(telegram-chat-id|chat_id)\s*:\s*(.+)$') {
                $chat = $Matches[2].Trim().Trim("'").Trim('"')
            }
        }
        if ($token -and $chat -and ($token -notlike "your-*") -and ($chat -notmatch "your-chat")) {
            return @{ Token = $token; ChatId = $chat }
        }
    }
    if ($env:TELEGRAM_BOT_TOKEN -and $env:TELEGRAM_CHAT_ID) {
        return @{ Token = $env:TELEGRAM_BOT_TOKEN.Trim(); ChatId = $env:TELEGRAM_CHAT_ID.Trim() }
    }
    return $null
}

function Send-Telegram([string]$Message) {
    $creds = Get-TelegramCreds
    if (-not $creds) {
        Write-MorningLog "No telegram credentials - skip"
        return
    }
    try {
        $uri = "https://api.telegram.org/bot$($creds.Token)/sendMessage"
        $body = @{
            chat_id                  = $creds.ChatId
            text                     = $Message
            disable_web_page_preview = $true
        } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $uri -Method POST -ContentType "application/json; charset=utf-8" `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 20 | Out-Null
        Write-MorningLog "Telegram ok"
    } catch {
        Write-MorningLog "Telegram send failed - $($_.Exception.Message)"
    }
}

function Test-FarmHealth {
    try {
        $h = Invoke-RestMethod -Uri "$FarmUrl/api/health" -TimeoutSec 3
        return ($h.status -eq "ok")
    } catch {
        return $false
    }
}

function Ensure-FarmServer {
    if (Test-FarmHealth) {
        Write-MorningLog "Dashboard already up at $FarmUrl"
        return $true
    }
    Write-MorningLog "Dashboard not reachable - starting run.ps1"
    $runPs1 = Join-Path $ProjectRoot "run.ps1"
    if (-not (Test-Path $runPs1)) {
        Write-MorningLog "ERROR: run.ps1 not found at $runPs1"
        return $false
    }
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $runPs1 `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Minimized | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        if (Test-FarmHealth) {
            Write-MorningLog "Dashboard is up."
            return $true
        }
    }
    Write-MorningLog "ERROR: Dashboard still not reachable after start."
    return $false
}

function Get-DefaultSlots {
    try {
        $devices = Invoke-RestMethod -Uri "$FarmUrl/api/devices" -TimeoutSec 15
        $slots = @()
        foreach ($d in $devices) {
            $u = [string]$d.user_name
            if ($u -match '^\d+$' -and -not $d.excluded -and -not $d.disabled) {
                $slots += [int]$u
            }
        }
        return ($slots | Sort-Object -Unique)
    } catch {
        Write-MorningLog "WARN: could not list devices - $($_.Exception.Message)"
        return 1..20
    }
}

function Get-HttpErrorDetail([System.Management.Automation.ErrorRecord]$err) {
    $detail = [string]$err.Exception.Message
    try {
        $resp = $err.Exception.Response
        if (-not $resp -and $err.ErrorDetails) {
            return [string]$err.ErrorDetails.Message
        }
        if ($err.ErrorDetails -and $err.ErrorDetails.Message) {
            $detail = [string]$err.ErrorDetails.Message
        }
        if ($resp -and $resp.GetResponseStream) {
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $bodyText = $reader.ReadToEnd()
            $reader.Close()
            if ($bodyText) { $detail = $bodyText }
        }
    } catch { }
    return $detail
}

function Test-AlreadyRunning([string]$detail) {
    return ($detail -match '(?i)already running')
}

Write-MorningLog "Morning start begin (root=$ProjectRoot brand=$Brand)"

if (-not $SkipEnsureServer) {
    if (-not (Ensure-FarmServer)) {
        Send-Telegram "Morning start failed - dashboard not running."
        exit 1
    }
}

$slotList = @($Slots)
if (-not $slotList.Count) {
    $slotList = @(Get-DefaultSlots)
}
if (-not $slotList.Count) {
    Write-MorningLog "ERROR: no farm slots to run"
    Send-Telegram "Morning - no Farm phones selected"
    exit 1
}

$headers = @{ "Content-Type" = "application/json" }
$secret = $env:FARM_SECRET
if (-not $secret -and (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Get-Content (Join-Path $ProjectRoot ".env") | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^FARM_SECRET\s*=\s*(.+)$') {
            $secret = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
}
if ($secret) {
    $headers["X-Farm-Secret"] = $secret
}

$bodyObj = @{
    brand     = $Brand
    slots     = @($slotList)
    run_batch = $true
}
# Labely morning run also schedules ValCoin for the same phones (warmup/post per profile).
if ($Brand -eq "labely") {
    $bodyObj.valcoin_slots = @($slotList)
}

$body = $bodyObj | ConvertTo-Json -Compress
Write-MorningLog "POST /api/slideshow/generate-and-run slots=$($slotList -join ',')"

try {
    $result = Invoke-RestMethod -Uri "$FarmUrl/api/slideshow/generate-and-run" `
        -Method POST -Headers $headers -Body $body -TimeoutSec 60
} catch {
    $detail = Get-HttpErrorDetail $_
    Write-MorningLog "generate-and-run response - $detail"
    if (Test-AlreadyRunning $detail) {
        $msg = "Morning - farm already running (skipped start)"
        Write-MorningLog "Telegram: $msg"
        Send-Telegram $msg
        exit 0
    }
    Write-MorningLog "ERROR: generate-and-run failed - $detail"
    Send-Telegram ("Morning - nothing started ({0})" -f $detail)
    exit 1
}

$jobId = $result.job.id
$n = $slotList.Count
Write-MorningLog "Job $jobId started (status=$($result.job.status) phase=$($result.job.phase))"
$msg = "Morning - $Brand started ($n phones, job $jobId)"
Write-MorningLog "Telegram: $msg"
Send-Telegram $msg
Write-MorningLog "Morning start finished (job continues in farm server)."
exit 0
