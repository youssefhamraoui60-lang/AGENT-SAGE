$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$workerPath = Join-Path $projectRoot 'scripts\supplier_mail_worker.py'
$runtimePath = Join-Path $projectRoot 'runtime'
$logPath = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Path $runtimePath,$logPath -Force | Out-Null
$pidPath = Join-Path $runtimePath 'supplier-mail.pid'
if (Test-Path -LiteralPath $pidPath) {
    $workerId = [int](Get-Content -LiteralPath $pidPath)
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId = $workerId" -ErrorAction SilentlyContinue
    if ($existing -and $existing.CommandLine -like '*supplier_mail_worker.py*') {
        Write-Output "Supplier mail worker already running: $workerId"
        exit 0
    }
}
$worker = Start-Process -FilePath $pythonPath -ArgumentList @('-u', $workerPath) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'supplier-mail.stdout.log') -RedirectStandardError (Join-Path $logPath 'supplier-mail.stderr.log') -PassThru
Set-Content -LiteralPath $pidPath -Value $worker.Id
Write-Output "Supplier mail worker started: $($worker.Id)"
