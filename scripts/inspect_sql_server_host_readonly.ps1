# Local inventory only. No import/export, key access, SQL login or service change.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if (@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress) -notcontains '192.168.9.200') {
    throw 'Run only on the authorized Sage host 192.168.9.200. Nothing changed.'
}
$results = [ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');read_only=$true;hostname=$env:COMPUTERNAME}
$computer = Get-CimInstance Win32_ComputerSystem
$results.computer = $computer | Select-Object DNSHostName,Domain,PartOfDomain
$results.services = @(Get-CimInstance Win32_Service |
    Where-Object { $_.Name -in 'MSSQL$SAGEX3','SQLAgent$SAGEX3','Sage_Syracuse_-_NODE0','V12','Sage_Safe_X3_AdxAdmin' } |
    Select-Object Name,State,StartMode,StartName)
$results.listeners = @(Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -In 1433,8124 | Select-Object LocalAddress,LocalPort,OwningProcess)
$service = Get-Service -Name 'MSSQL$SAGEX3' -ErrorAction SilentlyContinue
if ($null -ne $service) { $results.declared_windows_dependents = @($service.DependentServices | Select-Object Name,Status) }
$instanceMap = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL'
$instanceId = $instanceMap.SAGEX3
$results.registry_instance_id = $instanceId
if ($instanceId -and $instanceId -match '^[A-Za-z0-9_.-]+$') {
    $networkKey = 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\'+$instanceId+'\MSSQLServer\SuperSocketNetLib'
    $results.sql_network = Get-ItemProperty -LiteralPath $networkKey |
        Select-Object Certificate,ForceEncryption,ForceStrictEncryption
    $results.sql_tcp = Get-ItemProperty -LiteralPath ($networkKey+'\Tcp') |
        Select-Object Enabled,ListenOnAllIPs
    $results.sql_ports = Get-ItemProperty -LiteralPath ($networkKey+'\Tcp\IPAll') |
        Select-Object TcpPort,TcpDynamicPorts
}
$results.public_certificates = @(foreach ($cert in (Get-ChildItem Cert:\LocalMachine\My)) {
    $hashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
    try { $sha256 = [BitConverter]::ToString($hashAlgorithm.ComputeHash($cert.RawData)).Replace('-','') }
    finally { $hashAlgorithm.Dispose() }
    [ordered]@{subject=$cert.Subject;issuer=$cert.Issuer;windows_thumbprint_sha1=$cert.Thumbprint;sha256=$sha256;
        not_before=$cert.NotBefore.ToUniversalTime().ToString('o');not_after=$cert.NotAfter.ToUniversalTime().ToString('o');
        has_private_key=$cert.HasPrivateKey;dns=@($cert.DnsNameList.Unicode);eku=@($cert.EnhancedKeyUsageList | ForEach-Object { $_.ToString() })}
})
$results.schannel_protocol_overrides = @(foreach ($version in 'TLS 1.0','TLS 1.1','TLS 1.2','TLS 1.3') {
    $protocolPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\'+$version+'\Server'
    if (Test-Path -LiteralPath $protocolPath) {
        $value=Get-ItemProperty -LiteralPath $protocolPath
        [ordered]@{protocol=$version;override_present=$true;enabled=$value.Enabled;disabled_by_default=$value.DisabledByDefault}
    } else { [ordered]@{protocol=$version;override_present=$false;meaning='Windows defaults; not evidence that protocol is enabled or disabled'} }
})
$results.not_established = @('Active certificate binding from registry may differ from running process until restart.',
    'Windows declared dependencies are not a full Sage application dependency inventory.',
    'HasPrivateKey does not verify the SQL service account ACL, key provider or KeySpec.',
    'No SQL ERRORLOG, active SQL sessions or private keys read by this script.')
$results | ConvertTo-Json -Depth 7
