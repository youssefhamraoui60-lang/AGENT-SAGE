#requires -Version 5.1
Set-StrictMode -Version Latest
$script:Client=$null
$script:Credential=$null
$script:Root=Split-Path $PSScriptRoot -Parent
$script:Endpoint='https://sage:8443/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC'

function Read-SafeXml([string]$Text) {
    if ($Text.Length -gt 4000000) { throw 'SOAP_RESPONSE_TOO_LARGE' }
    $options=[Xml.XmlReaderSettings]::new()
    $options.DtdProcessing=[Xml.DtdProcessing]::Prohibit
    $options.XmlResolver=$null
    $reader=[Xml.XmlReader]::Create([IO.StringReader]::new($Text),$options)
    try { $doc=[Xml.XmlDocument]::new();$doc.XmlResolver=$null;$doc.Load($reader);return ,$doc }
    finally { $reader.Dispose() }
}
function Escape-Xml([string]$Value) { [Security.SecurityElement]::Escape($Value) }
function Get-Hash([string]$Value) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Assert-Code([string]$Code) {
    if ($Code -cnotmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,19}$') { throw 'INVALID_ARTICLE_CODE' }
}
function Disconnect-SageTestSoap {
    if ($script:Client) { $script:Client.Dispose() }
    $script:Client=$null;$script:Credential=$null
}
function Connect-SageTestSoap {
    [CmdletBinding()]
    param([string]$CredentialPath=(Join-Path $script:Root 'runtime\admin-secret\credential.clixml'))
    Disconnect-SageTestSoap
    if ([Security.Principal.WindowsIdentity]::GetCurrent().Name -ine 'VM7\youssef') { throw 'EXPECTED_WINDOWS_IDENTITY_VM7_YOUSSEF' }
    if ($null -ne [Net.ServicePointManager]::ServerCertificateValidationCallback) { throw 'CUSTOM_GLOBAL_TLS_CALLBACK_REFUSED' }
    try { $credential=Import-Clixml -LiteralPath $CredentialPath }
    catch { throw 'DPAPI_CREDENTIAL_UNAVAILABLE' }
    if ($credential -isnot [Management.Automation.PSCredential] -or $credential.UserName -cne 'admin' -or $credential.Password.Length -eq 0) { throw 'ADMIN_PSCREDENTIAL_REQUIRED' }
    Add-Type -AssemblyName System.Net.Http
    $handler=[Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect=$false
    # TEST exception explicitly approved by the user: preserve the Windows
    # HttpClient default, without imposing an additional revocation requirement.
    # Certificate trust, chain, dates and server name validation remain enabled.
    $revocationRequired=$handler.CheckCertificateRevocationList
    $handler.Credentials=$credential.GetNetworkCredential()
    $client=[Net.Http.HttpClient]::new($handler)
    $client.Timeout=[TimeSpan]::FromSeconds(30)
    $client.MaxResponseContentBufferSize=4000000
    $script:Client=$client;$script:Credential=$credential
    [pscustomobject]@{Configured=$true;Authenticated=$false;Account='admin';Folder='TEST';Pool='POOL_AI_TEST';WindowsRevocationRequired=$revocationRequired;TlsPolicy='APPROVED_TEST_WINDOWS_DEFAULT';CertificateValidation='Windows trust, chain, dates and hostname'}
}
function Invoke-TestSoap([ValidateSet('getDescription','read','save')][string]$Operation,[string]$Parameters='',
    [ValidateSet('WS_ARTICLE','WS_AR_SITE')][string]$Publication='WS_ARTICLE') {
    if (-not $script:Client) { throw 'CONNECT_FIRST' }
    $body='<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:w="http://www.adonix.com/WSS" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:enc="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><w:'+$Operation+' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><callContext><codeLang>FRA</codeLang><poolAlias>POOL_AI_TEST</poolAlias><poolId></poolId><requestConfig>adxwss.optreturn=XML&amp;adxwss.trace.on=off</requestConfig></callContext><publicName>WS_ARTICLE</publicName>'+$Parameters+'</w:'+$Operation+'></s:Body></s:Envelope>'
    if ($Publication -eq 'WS_AR_SITE') { $body=$body.Replace('<publicName>WS_ARTICLE</publicName>','<publicName>WS_AR_SITE</publicName>') }
    $request=[Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post,$script:Endpoint)
    $request.Headers.Add('SOAPAction',$Operation)
    $request.Content=[Net.Http.StringContent]::new($body,[Text.Encoding]::UTF8,'text/xml')
    try {
        try { $response=$script:Client.SendAsync($request).GetAwaiter().GetResult() }
        catch {
            if ($_.Exception.ToString() -match 'AuthenticationException|certificate|certificat|trust|confiance') { throw 'HTTPS_WINDOWS_VALIDATION_FAILED' }
            throw 'SOAP_TRANSPORT_FAILED_NO_AUTOMATIC_RETRY'
        }
        try {
            if ([int]$response.StatusCode -ne 200) { throw ('SOAP_HTTP_'+[int]$response.StatusCode) }
            $xml=Read-SafeXml ($response.Content.ReadAsStringAsync().GetAwaiter().GetResult())
            $returned=$xml.SelectNodes('/*[local-name()="Envelope" and namespace-uri()="http://schemas.xmlsoap.org/soap/envelope/"]/*[local-name()="Body"]/*[local-name()="'+$Operation+'Response" and namespace-uri()="http://www.adonix.com/WSS"]/*[local-name()="'+$Operation+'Return"]')
            if ($returned.Count -ne 1) { throw 'SOAP_REPLY_INVALID_OR_FAULT' }
            $status=$returned[0].SelectSingleNode('./*[local-name()="status"]')
            if (-not $status -or $status.InnerText -notmatch '^\d+$') { throw 'SOAP_STATUS_MISSING' }
            $result=$returned[0].SelectSingleNode('./*[local-name()="resultXml"]')
            # SOAP RPC encoded message arrays may be multiRef siblings of Return.
            $messages=@($xml.SelectNodes('//*[local-name()="message"]') | ForEach-Object {
                $text=$_.InnerText
                $secret=$script:Credential.GetNetworkCredential().Password
                try { if ($secret) { $text=$text.Replace($secret,'[REDACTED]') };$text }
                finally { $secret=$null }
            })
            return [pscustomobject]@{Status=[int]$status.InnerText;Messages=$messages;ResultXml=if($result){$result.InnerText}else{''}}
        } finally { $response.Dispose() }
    } finally { $request.Dispose() }
}
function Get-SageTestDescription {
    $reply=Invoke-TestSoap getDescription
    if ($reply.Status -ne 1 -or -not $reply.ResultXml) { throw 'SOAP_DESCRIPTION_FAILED' }
    $doc=Read-SafeXml $reply.ResultXml
    foreach ($pair in @(@('FOL','TEST'),@('SOL','V12'),@('PNA','WS_ARTICLE'),@('OBJ','ITM'))) {
        if ($doc.DocumentElement.GetAttribute($pair[0]) -cne $pair[1]) { throw 'SOAP_TARGET_IS_NOT_V12_TEST_ARTICLE' }
    }
    return ,$doc
}
function Read-ArticleInternal([string]$Code) {
    Assert-Code $Code
    $reply=Invoke-TestSoap read ('<objectKeys enc:arrayType="w:CAdxParamKeyValue[1]" xsi:type="enc:Array"><item><key>ITMREF</key><value>'+(Escape-Xml $Code)+'</value></item></objectKeys>')
    if ($reply.Status -eq 0 -and -not $reply.ResultXml -and @($reply.Messages | Where-Object { $_.Trim() -ceq 'Fiche inexistante' }).Count -gt 0) {
        return [pscustomobject]@{Code=$Code;Exists=$false;Status=0;Messages=$reply.Messages;Fields=@{}}
    }
    if ($reply.Status -ne 1 -or -not $reply.ResultXml) { throw 'ARTICLE_EXISTENCE_UNKNOWN' }
    $doc=Read-SafeXml $reply.ResultXml
    $key=$doc.SelectNodes('//FLD[@NAME="ITMREF"]')
    if ($key.Count -ne 1 -or $key[0].InnerText -cne $Code) { throw 'READ_KEY_MISMATCH' }
    $fields=@{}
    foreach ($node in $doc.SelectNodes('//GRP/FLD')) { $fields[$node.ParentNode.GetAttribute('ID')+'.'+$node.GetAttribute('NAME')]=$node.InnerText }
    foreach ($list in $doc.SelectNodes('//GRP/LST')) {
        $index=0
        foreach ($item in $list.SelectNodes('./ITM')) {
            $fields[$list.ParentNode.GetAttribute('ID')+'.'+$list.GetAttribute('NAME')+'['+$index+']']=$item.InnerText
            $index++
        }
    }
    foreach ($node in $doc.SelectNodes('//TAB/LIN/FLD')) { $fields[$node.ParentNode.ParentNode.GetAttribute('ID')+'['+$node.ParentNode.GetAttribute('NUM')+'].'+$node.GetAttribute('NAME')]=$node.InnerText }
    [pscustomobject]@{Code=$Code;Exists=$true;Status=1;Messages=$reply.Messages;Fields=$fields}
}
function Get-SageTestArticle {
    [CmdletBinding()]param([Parameter(Mandatory)][string]$Code)
    $null=Get-SageTestDescription
    Read-ArticleInternal $Code
}
function New-SageTestArticlePlan {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Code,[Parameter(Mandatory)][ValidateLength(1,70)][string]$Designation,
          [ValidateLength(1,5)][string]$Category='NEG',[ValidateLength(1,3)][string]$Unit='UN',
          [ValidatePattern('^$|^[A-Z0-9_-]{1,15}$')][string]$SupplierCode='',
          [ValidateSet('','1')][string]$StockManagement='',
          [ValidateSet('','T20')][string]$TaxCode='')
    Assert-Code $Code
    $description=Get-SageTestDescription
    $existing=Read-ArticleInternal $Code
    if ($existing.Exists) { throw 'DUPLICATE_ARTICLE_EXISTS' }
    if ($description.SelectNodes('//MET[@ID="CREATE"]').Count -eq 0) { throw 'CREATE_NOT_PUBLISHED' }
    # Only article fields, no technical identifiers, suppliers or implicit sites.
    $values=[ordered]@{'ITM0_1.TCLCOD'=$Category;'ITM0_1.ITMSTA'='1';'ITM0_1.ITMREF'=$Code;'ITM0_1.DES1AXX'=$Designation}
    if ($SupplierCode) { $values['ITM0_1.XBPS']=$SupplierCode }
    if ($StockManagement) { $values['ITM2_1.STOMGTCOD']=$StockManagement }
    foreach ($entry in @(@('STU',$Unit),@('PUU',$Unit),@('PUUSTUCOE','1'),@('SAU',$Unit),@('SAUSTUCOE','1'))) { $values['ITM3_1.'+$entry[0]]=$entry[1] }
    if ($SupplierCode) { $values['ITP_1[1].BPSNUM']=$SupplierCode }
    $doc=[Xml.XmlDocument]::new();$param=$doc.CreateElement('PARAM');$null=$doc.AppendChild($param);$groups=@{}
    foreach ($path in $values.Keys) {
        $group,$name=$path.Split('.')
        $isTable=$group -eq 'ITP_1[1]'
        $groupName=if($isTable){'ITP_1'}else{$group}
        $meta=$description.SelectSingleNode('/ADXDOC/ADXDATA/GRP[@NAM="'+$groupName+'"]/FLD[@NAM="'+$name+'"]')
        if (-not $meta -or $meta.GetAttribute('MOD') -cne 'Input' -or ($meta.HasAttribute('DIM') -and $meta.GetAttribute('DIM') -ne '1')) { throw 'FIELD_NOT_PUBLISHED_SCALAR_INPUT' }
        $value=[string]$values[$path]
        if ($meta.GetAttribute('TYP') -eq 'Char' -and $value.Length -gt [int]$meta.GetAttribute('LEN')) { throw 'FIELD_TOO_LONG' }
        if ($meta.HasAttribute('MEN')) {
            $options=$description.SelectNodes('/ADXDOC/ADXMEN/MNU[@NO="'+$meta.GetAttribute('MEN')+'"]/VAL')
            if (@($options | Where-Object { $_.GetAttribute('IND') -ceq $value }).Count -eq 0) { throw 'INVALID_PUBLISHED_MENU_VALUE' }
        }
        if (-not $groups.ContainsKey($group)) {
            $g=$doc.CreateElement($(if($isTable){'TAB'}else{'GRP'}));$g.SetAttribute('ID',$groupName);$null=$param.AppendChild($g)
            if ($isTable) {
                if ($meta.ParentNode.GetAttribute('TYB') -cne 'Table') { throw 'SUPPLIER_TABLE_MAPPING_CHANGED' }
                $line=$doc.CreateElement('LIN');$line.SetAttribute('NUM','1');$null=$g.AppendChild($line);$groups[$group]=$line
            } else { $groups[$group]=$g }
        }
        $f=$doc.CreateElement('FLD');$f.SetAttribute('NAME',$name);$f.InnerText=$value;$null=$groups[$group].AppendChild($f)
    }
    if ($TaxCode) {
        $meta=$description.SelectSingleNode('/ADXDOC/ADXDATA/GRP[@NAM="ITM5_1"]/FLD[@NAM="VACITM"]')
        if (-not $meta -or $meta.GetAttribute('MOD') -cne 'Input' -or $meta.GetAttribute('TYP') -cne 'Char' -or $meta.GetAttribute('DIM') -cne '3' -or $TaxCode.Length -gt [int]$meta.GetAttribute('LEN')) { throw 'TAX_LIST_MAPPING_CHANGED' }
        $g=$doc.CreateElement('GRP');$g.SetAttribute('ID','ITM5_1');$null=$param.AppendChild($g)
        $list=$doc.CreateElement('LST');$list.SetAttribute('NAME','VACITM');$list.SetAttribute('SIZE','3');$list.SetAttribute('TYPE','Char');$null=$g.AppendChild($list)
        for ($i=0;$i -lt 3;$i++) {
            $value=if($i -eq 0){$TaxCode}else{''}
            $item=$doc.CreateElement('ITM');$item.InnerText=$value;$null=$list.AppendChild($item)
            $values['ITM5_1.VACITM['+$i+']']=$value
        }
    }
    [pscustomobject]@{Code=$Code;Designation=$Designation;Category=$Category;Unit=$Unit;SupplierCode=$SupplierCode;StockManagement=$StockManagement;TaxCode=$TaxCode;Folder='TEST';Pool='POOL_AI_TEST';
        ObjectXml=$doc.OuterXml;Digest=(Get-Hash $doc.OuterXml);DescriptionHash=(Get-DescriptionHash $description);
        Fields=$values;DuplicateChecked=$true;HumanApprovalRequired=$true;SaveSent=$false;
        ReviewRequired='Review category defaults and explicit fields. No site or supplier master will be created. A supplied vendor is linked in ITP_1.BPSNUM.'}
}
function Get-DescriptionHash($Description) {
    $copy=$Description.CloneNode($true);$copy.DocumentElement.RemoveAttribute('TIM')
    Get-Hash $copy.OuterXml
}
function Invoke-SageTestArticleCreation {
    [CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
    param([Parameter(Mandatory)]$Plan,[switch]$AuthorizedTestAgent004,$ApprovalReceipt=$null)
    Assert-Code $Plan.Code
    # Rebuild from the actual publication and key before displaying a human challenge.
    $extras=@{}
    if ($Plan.PSObject.Properties['SupplierCode']) {$extras.SupplierCode=[string]$Plan.SupplierCode}
    if ($Plan.PSObject.Properties['StockManagement']) {$extras.StockManagement=[string]$Plan.StockManagement}
    if ($Plan.PSObject.Properties['TaxCode']) {$extras.TaxCode=[string]$Plan.TaxCode}
    $fresh=New-SageTestArticlePlan -Code $Plan.Code -Designation $Plan.Designation -Category $Plan.Category -Unit $Plan.Unit @extras
    if ($fresh.Digest -cne $Plan.Digest -or $fresh.DescriptionHash -cne $Plan.DescriptionHash -or (Get-Hash $Plan.ObjectXml) -cne $fresh.Digest) { throw 'PLAN_CHANGED_REBUILD_AND_REVIEW' }
    if (-not $PSCmdlet.ShouldProcess(('V12/TEST/'+$fresh.Code),'One SOAP SAVE followed by READ')) { return }
    Write-Host $fresh.ObjectXml
    Write-Host $fresh.ReviewRequired
    $phrase='CREER TEST '+$fresh.Code+' '+$fresh.Digest
    if ($ApprovalReceipt) {
        if ($fresh.TaxCode) { throw 'TAX_REQUIRES_INTERACTIVE_APPROVAL' }
        $foamNames=@{'MFB-A-XPS-40'='Modern foam boards A XPS 4 CM';'MFB-B-XPS-40'='Modern foam boards B XPS 4 CM'}
        $foam=$foamNames.ContainsKey([string]$fresh.Code) -and $fresh.Designation -ceq $foamNames[[string]$fresh.Code] -and $fresh.Unit -ceq 'M2' -and -not $fresh.SupplierCode -and -not $fresh.StockManagement
        $requiredSite=if($foam){'202'}else{'201'}
        $expiry=[DateTimeOffset]::Parse([string]$ApprovalReceipt.ExpiresAt)
        if ($ApprovalReceipt.Approved -ne $true -or $ApprovalReceipt.Folder -cne 'TEST' -or
            $ApprovalReceipt.Site -cne $requiredSite -or $ApprovalReceipt.Code -cne $fresh.Code -or
            $ApprovalReceipt.Digest -cne $fresh.Digest -or $ApprovalReceipt.DescriptionHash -cne $fresh.DescriptionHash -or
            $expiry -le [DateTimeOffset]::UtcNow -or $expiry -gt [DateTimeOffset]::UtcNow.AddMinutes(15) -or
            [string]$ApprovalReceipt.Actor -notmatch '^chat:[0-9a-f-]{36}$') { throw 'WEB_HUMAN_APPROVAL_INVALID' }
        $extinguisher=$fresh.Code -ceq 'EXT_POUDRE' -and $fresh.Designation -ieq ('Extincteur '+[char]0xe0+' poudre') -and $fresh.SupplierCode -ceq 'F1025' -and $fresh.StockManagement -ceq '1'
        if (($fresh.Code -cnotmatch '^TEST[A-Z0-9_.-]{1,16}$' -and -not $extinguisher -and -not $foam) -or $fresh.Category -cne 'NEG' -or $fresh.Unit -cne $(if($foam){'M2'}else{'UN'})) { throw 'OUTSIDE_WEB_TEST_SCOPE' }
        if (-not $extinguisher -and ($fresh.SupplierCode -or $fresh.StockManagement)) { throw 'OUTSIDE_WEB_TEST_SCOPE' }
    } elseif ($AuthorizedTestAgent004) {
        # Explicit user authorization received in this session, for these exact
        # business values only. Does not authorize another code or a second SAVE.
        if ($fresh.Code -cne 'TESTAGENT004' -or $fresh.Designation -cne 'ARTICLE TEST CREATION AGENT IA' -or $fresh.Category -cne 'NEG' -or $fresh.Unit -cne 'UN' -or $fresh.SupplierCode -or $fresh.StockManagement -or $fresh.TaxCode) { throw 'OUTSIDE_EXPLICIT_USER_AUTHORIZATION' }
    } else {
        $answer=Read-Host ('After business review, type exactly: '+$phrase)
        if ($answer -cne $phrase) { throw 'HUMAN_APPROVAL_NOT_GIVEN' }
    }
    # Revalidate after the human's response, before consuming the permanent attempt.
    $current=Get-SageTestDescription
    if ((Get-DescriptionHash $current) -cne $fresh.DescriptionHash) { throw 'PUBLICATION_CHANGED_AFTER_APPROVAL' }
    if ((Read-ArticleInternal $fresh.Code).Exists) { throw 'DUPLICATE_ARTICLE_EXISTS' }
    $directory=Join-Path $script:Root 'runtime\powershell-soap-attempts'
    $null=New-Item -ItemType Directory -Path $directory -Force
    $marker=Join-Path $directory ($fresh.Code+'.attempt.json')
    $result=[ordered]@{Code=$fresh.Code;Folder='TEST';Digest=$fresh.Digest;At=[DateTime]::UtcNow.ToString('o');
        SaveAttempts=1;SaveStatus=$null;Messages=@();ReadConfirmed=$false;RetryAllowed=$false;State='CLAIMED'}
    # CreateNew is atomic across processes. Never remove this marker to retry.
    $stream=[IO.File]::Open($marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $bytes=[Text.Encoding]::UTF8.GetBytes(($result | ConvertTo-Json -Depth 6));$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true) }
    finally { $stream.Dispose() }
    try {
        $saved=Invoke-TestSoap save ('<objectXml>'+(Escape-Xml $fresh.ObjectXml)+'</objectXml>')
        $result.SaveStatus=$saved.Status;$result.Messages=$saved.Messages
    } catch { $result.State='SAVE_OUTCOME_UNKNOWN' }
    try {
        $read=Read-ArticleInternal $fresh.Code
        $matches=$read.Exists
        foreach ($path in $fresh.Fields.Keys) {
            $actual=$read.Fields[$path];$expected=[string]$fresh.Fields[$path]
            if ($path -in @('ITM3_1.PUUSTUCOE','ITM3_1.SAUSTUCOE')) {
                $number=[decimal]0
                if (-not [decimal]::TryParse([string]$actual,[Globalization.NumberStyles]::Number,[Globalization.CultureInfo]::InvariantCulture,[ref]$number) -or $number -ne [decimal]1) { $matches=$false }
            } elseif ($actual -cne $expected) { $matches=$false }
        }
        $result.ReadConfirmed=$matches
        $result['ReadStatus']=$read.Status
        $result['ReadFields']=$read.Fields
    } catch { $result['ReadError']='READBACK_UNAVAILABLE' }
    if ($result.SaveStatus -eq 1 -and $result.ReadConfirmed) { $result.State='CREATED_AND_READ_BACK' }
    elseif ($result.State -ne 'SAVE_OUTCOME_UNKNOWN') { $result.State='UNCONFIRMED_DO_NOT_RETRY' }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ($marker+'.result.json') -Encoding UTF8
    [pscustomobject]$result
}
Export-ModuleMember -Function Connect-SageTestSoap,Disconnect-SageTestSoap,Get-SageTestDescription,Get-SageTestArticle,New-SageTestArticlePlan,Invoke-SageTestArticleCreation
