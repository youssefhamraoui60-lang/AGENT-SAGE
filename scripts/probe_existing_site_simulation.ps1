#requires -Version 5.1
# Pure simulation: the preparation function is replaced inside this process only.
# No connection is initialized, and no Sage method is called.
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Import-Module (Join-Path $PSScriptRoot 'SageTestArticleSites.psm1') -Force
$module=Get-Module SageTestArticleSites
& $module {
    function script:New-SageTestArticleSitePlan {
        param($Code,$Site)
        [pscustomobject]@{Code=$Code;Site=$Site;Exists=$true;
            Read=[pscustomobject]@{Fields=@{'ITF0_1.STU'='M2'}}}
    }
}
$plan=[pscustomobject]@{Code='EXT_POUDRE';Site='201';Fields=@{'ITF0_1.STU'='UN'}}
$actual=Invoke-SageTestArticleSiteCreation -Plan $plan -Approval ([pscustomobject]@{})
$report=@{Mode='SIMULATION_NO_NETWORK';ExpectedUnit='UN';ActualExistingUnit='M2';
    ExpectedReadConfirmed=$false;Obtained=$actual;SageCalls=0;SaveAttempts=0;
    DefectReproduced=($actual.ReadConfirmed -eq $true)}
$path=Join-Path (Split-Path $PSScriptRoot -Parent) 'tests\ai-evaluation\failures\existing-site-mismatch-simulation.json'
$null=New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force
$report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $path -Encoding UTF8
$report|ConvertTo-Json -Depth 8
if($report.DefectReproduced){exit 1}
