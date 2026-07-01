# Tile Google Chrome and iMouseXP side-by-side (50% / 50%) on the primary monitor.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\tile_chrome_imouse.ps1 [-FarmUrl url] [-ChromeSide left|right]

param(
    [string]$FarmUrl = "http://localhost:8080/",
    [ValidateSet("left", "right")]
    [string]$ChromeSide = "left",
    [string]$IMouseTitleContains = "iMouse",
    [int]$WaitSeconds = 2
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Tile {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    public const int SW_RESTORE = 9;
    public const uint SWP_NOZORDER = 0x0004;
    public const uint SWP_SHOWWINDOW = 0x0040;
}
"@

function Set-WindowRect {
    param([IntPtr]$Handle, [int]$X, [int]$Y, [int]$W, [int]$H)
    if ($Handle -eq [IntPtr]::Zero) { return $false }
    [void][Win32Tile]::ShowWindow($Handle, [Win32Tile]::SW_RESTORE)
    return [Win32Tile]::SetWindowPos(
        $Handle,
        [IntPtr]::Zero,
        $X, $Y, $W, $H,
        [Win32Tile]::SWP_NOZORDER -bor [Win32Tile]::SWP_SHOWWINDOW
    )
}

function Find-ChromeWindow {
    $candidates = Get-Process -Name "chrome" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero -and $_.MainWindowTitle }
    if (-not $candidates) { return $null }
    $preferred = $candidates | Where-Object {
        $t = $_.MainWindowTitle
        $t -match "localhost|127\.0\.0\.1|Farm|Slideshow|Labely|ValCoin|Valcoin|automation"
    } | Select-Object -First 1
    if ($preferred) { return $preferred }
    return $candidates | Sort-Object { $_.MainWindowTitle.Length } -Descending | Select-Object -First 1
}

function Find-IMouseWindow {
    $procs = Get-Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.MainWindowHandle -ne [IntPtr]::Zero -and
            $_.MainWindowTitle -and
            ($_.MainWindowTitle -like "*$IMouseTitleContains*" -or $_.ProcessName -like "*imouse*")
        }
    if (-not $procs) { return $null }
    return $procs | Sort-Object { $_.MainWindowTitle.Length } -Descending | Select-Object -First 1
}

function Start-ChromeFarmTab {
    param([string]$Url)
    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    $exe = $paths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        Write-Warning "Google Chrome not found - install Chrome or open the farm dashboard manually."
        return $false
    }
    Start-Process -FilePath $exe -ArgumentList @("--new-window", $Url)
    return $true
}

$wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$halfW = [int][math]::Floor($wa.Width / 2)
$rightW = [int]($wa.Width - $halfW)

if ($ChromeSide -eq "left") {
    $chromeX = [int]$wa.X; $chromeW = $halfW
    $imouseX = [int]($wa.X + $halfW); $imouseW = $rightW
} else {
    $imouseX = [int]$wa.X; $imouseW = $halfW
    $chromeX = [int]($wa.X + $halfW); $chromeW = $rightW
}
$topY = [int]$wa.Y
$height = [int]$wa.Height

$chrome = Find-ChromeWindow
if (-not $chrome) {
    if (Start-ChromeFarmTab -Url $FarmUrl) {
        Start-Sleep -Seconds $WaitSeconds
        $chrome = Find-ChromeWindow
    }
}

$imouse = Find-IMouseWindow

$result = @{
    ok = $true
    chrome = $null
    imouse = $null
    warnings = @()
}

if ($chrome) {
    $ok = Set-WindowRect -Handle $chrome.MainWindowHandle -X $chromeX -Y $topY -W $chromeW -H $height
    $result.chrome = @{
        title = $chrome.MainWindowTitle
        pid = $chrome.Id
        placed = [bool]$ok
        side = $ChromeSide
    }
} else {
    $result.warnings += "Chrome window not found"
}

if ($imouse) {
    $side = if ($ChromeSide -eq "left") { "right" } else { "left" }
    $ok = Set-WindowRect -Handle $imouse.MainWindowHandle -X $imouseX -Y $topY -W $imouseW -H $height
    $result.imouse = @{
        title = $imouse.MainWindowTitle
        pid = $imouse.Id
        placed = [bool]$ok
        side = $side
    }
} else {
    $result.warnings += "iMouseXP window not found (match title: $IMouseTitleContains)"
}

if (-not $result.chrome -and -not $result.imouse) {
    $result.ok = $false
}

$result | ConvertTo-Json -Compress
