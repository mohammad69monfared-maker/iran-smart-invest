[CmdletBinding()]
param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1') $PythonPath
$script = Join-Path $PSScriptRoot 'run-bot.ps1'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -PythonPath "{1}"' -f $script, $python)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'IranSmartInvestBot' -User $user -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host 'Installed IranSmartInvestBot for the current Windows user.'
