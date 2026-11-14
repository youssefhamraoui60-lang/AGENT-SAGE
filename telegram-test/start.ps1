$ErrorActionPreference = 'Stop'
$testRoot = $PSScriptRoot
$testPython = Join-Path $testRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $testPython)) {
    $basePython = Join-Path $testRoot '../backend/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $basePython)) { throw 'Python introuvable.' }
    & $basePython -m venv (Join-Path $testRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Création de l’environnement de test impossible.' }
}
& $testPython -m pip install -r (Join-Path $testRoot 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Installation de Telethon impossible.' }
& $testPython (Join-Path $testRoot 'connect.py')
if ($LASTEXITCODE -ne 0) { throw 'Le test Telegram a échoué.' }
