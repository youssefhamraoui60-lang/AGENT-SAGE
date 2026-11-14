# LOCAL backup only: new protected folder, selected configuration files,
# hashes and manifest. No service/configuration/certificate-store changes.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string[]]$ConfigurationFile,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference='Stop'
if(@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress) -notcontains '192.168.9.200'){throw 'Run locally on server 192.168.9.200. Nothing copied.'}
if(!$ConfigurationFile.Count -or $ConfigurationFile.Count -gt 20){throw 'Select between 1 and 20 configuration files.'}
if($Destination -notmatch '^[A-Za-z]:\\' -or $Destination -match '[*?\[\]]'){throw 'Use a new absolute local destination folder.'}
$target=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $target){throw 'Destination must not exist; no existing folder will be modified.'}
$parent=Get-Item -LiteralPath (Split-Path $target -Parent)
if(!$parent.PSIsContainer -or $parent.PSProvider.Name -ne 'FileSystem'){throw 'Select an existing approved local backup parent folder.'}
$sources=@(foreach($file in $ConfigurationFile){
    if($file -notmatch '^[A-Za-z]:\\'){throw 'Configuration sources must be local files.'}
    $item=Get-Item -LiteralPath $file
    if($item.PSIsContainer -or $item.Length -gt 20971520){throw 'Only selected configuration files up to 20MB each are accepted.'}
    if($item.Extension -notin '.js','.json','.conf','.ini','.config','.properties'){throw 'Only configuration/export files accepted; no certificate or private-key containers.'}
    $item
})
$directory=New-Item -ItemType Directory -Path $target
# Secure the empty new directory BEFORE copying potentially sensitive settings.
$acl=[Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true,$false)
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($owner)
foreach($sid in @($owner,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'),[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))){
    $rule=[Security.AccessControl.FileSystemAccessRule]::new($sid,[Security.AccessControl.FileSystemRights]::FullControl,([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
    [void]$acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $directory.FullName -AclObject $acl
$files=@();$index=0
foreach($source in $sources){
    $index++;$name=('{0:D2}-' -f $index)+$source.Name
    $copy=Join-Path $target $name
    $before=(Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
    Copy-Item -LiteralPath $source.FullName -Destination $copy
    $after=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash
    $sourceAfter=(Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
    if($before -ne $after -or $before -ne $sourceAfter){throw 'File changed during copy or backup mismatch. Do not use this backup; sources left unchanged.'}
    $files+=@{source=$source.FullName;backup_name=$name;configuration_file_sha256=$after;bytes=$source.Length}
}
$manifest=@{computer=$env:COMPUTERNAME;created_at_utc=[DateTime]::UtcNow.ToString('o');files=$files;runtime_settings_changed=$false;service_actions=0;notice='Sensitive local backup. Do not send configuration contents or secrets to the agent/chat. Not a MongoDB/database backup.'}
[IO.File]::WriteAllText((Join-Path $target 'manifest.json'),($manifest|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{backup=$target;files=$files.Count;hashes_verified=$true;source_files_changed=$false;service_actions=0}
