param([switch]$TestPersistence)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
$results=[Collections.Generic.List[object]]::new()
function Record($Test,$Status,$Evidence){
    $results.Add([pscustomobject]@{test=$Test;status=$Status;evidence=$Evidence})
    Write-Host "$Status | $Test | $Evidence"
}
function RemoteTest($Action){
    $evidence=& $python scripts\vm_ops.py $Action 2>&1 | Out-String
    if($LASTEXITCODE -eq 0){Record "VM $Action" PASS $evidence;return $true}
    Record "VM $Action" FAIL $evidence
    return $false
}
if(Test-Path docker\vm.local.json){$vmOK=RemoteTest check}else{
    $vmOK=$false
    Record 'VM docker info' SKIPPED 'VM Ubuntu et acces SSH non fournis; docker/vm.local.json absent'
}
if($vmOK){
    $null=RemoteTest status
    $null=RemoteTest dbcheck
    $null=RemoteTest connectivity
}else{
    foreach($test in 'VM compose up/ps','VM PostgreSQL/n8n','VM n8n vers FastAPI'){
        Record $test SKIPPED 'Acces au moteur Linux requis'
    }
}
foreach($entry in @(
    @('FastAPI','http://127.0.0.1:8000/health'),
    @('FastAPI vers PostgreSQL','http://127.0.0.1:8000/health/db'),
    @('FastAPI vers Ollama','http://127.0.0.1:8000/health/ollama'),
    @('n8n readiness via tunnel','http://127.0.0.1:5678/healthz/readiness')
)){
    try{$r=Invoke-WebRequest $entry[1] -UseBasicParsing -TimeoutSec 8;Record $entry[0] PASS "HTTP $($r.StatusCode) $($r.Content)"}
    catch{Record $entry[0] FAIL $_.Exception.Message}
}
if($vmOK){
    Push-Location backend
    try{
        $proof=& $python ..\scripts\test_database.py prepare 2>&1 | Out-String
        $dbOK=$LASTEXITCODE -eq 0
        if($dbOK){Record 'Tables insertion lecture rollback' PASS $proof}else{Record 'Tables insertion lecture rollback' FAIL $proof}
    }finally{Pop-Location}
    if($TestPersistence -and $dbOK){
        $restarted=RemoteTest restart
        if($restarted){
            Push-Location backend
            try{
                $proof=& $python ..\scripts\test_database.py verify 2>&1 | Out-String
                if($LASTEXITCODE -eq 0){Record 'Persistance PostgreSQL' PASS $proof}else{Record 'Persistance PostgreSQL' FAIL $proof}
            }finally{Pop-Location}
        }else{Record 'Persistance PostgreSQL' FAIL 'Redemarrage des services echoue'}
    }else{Record 'Persistance PostgreSQL' SKIPPED 'Necessite -TestPersistence et test DB reussi'}
    $null=RemoteTest logs
}else{Record 'Tables insertion lecture rollback et persistance' SKIPPED 'Moteur Linux inaccessible'}
Record 'Workflow n8n et persistance workflow' SKIPPED 'Import et execution du workflow puis comparaison avant/apres restart requis; voir docker/UBUNTU-VM.md'
$results | ConvertTo-Json -Depth 5 | Set-Content logs\vm-integration-tests.json -Encoding UTF8
if($results.status -contains 'FAIL' -or $results.status -contains 'SKIPPED'){exit 1}
