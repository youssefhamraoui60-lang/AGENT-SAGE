$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
& $python scripts\native_stack.py stop-n8n
if($LASTEXITCODE -ne 0){throw 'n8n stop refused or failed; PostgreSQL left running'}
if(Test-Path runtime\postgres\PG_VERSION){
    & $python scripts\native_stack.py stop-pg
    if($LASTEXITCODE -ne 0){throw 'PostgreSQL stop failed'}
}
Write-Host 'Native n8n and project PostgreSQL stopped. FastAPI and Ollama preserved.'
