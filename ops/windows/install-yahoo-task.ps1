# Registers the "Fantasy Yahoo Rosters" scheduled task: every hour, as the
# current user (no elevation), it runs
#   python pull_yahoo.py sync --league <n> --apply --log ops\windows\logs\yahoo.log
# through hidden_run.vbs. Yahoo has no transaction feed here, so the sync makes
# the league's rosters, positions and can't-cut flags exactly Yahoo's. Needs the
# Yahoo app keys (pull_yahoo.py auth) or Firefox signed in to Yahoo. Re-run to
# change the interval. Usage: install-yahoo-task.ps1 -League <number>
param(
    [Parameter(Mandatory=$true)][string]$League,   # Yahoo league number (League settings platform_league_id)
    [int]$Minutes = 60,
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'

if (-not $Python) { $Python = (Get-Command python).Source }
$vbs = Join-Path $PSScriptRoot 'hidden_run.vbs'
$tr = "wscript.exe //B //Nologo `"$vbs`" `"$Python`" pull_yahoo.py sync --league $League --apply --log ops\windows\logs\yahoo.log"

schtasks /create /tn "Fantasy Yahoo Rosters" /sc minute /mo $Minutes /tr $tr /f
if ($LASTEXITCODE -ne 0) { throw "schtasks failed with exit code $LASTEXITCODE" }
Write-Host "Registered task: Fantasy Yahoo Rosters (every $Minutes min, current user)"

# Catch up a run missed while asleep, allow battery, kill a hung run after 10 min (default 72 h blocks every later one).
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Set-ScheduledTask -TaskName "Fantasy Yahoo Rosters" -Settings $set | Out-Null
