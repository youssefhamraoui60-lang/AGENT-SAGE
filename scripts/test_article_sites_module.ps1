# Offline transport mocks only. No credentials and no network/ERP writes.
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'SageTestArticleSites.psm1') -Force
$module=Get-Module SageTestSoap
& $module {
    $script:SiteTestDescription=[IO.File]::ReadAllText((Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\crud-WS_AR_SITE-description.xml'))
    $script:ArticleTestDescription=[IO.File]::ReadAllText((Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\crud-WS_ARTICLE-description.xml'))
    $script:Root=Join-Path ([IO.Path]::GetTempPath()) ('site-module-test-'+[guid]::NewGuid().ToString('N'))
    $script:SiteTestSaved=@{};$script:SiteCalls=0;$script:FailAfterSave=$false
    function script:Invoke-TestSoap($Operation,$Parameters='',$Publication='WS_ARTICLE') {
        if($Operation -eq 'getDescription') {
            return [pscustomobject]@{Status=1;Messages=@();ResultXml=if($Publication -eq 'WS_AR_SITE'){$script:SiteTestDescription}else{$script:ArticleTestDescription}}
        }
        if($Operation -eq 'read' -and $Publication -eq 'WS_ARTICLE') {
            return [pscustomobject]@{Status=1;Messages=@();ResultXml='<RESULT><GRP ID="ITM0_1"><FLD NAME="ITMREF">EXT_POUDRE</FLD><FLD NAME="TCLCOD">NEG</FLD></GRP><GRP ID="ITM3_1"><FLD NAME="STU">UN</FLD></GRP><GRP ID="ITM2_1"><FLD NAME="STOMGTCOD">1</FLD></GRP></RESULT>'}
        }
        if($Publication -ne 'WS_AR_SITE'){throw 'MASTER_WRITE_FORBIDDEN'}
        if($Operation -eq 'save') {
            $script:SiteCalls++
            $outer=[xml]('<root>'+$Parameters+'</root>');$business=[xml]$outer.root.objectXml
            $site=$business.SelectSingleNode('//FLD[@NAME="STOFCY"]').InnerText
            $script:SiteTestSaved[$site]=$business.OuterXml
            if($script:FailAfterSave){throw 'MOCK_TIMEOUT_AFTER_COMMIT'}
            return [pscustomobject]@{Status=1;Messages=@();ResultXml=''}
        }
        $site=[regex]::Match($Parameters,'<value>(201|202|209)</value>').Groups[1].Value
        if($script:SiteTestSaved.ContainsKey($site)){return [pscustomobject]@{Status=1;Messages=@();ResultXml=$script:SiteTestSaved[$site]}}
        return [pscustomobject]@{Status=0;Messages=@('Fiche inexistante');ResultXml=''}
    }
}
$plan=New-SageTestArticleSitePlan -Code EXT_POUDRE -Site 201
if($plan.Exists -or $plan.ObjectXml -notmatch 'STOFCY">201') {throw 'SITE_PLAN_FAILED'}
$approval=[pscustomobject]@{Approved=$true;Folder='TEST';Code='EXT_POUDRE';Site='202';Digest=$plan.Digest;DescriptionHash=$plan.DescriptionHash;Actor=('chat:'+([guid]::NewGuid().ToString()));ExpiresAt=[DateTimeOffset]::UtcNow.AddMinutes(10).ToString('o')}
try{$null=Invoke-SageTestArticleSiteCreation -Plan $plan -Approval $approval;throw 'WRONG_SITE_ACCEPTED'}catch{if($_.Exception.Message -notmatch 'SITE_HUMAN_APPROVAL_INVALID'){throw}}
if((& $module {$script:SiteCalls}) -ne 0){throw 'INVALID_APPROVAL_SENT_SAVE'}
$approval.Site='201'
$result=Invoke-SageTestArticleSiteCreation -Plan $plan -Approval $approval
if($result.State -ne 'CREATED_AND_READ_BACK' -or $result.ReadStatus -ne 1){throw 'MOCK_SITE_SAVE_READ_FAILED'}
$again=Invoke-SageTestArticleSiteCreation -Plan $plan -Approval $approval
if($again.State -ne 'ALREADY_EXISTS' -or (& $module {$script:SiteCalls}) -ne 1){throw 'DUPLICATE_SITE_SAVE'}
& $module {$script:FailAfterSave=$true}
$plan2=New-SageTestArticleSitePlan -Code EXT_POUDRE -Site 202
$approval.Site='202';$approval.Digest=$plan2.Digest;$approval.DescriptionHash=$plan2.DescriptionHash
$uncertain=Invoke-SageTestArticleSiteCreation -Plan $plan2 -Approval $approval
if($uncertain.State -ne 'UNCERTAIN' -or -not $uncertain.ReadConfirmed){throw 'UNCERTAIN_SITE_NOT_READ_BACK'}
[pscustomobject]@{Status='PASS';Mode='OFFLINE_MOCKS_ONLY';RealSaves=0;Checks=@('No master write','Metadata plan','Approval site binding','Single site SAVE and READ','Duplicate skip','Uncertain readback')}|ConvertTo-Json
