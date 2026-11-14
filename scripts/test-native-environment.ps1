param([switch]$TestPersistence)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
$results=[Collections.Generic.List[object]]::new()
function Record($Test,$Status,$Evidence){
    $results.Add([pscustomobject]@{test=$Test;status=$Status;evidence=$Evidence})
    Write-Host "$Status | $Test | $Evidence"
}
foreach($entry in @(
    @('FastAPI','http://127.0.0.1:8000/health'),
    @('FastAPI PostgreSQL','http://127.0.0.1:8000/health/db'),
    @('FastAPI Ollama','http://127.0.0.1:8000/health/ollama'),
    @('n8n PostgreSQL readiness','http://127.0.0.1:5678/healthz/readiness')
)){
    try{$r=Invoke-WebRequest $entry[1] -UseBasicParsing -TimeoutSec 10;Record $entry[0] PASS "HTTP $($r.StatusCode) $($r.Content)"}
    catch{Record $entry[0] FAIL $_.Exception.Message}
}
if(Test-Path runtime\postgres\PG_VERSION){
    Push-Location backend
    try{
        $evidence=& $python ..\scripts\test_database.py prepare 2>&1 | Out-String
        $dbOK=$LASTEXITCODE -eq 0
        if($dbOK){Record 'PostgreSQL schema insertion lecture rollback' PASS $evidence}else{Record 'PostgreSQL schema insertion lecture rollback' FAIL $evidence}
    }finally{Pop-Location}
    if($dbOK -and $TestPersistence){
        $evidence=& $python scripts\native_stack.py restart-pg 2>&1 | Out-String
        if($LASTEXITCODE -eq 0){
            Push-Location backend
            try{
                $evidence=& $python ..\scripts\test_database.py verify 2>&1 | Out-String
                if($LASTEXITCODE -eq 0){Record 'Persistance PostgreSQL apres restart' PASS $evidence}else{Record 'Persistance PostgreSQL apres restart' FAIL $evidence}
            }finally{Pop-Location}
        }else{Record 'Persistance PostgreSQL apres restart' FAIL $evidence}
    }else{Record 'Persistance PostgreSQL apres restart' SKIPPED 'Requiert -TestPersistence et DB operationnelle'}
}else{Record 'Schema PostgreSQL et persistance' SKIPPED 'Cluster natif non initialise'}
if(Test-Path logs\native-workflow-tests.json){
    $workflow=Get-Content logs\native-workflow-tests.json -Raw -Encoding UTF8 | ConvertFrom-Json
    Record 'n8n workflow integration' $workflow.status 'Voir logs/native-workflow-tests.json; preuve du dernier essai'
}else{Record 'n8n workflow integration' SKIPPED 'Workflow de demonstration non teste'}
if(Test-Path logs\native-backup-tests.json){
    $backup=Get-Content logs\native-backup-tests.json -Raw -Encoding UTF8 | ConvertFrom-Json
    Record 'Sauvegarde restauration' $backup.restore 'Voir logs/native-backup-tests.json; preuve du dernier essai'
}else{Record 'Sauvegarde restauration' SKIPPED 'Sauvegarde/restauration non testee'}
Record 'Docker' SKIPPED 'Architecture native Windows retenue; moteur Linux non requis'
$results | ConvertTo-Json -Depth 6 | Set-Content logs\native-environment-tests.json -Encoding UTF8
if($results.status -contains 'FAIL' -or (@($results | Where-Object {$_.status -eq 'SKIPPED' -and $_.test -ne 'Docker'}).Count -gt 0)){exit 1}
