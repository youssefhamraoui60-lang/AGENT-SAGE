param([switch]$Live)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
Push-Location (Join-Path $root 'backend')
try {
    & $python ..\scripts\step2_admin.py migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migration verification failed' }
    $env:RUN_STEP2_INTEGRATION='1'
    & $python -m pytest tests -q --junitxml=..\logs\step2-pytest.xml
    if ($LASTEXITCODE -ne 0) { throw 'Step 2 tests failed' }
} finally { Pop-Location }
if ($Live) {
    Push-Location $root
    try {
        foreach ($name in @('test_step2_live.py','test_step2_n8n.py','test_step2_persistence.py')) {
            & $python (Join-Path 'scripts' $name)
            if ($LASTEXITCODE -ne 0) { throw "Live test failed: $name" }
        }
    } finally { Pop-Location }
}
