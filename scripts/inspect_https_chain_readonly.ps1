$ErrorActionPreference='Stop'
# Inspection only: validation callback ALWAYS refuses the connection.
# No HTTP, credentials, trust-store modification or successful TLS acceptance.
Add-Type -TypeDefinition @'
using System;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
public static class RefusingTlsInspector {
 public static byte[] Leaf;
 public static string Errors;
 public static string Failure;
 public static string[] ChainStatus;
 public static void Inspect() {
  using(var tcp=new TcpClient()) {
   var task=tcp.ConnectAsync("192.168.9.200",8443);
   if(!task.Wait(6000)) throw new TimeoutException();
   using(var stream=new SslStream(tcp.GetStream(),false,(sender,cert,chain,errors)=>{
    Leaf=cert.GetRawCertData(); Errors=errors.ToString();
    var statuses=new System.Collections.Generic.List<string>();
    if(chain!=null) foreach(var e in chain.ChainElements) foreach(var s in e.ChainElementStatus) statuses.Add(e.Certificate.Subject+": "+s.Status+" "+s.StatusInformation.Trim());
    ChainStatus=statuses.ToArray(); return false;
   })) {
    stream.ReadTimeout=10000;stream.WriteTimeout=10000;
    try {stream.AuthenticateAsClient("sage",new X509CertificateCollection(),SslProtocols.None,true);} catch(AuthenticationException e) {Failure=e.ToString();}
   }
  }
 }
}
'@
[RefusingTlsInspector]::Inspect()
if(![RefusingTlsInspector]::Leaf){throw ('No server certificate captured: '+[RefusingTlsInspector]::Failure)}
$leaf=New-Object Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList (,[RefusingTlsInspector]::Leaf)
$ca=New-Object Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList 'C:\AGENT-SAGE-X3\certs\ca.cacrt'
function Details($cert) {
 $sha=[Security.Cryptography.SHA256]::Create()
 try {$hash=([BitConverter]::ToString($sha.ComputeHash($cert.RawData))).Replace('-','')}finally{$sha.Dispose()}
 $oids=@('2.5.29.35','2.5.29.14','2.5.29.17','2.5.29.19','2.5.29.15','2.5.29.31','1.3.6.1.5.5.7.1.1','2.5.29.37')
 $extensions=@();foreach($oid in $oids){$ext=@($cert.Extensions | Where-Object {$_.Oid.Value -eq $oid});$extensions+=@{oid=$oid;present=($ext.Count -gt 0);value=if($ext.Count){$ext[0].Format($true)}else{$null};critical=if($ext.Count){$ext[0].Critical}else{$null}}}
 return @{subject=$cert.Subject;issuer=$cert.Issuer;sha256_der=$hash;not_before=$cert.NotBefore.ToUniversalTime().ToString('o');not_after=$cert.NotAfter.ToUniversalTime().ToString('o');extensions=$extensions}
}
$report=@{leaf=(Details $leaf);ca=(Details $ca);validation_errors=[RefusingTlsInspector]::Errors;chain_status=[RefusingTlsInspector]::ChainStatus;callback_always_refused=$true;revocation_check_requested=$true;trust_store_modified=$false}
[IO.File]::WriteAllBytes('C:\AGENT-SAGE-X3\logs\https-presented-sage-20261024.cer',$leaf.RawData)
$report | ConvertTo-Json -Depth 9 | Set-Content -Encoding UTF8 'C:\AGENT-SAGE-X3\logs\https-x509-extensions-20261024.json'
$report | ConvertTo-Json -Depth 9
