$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
if(!(Test-Path runtime\postgres\PG_VERSION)){throw 'Cluster natif absent; satisfaire le prerequis Microsoft C++, puis executer native_stack.py init'}
if(!(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)){
    & $python scripts\native_stack.py start-ollama
    if($LASTEXITCODE -ne 0){throw 'Ollama start failed'}
}
if(!(Get-NetTCPConnection -State Listen -LocalPort 55432 -ErrorAction SilentlyContinue)){
    & $python scripts\native_stack.py start-pg
    if($LASTEXITCODE -ne 0){throw 'PostgreSQL start failed'}
}
if(!(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)){
    & .\scripts\start.ps1 -BackendOnly
}
if(!(Get-NetTCPConnection -State Listen -LocalPort 5678 -ErrorAction SilentlyContinue)){
    & $python scripts\native_stack.py start-n8n
    if($LASTEXITCODE -ne 0){throw 'n8n start failed'}
}
Write-Host 'Run scripts/test-native-environment.ps1 to verify readiness. Existing listeners were preserved.'
