param([switch]$TestPersistence)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if(Select-String -LiteralPath '.env' -Pattern '^STACK_MODE=native$' -Quiet){
    & .\scripts\test-native-environment.ps1 -TestPersistence:$TestPersistence
    exit $LASTEXITCODE
}
. "$PSScriptRoot\tools.ps1"
$results = [System.Collections.Generic.List[object]]::new()
function Record($Name,$Status,$Evidence) {
    $results.Add([pscustomobject]@{test=$Name;status=$Status;evidence=$Evidence})
    Write-Host "$Status | $Name | $Evidence"
}
function CommandTest($Name,$Command,$Arguments) {
    try {
        $cmd=Get-Command $Command -ErrorAction Stop
        if ($cmd.Source -match 'WindowsApps\\python.exe$') { throw 'Alias Microsoft Store; Python non installe' }
        $out=(& $Command @Arguments 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw $out }
        Record $Name PASS $out
        return $true
    } catch { Record $Name FAIL $_.Exception.Message; return $false }
}
function HttpTest($Name,$Url) {
    try { $r=Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 8; Record $Name PASS "HTTP $($r.StatusCode) $($r.Content)"; return $true }
    catch { Record $Name FAIL $_.Exception.Message; return $false }
}
$pythonOK=CommandTest 'Python' python @('--version')
if ($pythonOK) { $null=CommandTest 'pip' python @('-m','pip','--version') } else { Record 'pip' SKIPPED 'Python absent/bloque' }
$null=CommandTest 'Git' git @('--version')
$null=CommandTest 'Node.js' node @('--version')
$null=CommandTest 'npm' npm.cmd @('--version')
$engineOK=CommandTest 'Docker Engine' docker @('info','--format','{{.OSType}}')
$null=CommandTest 'Docker Compose' docker @('compose','version')
$null=CommandTest 'Compose configuration' docker @('compose','config','--quiet')
$ollamaOK=HttpTest 'Ollama' 'http://127.0.0.1:11434/api/tags'
if($ollamaOK){
    $tags=Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5
    if($tags.models.name -contains 'qwen2.5:7b'){Record 'Modele IA' PASS 'qwen2.5:7b present'} else {Record 'Modele IA' FAIL 'qwen2.5:7b absent'}
} else {Record 'Modele IA' SKIPPED 'Ollama inaccessible'}
$venv=Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
if(Test-Path $venv){
    Push-Location backend
    try {
        & $venv ..\scripts\test_ai.py
        if($LASTEXITCODE -eq 0){Record 'Inference et JSON Python (9 essais)' PASS 'logs/ollama-tests.json'} else {Record 'Inference et JSON Python (9 essais)' FAIL 'logs/ollama-tests.json'}
        if($engineOK){
            & $venv ..\scripts\test_database.py prepare
            $dbOK=$LASTEXITCODE -eq 0
            if($dbOK){Record 'PostgreSQL tables/lecture/rollback' PASS 'Script integration execute'}else{Record 'PostgreSQL tables/lecture/rollback' FAIL 'Script integration echoue'}
        } else {Record 'PostgreSQL tables/lecture/rollback' SKIPPED 'Moteur Docker inaccessible'}
    } finally {Pop-Location}
} else {Record 'Inference et JSON Python (9 essais)' SKIPPED 'Venv Python absent'; Record 'PostgreSQL tables/lecture/rollback' SKIPPED 'Venv Python absent'}
$null=HttpTest 'FastAPI' 'http://127.0.0.1:8000/health'
$null=HttpTest 'PostgreSQL via backend' 'http://127.0.0.1:8000/health/db'
$null=HttpTest 'Connectivite backend vers Ollama' 'http://127.0.0.1:8000/health/ollama'
$null=HttpTest 'n8n et connexion PostgreSQL readiness' 'http://127.0.0.1:5678/healthz/readiness'
if($engineOK -and $TestPersistence -and $dbOK){
    docker compose restart postgres n8n
    $restartOK=$LASTEXITCODE -eq 0
    if($restartOK){
        docker compose up -d --wait --wait-timeout 180
        if($LASTEXITCODE -eq 0){
            Push-Location backend
            try{& $venv ..\scripts\test_database.py verify; if($LASTEXITCODE -eq 0){Record 'Persistance PostgreSQL' PASS 'Marqueur relu apres restart'}else{Record 'Persistance PostgreSQL' FAIL 'Marqueur non relu'}}finally{Pop-Location}
        }else{Record 'Persistance PostgreSQL' FAIL 'Services non sains apres restart'}
    }else{Record 'Persistance PostgreSQL' FAIL 'Restart echoue'}
    Record 'Persistance n8n' SKIPPED 'Necessite workflow importe et verification avant/apres restart dans n8n'
}else{Record 'Persistance PostgreSQL/n8n' SKIPPED 'Necessite moteur, venv, test DB reussi et -TestPersistence'}
if($engineOK){
    $serviceLogs=docker compose logs --no-color --tail 200 2>&1 | Out-String
    if($LASTEXITCODE -ne 0){Record 'Logs critiques' FAIL 'Lecture logs impossible'}
    elseif($serviceLogs -match '(?im)\b(fatal|panic|traceback|error)\b'){Record 'Logs critiques' FAIL 'Motif erreur detecte; examiner docker compose logs'}
    else{Record 'Logs critiques' PASS 'Aucun motif fatal/panic/traceback/error dans les 200 dernieres lignes par service'}
}else{Record 'Logs critiques' SKIPPED 'Moteur Docker inaccessible'}
$results | ConvertTo-Json -Depth 5 | Set-Content logs\environment-tests.json -Encoding UTF8
$lines=@('# Tests environnement','',"Date: $([DateTimeOffset]::Now.ToString('o'))",'')
foreach($row in $results){$lines+="## $($row.test)`n`n$($row.status)`n`n$($row.evidence)`n"}
$lines | Set-Content logs\environment-tests.md -Encoding UTF8
if($results.status -contains 'FAIL'){exit 1}
