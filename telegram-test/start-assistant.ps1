$ErrorActionPreference = 'Stop'
$testPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $testPython)) { throw 'Lancer start.ps1 une premiere fois pour installer Telethon.' }
& (Join-Path $PSScriptRoot '../backend/.venv/Scripts/python.exe') -X utf8 (Join-Path $PSScriptRoot 'learning_memory.py')
if ($LASTEXITCODE -ne 0) { throw 'Memoire d’apprentissage indisponible.' }
& $testPython -X utf8 (Join-Path $PSScriptRoot 'connect.py') --assistant --routing-policy
if ($LASTEXITCODE -ne 0) { throw 'Assistant Telegram arrete avec une erreur.' }
