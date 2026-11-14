#requires -Version 5.1
# Default: read-only Sage calls and local review artifacts. Never sends SAVE.
[CmdletBinding()]
param([switch]$CreateAfterSpecificApproval)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
try {
    $null=Connect-SageTestSoap
    $plan=New-SageTestArticlePlan -Code TESTPEINTURE001 -Designation 'PEINTURE ACRYLIQUE BLANCHE 20 KG' -Category NEG -Unit UN -StockManagement 1 -TaxCode T20
    $plan | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $root 'logs\TESTPEINTURE001-plan.json') -Encoding UTF8
    $plan.ObjectXml | Set-Content (Join-Path $root 'logs\TESTPEINTURE001-corrected.xml') -Encoding UTF8
    if ($CreateAfterSpecificApproval) {
        # Retains module confirmation, exact digest challenge, duplicate checks,
        # permanent one-attempt marker and SOAP readback. No approval bypass.
        Invoke-SageTestArticleCreation -Plan $plan
    } else { $plan }
} finally { Disconnect-SageTestSoap }
