[CmdletBinding()]
param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$PythonPath = & (Join-Path $PSScriptRoot 'resolve-python.ps1') $PythonPath
Push-Location (Split-Path $PSScriptRoot)
try {
    & $PythonPath -m engine
    $analysisExit = $LASTEXITCODE
    & $PythonPath -m engine.notifications publish
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Telegram delivery failed.' }
    exit $analysisExit
} finally { Pop-Location }
