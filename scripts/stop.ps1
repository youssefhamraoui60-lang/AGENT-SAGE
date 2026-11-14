param([switch]$BackendOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if(!$BackendOnly -and (Select-String -LiteralPath '.env' -Pattern '^STACK_MODE=native$' -Quiet)){
    & .\scripts\stop-native.ps1
    return
}
if($BackendOnly){
    if(Test-Path logs\backend.pid){
        $backendPid=[int](Get-Content logs\backend.pid)
        $proc=Get-CimInstance Win32_Process -Filter "ProcessId = $backendPid"
        if($proc -and $proc.ExecutablePath -eq (Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe') -and $proc.CommandLine -match 'uvicorn app.main:app'){
            Get-CimInstance Win32_Process -Filter "ParentProcessId = $backendPid" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app'} | ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
            Stop-Process -Id $backendPid
        }elseif($proc){throw 'PID reutilise ou processus different; arret refuse'}
    }
    return
}
docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'Arret incomplet' }
