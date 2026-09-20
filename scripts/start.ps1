$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$projectPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Run py -3.12 -m venv .venv, then .\.venv\Scripts\python.exe -m pip install -r requirements.txt first.'
}
& $projectPython run.py
