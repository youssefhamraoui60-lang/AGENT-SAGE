Set-Location (Split-Path $PSScriptRoot -Parent)
if(Select-String -LiteralPath '.env' -Pattern '^STACK_MODE=native$' -Quiet){
    Write-Host 'Mode natif Windows: Docker non utilise'
    if(Test-Path runtime\postgres\PG_VERSION){& .\.tools\postgresql-17\pgsql\bin\pg_ctl.exe -D runtime\postgres status}else{Write-Host 'PostgreSQL: cluster non initialise'}
}else{docker compose ps --all}
foreach ($url in 'http://127.0.0.1:8000/health','http://127.0.0.1:8000/health/db','http://127.0.0.1:8000/health/ollama','http://127.0.0.1:5678/healthz/readiness','http://127.0.0.1:11434/api/tags') {
    try { $r=Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5; "$url HTTP $($r.StatusCode)" } catch { "$url FAIL $($_.Exception.Message)" }
}
