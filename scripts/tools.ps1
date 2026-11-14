$toolRoot = Join-Path $env:LOCALAPPDATA 'AGENT-SAGE-X3-tools'
$extraPaths = @("$toolRoot\mingit\cmd", "$toolRoot\node-v24.20.0-win-x64", "$env:LOCALAPPDATA\Programs\Ollama", "$env:LOCALAPPDATA\Programs\Python\Python312", "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts")
foreach ($item in $extraPaths) { if (Test-Path $item) { $env:PATH = "$item;$env:PATH" } }
$pythonRegistry=Get-ItemProperty 'HKCU:\Software\Python\PythonCore\*\InstallPath' -ErrorAction SilentlyContinue
foreach($installedPython in $pythonRegistry){if(Test-Path $installedPython.ExecutablePath){$env:PATH="$(Split-Path $installedPython.ExecutablePath);$env:PATH"}}
