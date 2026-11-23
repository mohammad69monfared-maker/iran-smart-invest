[CmdletBinding()]
param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$PythonPath = & (Join-Path $PSScriptRoot 'resolve-python.ps1') $PythonPath
$root = Split-Path $PSScriptRoot
Push-Location $root
try {
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
    # Long polling: the process stays alive and answers commands immediately.
    & $PythonPath -m engine.notifications poll
} finally { Pop-Location }
