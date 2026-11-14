# Local TEST pilot only. Does not stop/restart the production backend on port 8000.
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
if(Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue){throw 'Port 8001 already in use. Stop the known pilot process first.'}
$previousMcp=$env:SAGE_MCP_ENABLED;$previousScheduler=$env:LEARNING_SCHEDULER_ENABLED;$previousWrites=$env:SAGE_WRITES_ENABLED
try {
 $env:SAGE_MCP_ENABLED='true';$env:LEARNING_SCHEDULER_ENABLED='false'
 $env:SAGE_WRITES_ENABLED='false'
 $process=Start-Process -FilePath (Join-Path $project 'backend/.venv/Scripts/python.exe') -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001' -WorkingDirectory (Join-Path $project 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'mcp-pilot-stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'mcp-pilot-stderr.log') -PassThru
 Write-Output ('MCP TEST pilot starting at http://127.0.0.1:8001/sage/ ; process '+$process.Id)
}finally{
 $env:SAGE_MCP_ENABLED=$previousMcp;$env:LEARNING_SCHEDULER_ENABLED=$previousScheduler;$env:SAGE_WRITES_ENABLED=$previousWrites
}
