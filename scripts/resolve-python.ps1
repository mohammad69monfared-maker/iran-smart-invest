param([string]$PreferredPython)
$candidates = @(
    $PreferredPython
    $env:CODEX_PRIMARY_RUNTIME_PYTHON
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    'python'
    'python3'
)
foreach ($candidate in $candidates) {
    if (!$candidate) { continue }
    $resolved = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$resolved -or $resolved.Source -like '*\Microsoft\WindowsApps\*') { continue }
    & $resolved.Source -c "import sys; sys.exit(sys.version_info < (3,10))" 2>$null
    if ($LASTEXITCODE -eq 0) { return $resolved.Source }
}
throw 'No usable Python 3.10+ interpreter found.'
