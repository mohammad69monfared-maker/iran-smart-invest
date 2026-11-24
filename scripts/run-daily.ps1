[CmdletBinding()]
param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$PythonPath = & (Join-Path $PSScriptRoot 'resolve-python.ps1') $PythonPath
$root = Split-Path $PSScriptRoot
Push-Location $root
try {
    # Credentials stay in the local .env file (never in source control).
    $envFile = Join-Path $root '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            if ($line -match '^\s*(#|$)') { continue }
            $separator = $line.IndexOf('=')
            if ($separator -lt 1) { continue }
            $name = $line.Substring(0, $separator).Trim()
            $value = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
            if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
                [Environment]::SetEnvironmentVariable($name, $value)
            }
        }
    }
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8')
    # A single stalled HTTP read used to block the whole run (and the SQLite
    # lock) for hours. Cap the analysis and kill the process tree if it hangs.
    $process = Start-Process -FilePath $PythonPath -ArgumentList '-m', 'engine' -PassThru -NoNewWindow
    if (-not $process.WaitForExit(90 * 60 * 1000)) {
        Write-Warning 'Analysis exceeded 90 minutes; stopping the hung run.'
        try { $process.Kill($true) } catch { }
        $analysisExit = 124
    } else {
        $analysisExit = $process.ExitCode
    }
    & $PythonPath -m engine.notifications publish
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Telegram delivery failed.' }
    exit $analysisExit
} finally { Pop-Location }
