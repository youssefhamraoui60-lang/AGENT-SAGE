param([long]$ResumeAfter=0)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$backendPython = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$connectPath = Join-Path $PSScriptRoot 'connect.py'
$runtimePath = Join-Path $projectRoot 'runtime\telegram-test'
& $backendPython -X utf8 (Join-Path $PSScriptRoot 'telegram_routing.py') --load
if ($LASTEXITCODE -ne 0) { throw 'Routage SOB approuve indisponible.' }
$running = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*telegram-test*connect.py*' })
if ($running | Where-Object { $_.CommandLine -like '*--routing-policy*' }) {
    Write-Output 'Routed SOB assistant already running.'
    exit 0
}
foreach ($process in $running) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($name in @('assistant-stdout.log','assistant-stderr.log')) {
    $path = Join-Path $runtimePath $name
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $runtimePath ($stamp+'-before-routing-'+$name))
    }
}
$workerArgs=@('-X','utf8','-u',$connectPath,'--assistant','--resume','--api-id','38572478','--routing-policy')
if ($ResumeAfter -gt 0) { $workerArgs+=@('--resume-after',[string]$ResumeAfter) }
$worker = Start-Process -FilePath $pythonPath -ArgumentList $workerArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'assistant-stdout.log') -RedirectStandardError (Join-Path $runtimePath 'assistant-stderr.log') -PassThru
Set-Content -LiteralPath (Join-Path $runtimePath 'assistant.pid') -Value $worker.Id
Write-Output "Routed SOB assistant started: $($worker.Id)"
