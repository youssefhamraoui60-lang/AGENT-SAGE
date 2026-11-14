#requires -Version 5.1
[CmdletBinding()]param([string]$Code='TESTSOAP003')
$ErrorActionPreference='Stop'
$report=[ordered]@{At=[DateTime]::UtcNow.ToString('o');Transport='Windows PowerShell 5.1 / HttpClient';Code=$Code;Folder='TEST';SaveAttempts=0;RevocationRequired=$null;Status='BLOCKED'}
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
try {
    $report['Connection']=Connect-SageTestSoap
    $report.RevocationRequired=$report.Connection.WindowsRevocationRequired
    $description=Get-SageTestDescription
    $report['DescriptionStatus']=1
    $report['EffectiveUser']=$description.DocumentElement.GetAttribute('USER')
    $report['Read']=Get-SageTestArticle -Code $Code
    $report.Status=if($report.Read.Exists){'READ_CONFIRMED'}else{'ABSENCE_CONFIRMED'}
} catch {
    # Only fixed module error codes are allowed in the public report.
    $code=$_.Exception.Message
    $report['Error']=if($code -cmatch '^[A-Z0-9_]+$'){$code}else{'POWERSHELL_SOAP_FAILED'}
} finally {
    Disconnect-SageTestSoap
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'logs\powershell-module-real-read.json') -Encoding UTF8
    $report | ConvertTo-Json -Depth 8
}
if ($report.Status -eq 'BLOCKED') { exit 1 }
