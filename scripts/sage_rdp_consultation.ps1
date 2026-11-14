# Windows PowerShell 5.1+. LOCAL consultations only. No remote execution,
# service control, configuration write, trust installation or SOAP write.
[CmdletBinding()]
param(
    [string]$PublicCertificate,
    [string[]]$PublicChain = @(),
    [string]$ReportPath
)
$ErrorActionPreference='Stop'
$addresses=@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
if($addresses -notcontains '192.168.9.200'){throw 'Wrong host. Run locally in RDP on 192.168.9.200. Nothing changed.'}
function Read-PublicCertificate([string]$File) {
    $resolved=(Resolve-Path -LiteralPath $File).Path
    if([IO.Path]::GetExtension($resolved) -match '^\.(pfx|p12|key)$'){throw 'Only public CER/DER/PEM certificates accepted.'}
    $bytes=[IO.File]::ReadAllBytes($resolved)
    if($bytes.Length -gt 262144){throw 'Public certificate file too large.'}
    $text=[Text.Encoding]::UTF8.GetString($bytes)
    if($text -match 'PRIVATE KEY'){throw 'Private key input refused. Do not send this file.'}
    if($text -match '-----BEGIN CERTIFICATE-----([\s\S]+?)-----END CERTIFICATE-----'){
        if(([regex]::Matches($text,'-----BEGIN CERTIFICATE-----')).Count -ne 1){throw 'Use one public certificate per file.'}
        $bytes=[Convert]::FromBase64String(($matches[1] -replace '\s',''))
    }
    if([Security.Cryptography.X509Certificates.X509Certificate2]::GetCertContentType($bytes) -ne [Security.Cryptography.X509Certificates.X509ContentType]::Cert){throw 'A single public X509 certificate is required; container imports refused.'}
    $cert=[Security.Cryptography.X509Certificates.X509Certificate2]::new($bytes)
    if($cert.HasPrivateKey){$cert.Dispose();throw 'Private key input refused.'}
    return $cert
}
function Public-Details($Cert){
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$hash=([BitConverter]::ToString($sha.ComputeHash($Cert.RawData))).Replace('-','')}
    finally{$sha.Dispose()}
    return [ordered]@{subject=$Cert.Subject;issuer=$Cert.Issuer;sha256_der=$hash;not_before=$Cert.NotBefore.ToUniversalTime().ToString('o');not_after=$Cert.NotAfter.ToUniversalTime().ToString('o');has_private_key=$Cert.HasPrivateKey;extensions=@($Cert.Extensions | Where-Object {$_.Oid.Value -in '2.5.29.17','2.5.29.37','2.5.29.19','2.5.29.15'} | ForEach-Object {@{oid=$_.Oid.Value;value=$_.Format($true)}})}
}
$service=Get-CimInstance Win32_Service | Where-Object Name -EQ 'Sage_Syracuse_-_NODE0'
$report=[ordered]@{
    checked_at_utc=[DateTime]::UtcNow.ToString('o');computer=$env:COMPUTERNAME
    service=@($service | Select-Object Name,State,StartMode,StartName)
    listeners=@(Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 8124,8443,443 | Select-Object LocalAddress,LocalPort,OwningProcess)
    established_clients=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object LocalPort -In 8124,8443 | Group-Object RemoteAddress | Select-Object Name,Count)
    firewall=@(Get-NetFirewallProfile -PolicyStore ActiveStore | Select-Object Name,Enabled,DefaultInboundAction)
    windows_public_certificates=@(Get-ChildItem Cert:\LocalMachine\My | ForEach-Object {Public-Details $_})
    changes_applied=$false;soap_calls_sent=0
    limits=@('No X3 rights or active users inferred from TCP connections.','Windows store is distinct from Syracuse certificates.','Offline chain does not check DNS hostname or guarantee current revocation.','No production settings or secrets backed up by this consultation script.')
}
if($service){
    $svc=Get-Service -Name $service.Name
    $report['windows_dependencies']=@($svc.ServicesDependedOn | ForEach-Object {@{name=$_.Name;status=$_.Status.ToString()}})
    $report['windows_dependents']=@($svc.DependentServices | ForEach-Object {@{name=$_.Name;status=$_.Status.ToString()}})
}
if($PublicChain.Count -and !$PublicCertificate){throw 'Provide PublicCertificate with PublicChain.'}
if($PublicCertificate){
    $leaf=$null;$chain=$null;$extra=@()
    try{
        $leaf=Read-PublicCertificate $PublicCertificate
        $chain=[Security.Cryptography.X509Certificates.X509Chain]::new()
        $chain.ChainPolicy.RevocationMode=[Security.Cryptography.X509Certificates.X509RevocationMode]::Offline
        $chain.ChainPolicy.VerificationFlags=[Security.Cryptography.X509Certificates.X509VerificationFlags]::NoFlag
        [void]$chain.ChainPolicy.ApplicationPolicy.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
        foreach($file in $PublicChain){$c=Read-PublicCertificate $file;$extra+=,$c;[void]$chain.ChainPolicy.ExtraStore.Add($c)}
        $built=$chain.Build($leaf)
        $report['candidate']=Public-Details $leaf
        $report['offline_chain']=[ordered]@{build_ok=$built;trust_install_requested=$false;extra_store_is_not_a_trust_grant=$true;revocation_mode='Offline';hostname_verified=$false;status=@($chain.ChainStatus | ForEach-Object {@{status=$_.Status.ToString();information=$_.StatusInformation}});elements=@($chain.ChainElements | ForEach-Object {Public-Details $_.Certificate});supplied_public_chain=@($extra | ForEach-Object {Public-Details $_})}
    }finally{if($chain){$chain.Dispose()};if($leaf){$leaf.Dispose()};foreach($c in $extra){$c.Dispose()}}
}
$json=$report | ConvertTo-Json -Depth 10
if($ReportPath){
    # Optional new report file only; never overwrite an existing file or create directories.
    $target=[IO.Path]::GetFullPath($ReportPath)
    if([IO.Path]::GetExtension($target) -ne '.json'){throw 'ReportPath must be a new JSON file.'}
    $stream=[IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes($json);$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
}
$json
