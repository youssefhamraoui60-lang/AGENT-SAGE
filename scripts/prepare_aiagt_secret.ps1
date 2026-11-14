# Optional provisioning on vm7 only. Not invoked by diagnostics.
# DPAPI protects the credential for this Windows user on this machine.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
try {
if([Security.Principal.WindowsIdentity]::GetCurrent().Name -ine 'VM7\youssef'){throw 'Run only under VM7\youssef.'}
$target='C:\AGENT-SAGE-X3\runtime\aiagt-secret'
if(Test-Path -LiteralPath (Join-Path $target 'credential.clixml')){throw 'Credential exists; no overwrite.'}
if(!(Test-Path -LiteralPath $target)){throw 'Protected storage directory must be prepared first.'}
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$existingAcl=Get-Acl -LiteralPath $target
$allowed=@($sid.Value,'S-1-5-18','S-1-5-32-544')
if(!$existingAcl.AreAccessRulesProtected){throw 'Storage ACL inheritance must be disabled.'}
foreach($rule in $existingAcl.Access){if($rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed){throw 'Unexpected storage ACL principal.'}}
@{stage='AWAITING_SECURE_INPUT';identity='VM7\youssef'} | ConvertTo-Json | Set-Content -Encoding UTF8 'C:\AGENT-SAGE-X3\logs\aiagt-provisioning-status.json'
Write-Host 'Compte AIAGT / VM7\youssef. Saisissez le mot de passe renouvele une seule fois.'
$password=Read-Host 'Mot de passe AIAGT (saisie masquee)' -AsSecureString
if(!$password -or $password.Length -eq 0){throw 'Empty password; no credential saved.'}
$credential=[pscredential]::new('AIAGT',$password)
$credential | Export-Clixml -LiteralPath (Join-Path $target 'credential.clixml')
$credential=$null
$password.Dispose();$password=$null
& 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' 'C:\AGENT-SAGE-X3\scripts\verify_aiagt_provisioning.py'
if($LASTEXITCODE -ne 0){throw 'Local credential verification failed; no SOAP sent.'}
& 'C:\AGENT-SAGE-X3\scripts\stop.ps1' -BackendOnly
& 'C:\AGENT-SAGE-X3\scripts\start.ps1' -BackendOnly
& 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' 'C:\AGENT-SAGE-X3\scripts\verify_aiagt_provisioning.py' --live
Write-Host 'Verification terminee. Aucun appel SOAP.'
} catch {
 @{stage='PROVISIONING_FAILED';error_type=$_.Exception.GetType().Name} | ConvertTo-Json | Set-Content -Encoding UTF8 'C:\AGENT-SAGE-X3\logs\aiagt-provisioning-status.json'
 Write-Host 'Provisionnement interrompu. Aucun secret journalise. Consulter le statut local.'
}
