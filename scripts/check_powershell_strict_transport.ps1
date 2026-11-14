#requires -Version 5.1
# No credentials, SOAP body or write operation. Native TLS verification enabled.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Net.Http
$report=[ordered]@{checked_at=[DateTimeOffset]::UtcNow.ToString('o');method='HEAD';endpoint='https://sage:8443/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC';credentials_sent=$false;soap_save_sent=$false;certificate_validation='Windows trust, hostname, validity and revocation';revocation_required=$true;tls_verified=$false}
$handler=$null;$client=$null;$request=$null;$response=$null
try {
    if($null -ne [Net.ServicePointManager]::ServerCertificateValidationCallback){throw 'CUSTOM_TLS_CALLBACK_REFUSED'}
    $handler=[Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect=$false
    $handler.UseDefaultCredentials=$false
    $handler.PreAuthenticate=$false
    $handler.CheckCertificateRevocationList=$true
    $client=[Net.Http.HttpClient]::new($handler)
    $client.Timeout=[TimeSpan]::FromSeconds(15)
    $request=[Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Head,$report.endpoint)
    $response=$client.SendAsync($request).GetAwaiter().GetResult()
    $report.tls_verified=$true
    $report.http_status=[int]$response.StatusCode
    $report.result='STRICT_TLS_COMPLETED_NO_AUTHENTICATION_OR_SAVE'
} catch {
    $report.result=if($_.Exception.ToString() -match 'AuthenticationException|certificate|certificat|trust|confiance'){'STRICT_TLS_VALIDATION_FAILED'}else{'CONNECTION_CHECK_FAILED'}
    $types=@();$exception=$_.Exception
    while($exception){$types+=$exception.GetType().FullName;$exception=$exception.InnerException}
    $report.error_types=$types
} finally {
    if($response){$response.Dispose()}
    if($request){$request.Dispose()}
    if($client){$client.Dispose()}elseif($handler){$handler.Dispose()}
}
$report|ConvertTo-Json -Depth 5
if(-not $report.tls_verified){exit 2}
