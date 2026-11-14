#requires -Version 5.1
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
try {
    $data=[Console]::In.ReadToEnd() | ConvertFrom-Json
    if($data.Code -cne 'EXT_POUDRE' -or $data.Site -notin @('201','202','209')){throw 'SITE_SCOPE_DENIED'}
    Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1')
    Import-Module (Join-Path $PSScriptRoot 'SageTestArticleSites.psm1')
    $null=Connect-SageTestSoap
    $result=switch($data.Mode){
        'prepare' {New-SageTestArticleSitePlan -Code $data.Code -Site $data.Site}
        'read' {Get-SageTestArticleSite -Code $data.Code -Site $data.Site}
        'execute' {Invoke-SageTestArticleSiteCreation -Plan $data.Plan -Approval $data.Approval}
        default {throw 'SITE_MODE_DENIED'}
    }
    @{ok=$true;result=$result}|ConvertTo-Json -Depth 16 -Compress
}catch{
    $message=$_.Exception.Message;$code=if($message -cmatch '^[A-Z0-9_]+$'){$message}else{'SITE_WORKER_FAILED'}
    @{ok=$false;code=$code}|ConvertTo-Json -Compress;exit 1
}finally{if(Get-Command Disconnect-SageTestSoap -ErrorAction SilentlyContinue){Disconnect-SageTestSoap}}
