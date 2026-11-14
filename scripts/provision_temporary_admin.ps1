# Run interactively as VM7\youssef. No ERP request, no write gate activation.
$ErrorActionPreference='Stop'
if ([Security.Principal.WindowsIdentity]::GetCurrent().Name -ine 'VM7\youssef') { throw 'VM7\youssef required' }
$root=Split-Path $PSScriptRoot -Parent
$directory=Join-Path $root 'runtime\admin-secret'
$target=Join-Path $directory 'credential.clixml'
if (Test-Path -LiteralPath $target) { throw 'Credential already exists; no overwrite' }
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$acl=[Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true,$false)
foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
 $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
}
Set-Acl -LiteralPath $directory -AclObject $acl
$credential=Get-Credential -UserName admin -Message 'Compte SOAP admin temporaire : secret DPAPI local uniquement'
if (-not $credential -or $credential.UserName -cne 'admin' -or $credential.Password.Length -eq 0) { throw 'Admin credential required' }
$credential | Export-Clixml -LiteralPath $target
$credential=$null
# Update only the identity and DPAPI path; preserve TLS and all write locks.
$envPath=Join-Path $root '.env'
$content=[IO.File]::ReadAllText($envPath)
$values=@{SAGE_SOAP_CREDENTIAL_FILE=$target.Replace('\','/');SAGE_SOAP_DPAPI_USERNAME='admin'}
foreach ($key in $values.Keys) {
 $line=$key+'='+$values[$key]
 if ($content -match ('(?m)^'+$key+'=.*$')) { $content=[regex]::Replace($content,'(?m)^'+$key+'=.*$', $line) }
 else { $content+=[Environment]::NewLine+$line+[Environment]::NewLine }
}
[IO.File]::WriteAllText($envPath,$content,[Text.UTF8Encoding]::new($false))
Write-Output 'DPAPI admin provisioned. Backend restart required. Write locks unchanged.'
