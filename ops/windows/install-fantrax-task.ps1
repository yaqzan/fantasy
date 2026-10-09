# Registers the "Fantasy Fantrax Rosters" scheduled task: every hour, as the
# current user (no elevation), it runs
#   python pull_fantrax.py rosters --apply --log ops\windows\logs\fantrax.log
# through hidden_run.vbs (no console flash; cwd = repo root). That prints new
# Fantrax transactions and makes every Fantrax league's rosters exactly
# Fantrax's. An expired login is re-read from Firefox, so stay logged in to
# fantrax.com there. Re-run this script to change the interval.
param(
    [int]$Minutes = 60,
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'

if (-not $Python) { $Python = (Get-Command python).Source }
$vbs = Join-Path $PSScriptRoot 'hidden_run.vbs'
$tr = "wscript.exe //B //Nologo `"$vbs`" `"$Python`" pull_fantrax.py rosters --apply --log ops\windows\logs\fantrax.log"

schtasks /create /tn "Fantasy Fantrax Rosters" /sc minute /mo $Minutes /tr $tr /f
if ($LASTEXITCODE -ne 0) { throw "schtasks failed with exit code $LASTEXITCODE" }
Write-Host "Registered task: Fantasy Fantrax Rosters (every $Minutes min, current user)"
