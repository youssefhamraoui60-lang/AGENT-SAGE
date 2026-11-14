$ErrorActionPreference = 'Stop'
$webPython = Join-Path $PSScriptRoot '../backend/.venv/Scripts/python.exe'
& $webPython -X utf8 -m uvicorn web:app --app-dir $PSScriptRoot --host 127.0.0.1 --port 8011
if ($LASTEXITCODE -ne 0) { throw 'Le serveur SOB a échoué.' }
