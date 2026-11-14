param([switch]$BackendOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if(!$BackendOnly -and (Select-String -LiteralPath '.env' -Pattern '^STACK_MODE=native$' -Quiet)){
    & .\scripts\start-native.ps1
    return
}
if($BackendOnly){
    $python=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
    if(!(Test-Path $python)){throw 'Venv Python absent'}
    if(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue){throw 'Port 8000 deja occupe'}
    $proc=Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path (Get-Location) 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path (Get-Location) 'logs/backend-stdout.log') -RedirectStandardError (Join-Path (Get-Location) 'logs/backend-stderr.log') -PassThru
    $proc.Id | Set-Content logs\backend.pid
    Write-Host "Backend lance, PID $($proc.Id); verifier scripts/status.ps1"
    return
}
docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { throw 'Moteur Docker indisponible. Aucun changement systeme effectue.' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose invalide' }
docker compose up -d --build --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Demarrage incomplet; consulter docker compose logs' }
