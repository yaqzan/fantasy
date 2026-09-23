# Fantasy watchdog - keeps the API alive on Windows.
# Registered by install-tasks.ps1 as "Fantasy Watchdog" (every 5 min + at logon).
#
# Probe cheaply FIRST, act only when the API is down. Two modes:
#   -Controller <script>  hand the restart to your own service controller, called as
#                         `<script> start -Service fantasy-api`
#   (no controller)       start `python backend/app.py` itself
# Never capture controller output: its Start-Process children hold inherited
# pipes open (the '| Out-Null' form once wedged a watchdog task for 8+ hours).
#
# Safe to run by hand:  powershell -ExecutionPolicy Bypass -File watchdog.ps1

param(
    [int]$Port = 5001,
    [string]$Controller = '',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Continue'

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$LogDir = Join-Path $PSScriptRoot 'logs'
$LogFile = Join-Path $LogDir 'watchdog.log'

function Write-Log {
    param([string]$Message)
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
}

function Rotate-Log {
    if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 512KB)) {
        $tail = Get-Content $LogFile -Tail 1500
        Set-Content -Path $LogFile -Value $tail
    }
}

function Test-App {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 8
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

Rotate-Log

if (Test-App) {
    Write-Log 'all up'
} elseif ($Controller) {
    Write-Log 'fantasy-api DOWN -> controller start'
    Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $Controller, 'start', '-Service', 'fantasy-api' -WindowStyle Hidden -Wait
    Start-Sleep -Seconds 20
    Write-Log ("post-start: app={0}" -f (Test-App))
} else {
    Write-Log 'fantasy-api DOWN -> python backend/app.py'
    $env:FANTASY_PORT = $Port
    Start-Process $Python -ArgumentList '-u', 'backend\app.py' -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'app.log') -RedirectStandardError (Join-Path $LogDir 'app.err.log')
    Start-Sleep -Seconds 20
    Write-Log ("post-start: app={0}" -f (Test-App))
}
