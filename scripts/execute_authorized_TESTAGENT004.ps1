#requires -Version 5.1
# Explicit user authorization: one TESTAGENT004 only. Permanent module marker
# prevents any subsequent SAVE for this code, including after an uncertain result.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
$report=[ordered]@{At=[DateTime]::UtcNow.ToString('o');Code='TESTAGENT004';Folder='TEST';SaveAttempts=0;State='PRECHECK'}
try {
    $report['Connection']=Connect-SageTestSoap
    $plan=New-SageTestArticlePlan -Code TESTAGENT004 -Designation 'ARTICLE TEST CREATION AGENT IA' -Category NEG -Unit UN
    $report['Plan']=$plan
    $result=Invoke-SageTestArticleCreation -Plan $plan -AuthorizedTestAgent004 -Confirm:$false
    $report['Result']=$result
    $report.SaveAttempts=$result.SaveAttempts
    $report.State=$result.State
} catch {
    $report.State='BLOCKED_OR_UNCERTAIN_NO_RETRY'
    $message=$_.Exception.Message
    $report['Error']=if($message -cmatch '^[A-Z0-9_]+$'){$message}else{'POWERSHELL_OPERATION_FAILED'}
    $marker=Join-Path $root 'runtime\powershell-soap-attempts\TESTAGENT004.attempt.json'
    if (Test-Path -LiteralPath $marker) {
        $report.SaveAttempts=1
        # Read-only reconciliation; never issue another SAVE.
        try { $report['Reconciliation']=Get-SageTestArticle -Code TESTAGENT004 }
        catch { $report['ReconciliationError']='READBACK_UNAVAILABLE' }
    }
} finally {
    Disconnect-SageTestSoap
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $root 'logs\TESTAGENT004-authorized-powershell-result.json') -Encoding UTF8
    $report | ConvertTo-Json -Depth 12
}
if ($report.State -ne 'CREATED_AND_READ_BACK') { exit 1 }
