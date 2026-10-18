param([switch]$CheckEnvironmentOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $localPython -PathType Leaf)) {
    throw 'Migrated project environment is missing; restore it from the verified migration backup.'
}
& $localPython -B (Join-Path $PSScriptRoot 'check-environment.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Pinned project dependencies are incomplete; application launch is blocked.'
}
if ($CheckEnvironmentOnly) { return }
$previousDirectory = Get-Location
try {
    Set-Location -LiteralPath $projectRoot
    & $localPython -B (Join-Path $projectRoot 'app.py')
    if ($LASTEXITCODE -ne 0) { throw 'Application exited with a nonzero status.' }
} finally {
    Set-Location -LiteralPath $previousDirectory
}
