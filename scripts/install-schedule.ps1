[CmdletBinding()]
param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1') $PythonPath
$script = Join-Path $PSScriptRoot 'run-daily.ps1'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -PythonPath "{1}"' -f $script, $python)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$iranZone = [TimeZoneInfo]::FindSystemTimeZoneById('Iran Standard Time')
$iranDay = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $iranZone).Date
$localTime = [TimeZoneInfo]::ConvertTimeToUtc($iranDay.AddHours(14), $iranZone).ToLocalTime()
$daily = New-ScheduledTaskTrigger -Daily -At $localTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'IranSmartInvestDaily' -User $user -Action $action -Trigger @($logon,$daily) -Settings $settings -Force | Out-Null
Write-Host 'Installed IranSmartInvestDaily for the current Windows user.'
