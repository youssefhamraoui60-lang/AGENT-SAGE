# One-shot SOAP test. No configuration changes, credential persistence or SAVE retry.
[CmdletBinding()]
param([string]$ValidatedBusinessXmlPath)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$endpoint = 'https://sage:8443/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC'
$reportPath = Join-Path $root 'logs\TESTSOAP003-admin-result.json'
$report = [ordered]@{article='TESTSOAP003';folder='TEST';save_attempts=0;status='BLOCKED';steps=@()}
$credential = $null
$client = $null
try {
    # Schannel validates Windows trust, name and revocation before any credentials.
    & curl.exe -4 --silent --show-error --output NUL --connect-timeout 5 --max-time 15 $endpoint
    if ($LASTEXITCODE -ne 0) { throw 'TLS_GATE_FAILED: no authenticated request sent' }
    if (-not $ValidatedBusinessXmlPath -or -not (Test-Path -LiteralPath $ValidatedBusinessXmlPath -PathType Leaf)) {
        throw 'VALIDATED_TESTSOAP002_BUSINESS_XML_REQUIRED'
    }
    function Parse-SafeXml([string]$text) {
        $options = [System.Xml.XmlReaderSettings]::new()
        $options.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
        $options.XmlResolver = $null
        $reader = [System.Xml.XmlReader]::Create([System.IO.StringReader]::new($text), $options)
        try { $doc = [System.Xml.XmlDocument]::new(); $doc.XmlResolver=$null; $doc.Load($reader); return ,$doc }
        finally { $reader.Dispose() }
    }
    $business = Parse-SafeXml (Get-Content -LiteralPath $ValidatedBusinessXmlPath -Raw)
    if ($business.DocumentElement.Name -ne 'PARAM') { throw 'EXPECTED_BUSINESS_PARAM_XML' }
    foreach ($pair in @(@('ITMREF','TESTSOAP003'),@('DES1AXX','ARTICLE TEST AGENT IA VM208'),@('TCLCOD','NEG'),@('ITMSTA','1'),@('STU','UN'),@('SAU','UN'),@('PUU','UN'))) {
        $nodes = $business.SelectNodes("//FLD[@NAME='$($pair[0])']")
        if ($nodes.Count -ne 1) { throw "VALIDATED_XML_FIELD_MISSING_OR_AMBIGUOUS: $($pair[0])" }
        if ($pair[0] -eq 'ITMREF' -and $nodes[0].InnerText -ne 'TESTSOAP002') { throw 'EXPECTED_TESTSOAP002_TEMPLATE' }
        $nodes[0].InnerText = $pair[1]
    }
    Add-Type -AssemblyName System.Net.Http
    $credential = Get-Credential -UserName 'admin' -Message 'SOAP TEST uniquement : TESTSOAP003'
    if ($null -eq $credential -or $credential.UserName -cne 'admin') { throw 'ADMIN_CREDENTIAL_REQUIRED' }
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.CheckCertificateRevocationList = $true
    $handler.Credentials = $credential.GetNetworkCredential()
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(45)
    function Invoke-Soap([string]$operation,[string]$parameters) {
        $body = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:w="http://www.adonix.com/WSS" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:enc="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><w:'+$operation+' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><callContext><codeLang>FRA</codeLang><poolAlias>POOL_AI_TEST</poolAlias><poolId></poolId><requestConfig>adxwss.optreturn=XML&amp;adxwss.trace.on=off</requestConfig></callContext><publicName>WS_ARTICLE</publicName>'+$parameters+'</w:'+$operation+'></s:Body></s:Envelope>'
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post,$endpoint)
        $request.Headers.Add('SOAPAction',$operation)
        $request.Content = [System.Net.Http.StringContent]::new($body,[System.Text.Encoding]::UTF8,'text/xml')
        try {
            $response = $client.SendAsync($request).GetAwaiter().GetResult()
            try {
                $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                if ([int]$response.StatusCode -ne 200) { throw "HTTP_$([int]$response.StatusCode)" }
                $xml = Parse-SafeXml $text
                $status = $xml.SelectSingleNode('//*[local-name()="status"]')
                $result = $xml.SelectSingleNode('//*[local-name()="resultXml"]')
                $messages = @($xml.SelectNodes('//*[local-name()="message"]') | ForEach-Object InnerText)
                $report.steps += [ordered]@{operation=$operation;status=if($status){$status.InnerText}else{$null};messages=$messages}
                return @{status=if($status){$status.InnerText}else{''};result=if($result){$result.InnerText}else{''};messages=$messages}
            } finally { $response.Dispose() }
        } finally { $request.Dispose() }
    }
    $description = Invoke-Soap 'getDescription' ''
    if ($description.status -ne '1' -or $description.result -notmatch 'TEST') { throw 'POOL_TEST_DESCRIPTION_NOT_CONFIRMED' }
    function Read-Article {
        Invoke-Soap 'read' '<objectKeys enc:arrayType="w:CAdxParamKeyValue[1]" xsi:type="enc:Array"><item><key>ITMREF</key><value>TESTSOAP003</value></item></objectKeys>'
    }
    $before = Read-Article
    if ($before.status -eq '1') { throw 'ARTICLE_EXISTS_OR_READ_AMBIGUOUS' }
    # A failed READ alone is not proof of absence: require a successful SQL SELECT too.
    & (Join-Path $PSScriptRoot 'test_sage_sql_readonly.ps1') -Article TESTSOAP003 | Out-Null
    $sql = Get-Content (Join-Path $root 'logs\sql-server-readonly-tests.json') -Raw | ConvertFrom-Json
    if ($sql.status -ne 'READ_ONLY_QUERIES_COMPLETED' -or $null -eq $sql.queries.article -or @($sql.queries.article).Count -ne 0) { throw 'SQL_ABSENCE_NOT_CONFIRMED' }
    if (($before.messages -join ' ') -notmatch '(?i)(inexistant|n.existe pas|does not exist|not found)') { throw 'SOAP_ABSENCE_NOT_CONFIRMED' }
    # Durable marker is written BEFORE transmission; reruns cannot issue another SAVE.
    $marker = Join-Path $root 'runtime\TESTSOAP003-save-attempt.lock'
    $stream = [System.IO.File]::Open($marker,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    $stream.Dispose()
    $report.save_attempts = 1
    try { $saved = Invoke-Soap 'save' ('<objectXml>'+[System.Security.SecurityElement]::Escape($business.OuterXml)+'</objectXml>') }
    catch { $report.save_transport_error=$_.Exception.GetType().Name }
    $after = Read-Article
    $report.soap_read_confirmed = $false
    if ($after.status -eq '1') {
        $record = Parse-SafeXml $after.result
        $key = $record.SelectSingleNode('//FLD[@NAME="ITMREF"]')
        $report.soap_read_confirmed = $null -ne $key -and $key.InnerText -eq 'TESTSOAP003'
    }
    & (Join-Path $PSScriptRoot 'test_sage_sql_readonly.ps1') -Article TESTSOAP003 | Out-Null
    $sql = Get-Content (Join-Path $root 'logs\sql-server-readonly-tests.json') -Raw | ConvertFrom-Json
    $report.sql_read_confirmed = $sql.status -eq 'READ_ONLY_QUERIES_COMPLETED' -and @($sql.queries.article | Where-Object ITMREF_0 -eq 'TESTSOAP003').Count -eq 1
    $report.status = if ($report.soap_read_confirmed -and $report.sql_read_confirmed) {'CREATED_AND_READ_BACK'} else {'UNCONFIRMED_DO_NOT_RETRY_SAVE'}
} catch { $report.error = $_.Exception.Message }
finally {
    if ($client) { $client.Dispose() }
    $credential = $null
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $report | ConvertTo-Json -Depth 8
}
