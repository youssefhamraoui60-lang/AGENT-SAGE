# Read-only inventory. Run on the Sage Windows host, not the agent VM.
# No installation, configuration change, secret access or remote execution.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
if ($addresses -notcontains '192.168.9.200') {
    throw 'Wrong host: expected a local interface with IP 192.168.9.200. Nothing changed.'
}
$osInfo = Get-CimInstance Win32_OperatingSystem
$computerInfo = Get-CimInstance Win32_ComputerSystem
$listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 8124,8443,443,22 |
    Select-Object LocalAddress,LocalPort,OwningProcess)
$firewallInfo = $null
$firewallError = $null
try {
    $firewallInfo = @(Get-NetFirewallProfile -PolicyStore ActiveStore |
        Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction)
} catch { $firewallError = 'Firewall inventory requires permitted local administrative read access.' }
$relayCommand = Get-Command stunnel.exe -ErrorAction SilentlyContinue
[ordered]@{
    checked_at = [DateTime]::UtcNow.ToString('o')
    computer = $env:COMPUTERNAME
    os = $osInfo.Caption
    build = $osInfo.BuildNumber
    logical_processors = $computerInfo.NumberOfLogicalProcessors
    free_memory_kb = $osInfo.FreePhysicalMemory
    interfaces_ipv4 = $addresses
    listeners = $listeners
    stunnel_in_path = [bool]$relayCommand
    firewall_profiles = $firewallInfo
    firewall_inventory_error = $firewallError
    remaining_manual_checks = @(
        'Review effective existing Allow/Block rules, including broad rules, for TCP 8443 and the agent IP.',
        'Verify loopback Syracuse access without sending credentials into logs.',
        'Confirm certificate SAN/chain/expiry/private-key match and execution-account ACLs.',
        'Inventory consumers of POOL_AI_TEST before any identity change.'
    )
    changes_applied = $false
} | ConvertTo-Json -Depth 5
