# Offline tests. Synthetic SOAP and human input; no HTTP client or credentials.
#requires -Version 5.1
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
$module=Get-Module SageTestSoap
& $module {
    $script:Root=Join-Path ([IO.Path]::GetTempPath()) ('sage-ps-test-'+[guid]::NewGuid().ToString('N'))
    $script:TestDescription=[IO.File]::ReadAllText((Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\crud-WS_ARTICLE-description.xml'))
    $script:TestSaved=$false;$script:TestCalls=0;$script:TestXml='';$script:TestTimeout=$false
    function script:Invoke-TestSoap($Operation,$Parameters='') {
        switch ($Operation) {
            'getDescription' { return [pscustomobject]@{Status=1;Messages=@();ResultXml=$script:TestDescription} }
            'read' {
                if ($script:TestSaved) { return [pscustomobject]@{Status=1;Messages=@();ResultXml=$script:TestXml} }
                return [pscustomobject]@{Status=0;Messages=@('Fiche inexistante');ResultXml=''}
            }
            'save' {
                $script:TestCalls++;$script:TestSaved=$true
                if ($script:TestTimeout) { throw 'SIMULATED_TIMEOUT_AFTER_COMMIT' }
                return [pscustomobject]@{Status=1;Messages=@('SIMULATED');ResultXml=''}
            }
            default { throw 'UNEXPECTED_OPERATION' }
        }
    }
    function script:Read-Host($Prompt) { return $Prompt.Substring($Prompt.IndexOf('CREER TEST ')) }
}
$plan=New-SageTestArticlePlan -Code SYNTHPS001 -Designation 'SYNTHETIC & TEST'
if ($plan.ObjectXml -notmatch '&amp;') { throw 'XML escaping failed' }
& $module { param($xml) $script:TestXml=$xml.Replace('NAME="PUUSTUCOE">1<','NAME="PUUSTUCOE">1.000<') } $plan.ObjectXml
$null=Invoke-SageTestArticleCreation -Plan $plan -WhatIf
if ((& $module {$script:TestCalls}) -ne 0) { throw 'WhatIf wrote' }
$result=Invoke-SageTestArticleCreation -Plan $plan -Confirm:$false
if ($result.State -ne 'CREATED_AND_READ_BACK' -or -not $result.ReadConfirmed) { throw 'Mock save/read failed' }
try { $null=New-SageTestArticlePlan -Code SYNTHPS001 -Designation 'Duplicate';throw 'Duplicate accepted' }
catch { if ($_.Exception.Message -notmatch 'DUPLICATE_ARTICLE_EXISTS') { throw } }
& $module { $script:TestSaved=$false }
try { $null=Invoke-SageTestArticleCreation -Plan $plan -Confirm:$false;throw 'Replay accepted' }
catch { if ($_.Exception.Message -match 'Replay accepted') { throw } }
if ((& $module {$script:TestCalls}) -ne 1) { throw 'Replay sent another save' }
$tampered=$plan.PSObject.Copy();$tampered.ObjectXml='<PARAM/>'
try { $null=Invoke-SageTestArticleCreation -Plan $tampered -Confirm:$false;throw 'Tamper accepted' }
catch { if ($_.Exception.Message -notmatch 'PLAN_CHANGED_REBUILD_AND_REVIEW') { throw } }
$plan2=New-SageTestArticlePlan -Code SYNTHPS002 -Designation 'SYNTHETIC UNCERTAIN'
& $module { param($xml) $script:TestXml=$xml;$script:TestTimeout=$true } $plan2.ObjectXml
$uncertain=Invoke-SageTestArticleCreation -Plan $plan2 -Confirm:$false
if ($uncertain.State -ne 'SAVE_OUTCOME_UNKNOWN' -or -not $uncertain.ReadConfirmed -or $uncertain.RetryAllowed) { throw 'Uncertain save handling failed' }
& $module { function script:Read-Host($Prompt) { 'NO' };$script:TestSaved=$false }
$plan3=New-SageTestArticlePlan -Code SYNTHPS003 -Designation 'SYNTHETIC DENIED'
try { $null=Invoke-SageTestArticleCreation -Plan $plan3 -Confirm:$false;throw 'Missing approval accepted' }
catch { if ($_.Exception.Message -notmatch 'HUMAN_APPROVAL_NOT_GIVEN') { throw } }
if ((& $module {$script:TestCalls}) -ne 2) { throw 'Unexpected number of synthetic writes' }
& $module { $script:TestSaved=$false;$script:TestTimeout=$false }
$webPlan=New-SageTestArticlePlan -Code TESTSYNTHWEB001 -Designation 'SYNTHETIC WEB APPROVAL'
& $module {param($xml)$script:TestXml=$xml} $webPlan.ObjectXml
$receipt=[pscustomobject]@{Approved=$true;Folder='TEST';Site='202';Code=$webPlan.Code;Digest=$webPlan.Digest;
    DescriptionHash=$webPlan.DescriptionHash;Actor=('chat:'+([guid]::NewGuid().ToString()));ExpiresAt=[DateTimeOffset]::UtcNow.AddMinutes(10).ToString('o')}
try { $null=Invoke-SageTestArticleCreation -Plan $webPlan -ApprovalReceipt $receipt -Confirm:$false;throw 'Other web site accepted' }
catch {if($_.Exception.Message -notmatch 'WEB_HUMAN_APPROVAL_INVALID'){throw}}
if ((& $module {$script:TestCalls}) -ne 2) {throw 'Invalid receipt sent SOAP SAVE'}
$receipt.Site='201'
$webResult=Invoke-SageTestArticleCreation -Plan $webPlan -ApprovalReceipt $receipt -Confirm:$false
if ($webResult.State -ne 'CREATED_AND_READ_BACK' -or (& $module {$script:TestCalls}) -ne 3) {throw 'Bound web approval failed'}
& $module {$script:TestSaved=$false}
$extPlan=New-SageTestArticlePlan -Code EXT_POUDRE -Designation ('Extincteur '+[char]0xe0+' poudre') -SupplierCode F1025 -StockManagement 1
if ($extPlan.ObjectXml -notmatch '<TAB ID="ITP_1"><LIN NUM="1"><FLD NAME="BPSNUM">F1025' -or $extPlan.ObjectXml -notmatch '<FLD NAME="STOMGTCOD">1</FLD>') {throw 'Supplier/stock XML missing'}
& $module {param($xml)$script:TestXml=$xml} $extPlan.ObjectXml
$receipt.Code=$extPlan.Code;$receipt.Digest=$extPlan.Digest;$receipt.DescriptionHash=$extPlan.DescriptionHash
$extResult=Invoke-SageTestArticleCreation -Plan $extPlan -ApprovalReceipt $receipt -Confirm:$false
if ($extResult.State -ne 'CREATED_AND_READ_BACK' -or $extResult.ReadFields['ITP_1[1].BPSNUM'] -cne 'F1025') {throw 'Supplier/stock mock readback failed'}
& $module {$script:TestSaved=$false}
$foamPlan=New-SageTestArticlePlan -Code MFB-A-XPS-40 -Designation 'Modern foam boards A XPS 4 CM' -Unit M2
& $module {param($xml)$script:TestXml=$xml} $foamPlan.ObjectXml
$receipt.Code=$foamPlan.Code;$receipt.Digest=$foamPlan.Digest;$receipt.DescriptionHash=$foamPlan.DescriptionHash;$receipt.Site='201'
try{$null=Invoke-SageTestArticleCreation -Plan $foamPlan -ApprovalReceipt $receipt -Confirm:$false;throw 'FOAM_WRONG_SITE_ACCEPTED'}catch{if($_.Exception.Message -notmatch 'WEB_HUMAN_APPROVAL_INVALID'){throw}}
$receipt.Site='202'
$foamResult=Invoke-SageTestArticleCreation -Plan $foamPlan -ApprovalReceipt $receipt -Confirm:$false
if($foamResult.State -ne 'CREATED_AND_READ_BACK' -or $foamResult.ReadFields['ITM3_1.STU'] -cne 'M2'){throw 'FOAM_M2_READBACK_FAILED'}
[pscustomobject]@{Status='PASS';Mode='OFFLINE_MOCKS_ONLY';Checks=@('XML escaping','WhatIf','SAVE and READ','Duplicate','Permanent replay lock','Tamper','Uncertain outcome readback','Human refusal','Web site restriction','Bound web approval');RealSaves=0} | ConvertTo-Json
