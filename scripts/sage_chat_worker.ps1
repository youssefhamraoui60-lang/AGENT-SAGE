#requires -Version 5.1
# Fixed JSON protocol on stdin. No command interpolation, no general SOAP dispatcher.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$report=$null
try {
    $inputText=[Console]::In.ReadToEnd()
    if ($inputText.Length -gt 100000) { throw 'REQUEST_TOO_LARGE' }
    $data=$inputText | ConvertFrom-Json
    $foamNames=@{'MFB-A-XPS-40'='Modern foam boards A XPS 4 CM';'MFB-B-XPS-40'='Modern foam boards B XPS 4 CM'}
    $foam=$foamNames.ContainsKey([string]$data.Code) -and $data.Designation -ceq $foamNames[[string]$data.Code] -and $data.Unit -ceq 'M2' -and -not $data.SupplierCode -and -not $data.StockManagement
    $requiredSite=if($foam){'202'}else{'201'}
    $extinguisher=$data.Code -ceq 'EXT_POUDRE' -and $data.Designation -ieq ('Extincteur '+[char]0xe0+' poudre') -and $data.SupplierCode -ceq 'F1025' -and $data.StockManagement -ceq '1'
    if ($data.Site -cne $requiredSite -or ($data.Code -cnotmatch '^TEST[A-Z0-9_.-]{1,16}$' -and -not $extinguisher -and -not $foam) -or $data.Category -cne 'NEG' -or $data.Unit -cne $(if($foam){'M2'}else{'UN'})) { throw 'SITE_201_TEST_SCOPE_REQUIRED' }
    if (-not $extinguisher -and ($data.SupplierCode -or $data.StockManagement)) { throw 'OUTSIDE_WEB_TEST_SCOPE' }
    Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
    $null=Connect-SageTestSoap
    switch ($data.Mode) {
        'prepare' { $report=New-SageTestArticlePlan -Code $data.Code -Designation $data.Designation -Category $data.Category -Unit $data.Unit -SupplierCode ([string]$data.SupplierCode) -StockManagement ([string]$data.StockManagement) }
        'execute' { $report=Invoke-SageTestArticleCreation -Plan $data.Plan -ApprovalReceipt $data.Approval -Confirm:$false 6>$null }
        'read' { $report=Get-SageTestArticle -Code $data.Code }
        default { throw 'INVALID_WORKER_MODE' }
    }
    @{ok=$true;result=$report} | ConvertTo-Json -Depth 16 -Compress
} catch {
    $message=$_.Exception.Message
    $code=if($message -cmatch '^[A-Z0-9_]+$'){$message}else{'POWERSHELL_WORKER_FAILED'}
    @{ok=$false;code=$code} | ConvertTo-Json -Compress
    exit 1
} finally { if (Get-Command Disconnect-SageTestSoap -ErrorAction SilentlyContinue) { Disconnect-SageTestSoap } }
