$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
if (!(Test-Path $python)) { throw 'Environnement Python absent: tests IA non executables. Voir logs/ollama-tests.md.' }
Push-Location backend
try { & $python ..\scripts\test_ai.py; if ($LASTEXITCODE -ne 0) { throw 'Echec des tests IA' } } finally { Pop-Location }
