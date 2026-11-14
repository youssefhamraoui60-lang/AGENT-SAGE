# Fixed SELECT queries only. Never executes SQL supplied by Telegram or the model.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$cn = $null
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $cred = Import-Clixml (Join-Path $PSScriptRoot '../runtime/sql-reader-credential.clixml')
    $secret = $cred.Password.Copy(); $secret.MakeReadOnly()
    $cn = [System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Application Name=SOB-preparation-SELECT;ApplicationIntent=ReadOnly')
    $cn.Credential = [System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
    $cn.Open()
    $cmd = $cn.CreateCommand(); $cmd.CommandTimeout = 8
    $cmd.CommandText = switch ($request.kind) {
        'delivery_status' { 'WITH O AS (SELECT TOP(3) H.SOHNUM_0,H.ORDDAT_0,H.BPCORD_0,H.DLVSTA_0,H.ORDSTA_0 FROM TEST.SORDER H WHERE ((@Code<>'''' AND H.SOHNUM_0=@Code) OR (@Code=''recent'' AND H.BPCORD_0=@Client AND H.ORDDAT_0>=DATEADD(day,-60,CAST(GETDATE() AS date)))) AND EXISTS(SELECT 1 FROM TEST.SORDERQ Q WHERE Q.SOHNUM_0=H.SOHNUM_0 AND (@Article='''' OR Q.ITMREF_0=@Article OR (@Article=''CPJ'' AND Q.ITMREF_0 LIKE ''CPJ%''))) ORDER BY H.ORDDAT_0 DESC,H.CREDATTIM_0 DESC,H.SOHNUM_0 DESC) SELECT O.SOHNUM_0,O.BPCORD_0,O.DLVSTA_0,O.ORDSTA_0,D.SDHNUM_0,DH.CFMFLG_0,SUM(D.QTY_0) AS DOCUMENT_QTY FROM O LEFT JOIN TEST.SDELIVERYD D ON D.SOHNUM_0=O.SOHNUM_0 AND (@Article='''' OR D.ITMREF_0=@Article OR (@Article=''CPJ'' AND D.ITMREF_0 LIKE ''CPJ%'')) LEFT JOIN TEST.SDELIVERY DH ON DH.SDHNUM_0=D.SDHNUM_0 GROUP BY O.SOHNUM_0,O.BPCORD_0,O.DLVSTA_0,O.ORDSTA_0,D.SDHNUM_0,DH.CFMFLG_0 ORDER BY O.SOHNUM_0 DESC,D.SDHNUM_0 DESC' }
        'delivery_schema' { 'SELECT S.name AS dossier,T.name AS table_name,C.name AS column_name,HAS_PERMS_BY_NAME(QUOTENAME(S.name)+N''.''+QUOTENAME(T.name),''OBJECT'',''SELECT'') AS can_read FROM sys.tables T JOIN sys.schemas S ON S.schema_id=T.schema_id JOIN sys.columns C ON C.object_id=T.object_id WHERE S.name IN (''TEST'',''OB'') AND T.name IN (''SDELIVERY'',''SDELIVERYD'') AND (C.name IN (''SDHNUM_0'',''SOHNUM_0'',''SOPLIN_0'',''SOQSEQ_0'',''ITMREF_0'',''QTY_0'',''CFMFLG_0'',''DLVDAT_0'',''BPCORD_0'') OR C.name LIKE ''%STA%'') ORDER BY S.name,T.name,C.column_id' }
        'order_lines' { 'SELECT H.SOHNUM_0,H.BPCORD_0,H.ORDATI_0,P.SOPLIN_0,P.ITMREF_0,P.SAU_0,P.NETPRIATI_0,Q.QTY_0,Q.XBPS_0 FROM TEST.SORDER H JOIN TEST.SORDERP P ON P.SOHNUM_0=H.SOHNUM_0 JOIN TEST.SORDERQ Q ON Q.SOHNUM_0=P.SOHNUM_0 AND Q.SOPLIN_0=P.SOPLIN_0 AND Q.SOQSEQ_0=P.SOPSEQ_0 WHERE H.SOHNUM_0=@Code ORDER BY P.SOPLIN_0' }
        'supplier' { 'SELECT TOP(25) BPSNUM_0,BPSNAM_0 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=@Code OR REPLACE(REPLACE(BPSNAM_0,'' '',''''),''.'','''') COLLATE Latin1_General_CI_AI LIKE @Pattern ESCAPE ''~'' ORDER BY BPSNUM_0' }
        'article_supplier' { 'SELECT ITMREF_0,BPSNUM_0 FROM TEST.ITMBPS WHERE ITMREF_0=@Code AND BPSNUM_0=@Client' }
        'client_by_ice' { 'SELECT C.BPCNUM_0,C.BPCNAM_0,C.CUR_0,C.REP_0,C.VACBPR_0 FROM TEST.BPCUSTOMER C JOIN TEST.BPARTNER B ON B.BPRNUM_0=C.BPCNUM_0 WHERE B.XICE_0=@Code ORDER BY C.BPCNUM_0' }
        'client_profile' { 'SELECT BPCNUM_0,BPCNAM_0,CUR_0,REP_0,VACBPR_0,IME_0,BPAADD_0,BPCINV_0,BPCPYR_0,BPAPYR_0,PTE_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@Code' }
        'last_price' { 'SELECT TOP (1) P.NETPRIATI_0 AS PRICE_TTC,P.SAU_0,H.CUR_0,H.SOHNUM_0,H.ORDDAT_0 FROM TEST.SORDERP P JOIN TEST.SORDER H ON H.SOHNUM_0=P.SOHNUM_0 WHERE H.BPCORD_0=@Client AND NOT EXISTS(SELECT 1 FROM OPENJSON(@ExcludedOrdersJSON) X WHERE X.value=H.SOHNUM_0) AND P.ITMREF_0=@Code AND P.NETPRIATI_0 IS NOT NULL AND P.NETPRIATI_0>=0 AND H.CUR_0=(SELECT CUR_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@Client) AND P.SAU_0=(SELECT SAU_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code) ORDER BY H.ORDDAT_0 DESC,H.CREDATTIM_0 DESC,H.SOHNUM_0 DESC,P.SOPLIN_0 DESC,P.SOPSEQ_0 DESC' }
        'receipt' { 'SELECT TOP (2) SOHNUM_0 FROM TEST.SORDER WHERE CUSORDREF_0=@Code ORDER BY SOHNUM_0' }
        'permissions' { 'SELECT HAS_PERMS_BY_NAME(''TEST.SORDER'',''OBJECT'',''INSERT'') AS SORDER_INSERT,HAS_PERMS_BY_NAME(''TEST.SORDERP'',''OBJECT'',''INSERT'') AS SORDERP_INSERT,HAS_PERMS_BY_NAME(''TEST.SORDERQ'',''OBJECT'',''INSERT'') AS SORDERQ_INSERT,HAS_PERMS_BY_NAME(''TEST.SVCRVAT'',''OBJECT'',''INSERT'') AS SVCRVAT_INSERT,HAS_PERMS_BY_NAME(''TEST.AVALNUM'',''OBJECT'',''UPDATE'',''VALEUR_0'',''COLUMN'') AS COUNTER_UPDATE' }
        'client' { 'SELECT TOP (25) BPCNUM_0,BPCNAM_0,CUR_0,REP_0,VACBPR_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@Code OR ((REPLACE(REPLACE(REPLACE(BPCNAM_0,''.'',''''),'' '',''''),''-'','''') COLLATE Latin1_General_CI_AI LIKE @Pattern ESCAPE ''~'' OR REPLACE(REPLACE(REPLACE(BPCNAM_0,''.'',''''),'' '',''''),''-'','''') COLLATE Latin1_General_CI_AI LIKE @ReversePattern ESCAPE ''~'' ) AND (@Representative='''' OR REP_0=@Representative)) ORDER BY BPCNUM_0' }
        'representative' { 'SELECT TOP (25) REPNUM_0,REPNAM_0 FROM TEST.SALESREP WHERE REPNUM_0=@Code OR REPLACE(REPLACE(REPLACE(REPNAM_0,''_'',''''),'' '',''''),''.'','''') COLLATE Latin1_General_CI_AI LIKE @Pattern ESCAPE ''~'' OR REPLACE(REPLACE(REPLACE(REPNAM_0,''_'',''''),'' '',''''),''.'','''') COLLATE Latin1_General_CI_AI LIKE @ReversePattern ESCAPE ''~'' ORDER BY REPNUM_0' }
        'article' { 'SELECT TOP (25) I.ITMREF_0,I.ITMDES1_0,I.SAU_0,I.SAUSTUCOE_0,I.VACITM_0,CASE WHEN F.ITMREF_0 IS NULL THEN 0 ELSE 1 END AS SITE_OK FROM TEST.ITMMASTER I LEFT JOIN TEST.ITMFACILIT F ON F.ITMREF_0=I.ITMREF_0 AND F.STOFCY_0=''201'' WHERE REPLACE(REPLACE(REPLACE(REPLACE(I.ITMREF_0,'' '',''''),''.'',''''),''-'',''''),''_'','''')=@Normalized OR REPLACE(REPLACE(REPLACE(I.ITMDES1_0,'' '',''''),''.'',''''),''-'','''') COLLATE Latin1_General_CI_AI LIKE @Pattern ESCAPE ''~'' ORDER BY CASE WHEN REPLACE(REPLACE(REPLACE(REPLACE(I.ITMREF_0,'' '',''''),''.'',''''),''-'',''''),''_'','''')=@Normalized THEN 0 ELSE 1 END,I.ITMREF_0' }
        default { throw 'Unknown SELECT' }
    }
    $folder = if ($request.folder) { [string]$request.folder } else { 'TEST' }
    if ($folder -notin @('TEST','OB')) { throw 'Invalid reference folder' }
    if ($folder -eq 'OB') { $cmd.CommandText=$cmd.CommandText.Replace('TEST.','OB.') }
    $code = [string]$request.code
    if ($code.Length -gt 100 -or $code.Length -eq 0) { throw 'Invalid search' }
    $parts = @($code -split '[\s._-]+' | Where-Object {$_})
    $escapedParts = @($parts | ForEach-Object {$_.Replace('~','~~').Replace('%','~%').Replace('[','~[')})
    $pattern = '%' + ($escapedParts -join '%') + '%'
    [array]::Reverse($escapedParts)
    $reversePattern = '%' + ($escapedParts -join '%') + '%'
    if (([string]$request.representative).Length -gt 30) { throw 'Invalid representative' }
    $null = $cmd.Parameters.Add('@Representative',[System.Data.SqlDbType]::NVarChar,30); $cmd.Parameters['@Representative'].Value = [string]$request.representative
    if (([string]$request.article).Length -gt 40) { throw 'Invalid article' }
    $null=$cmd.Parameters.Add('@Article',[System.Data.SqlDbType]::NVarChar,40);$cmd.Parameters['@Article'].Value=[string]$request.article
    $null = $cmd.Parameters.Add('@Code',[System.Data.SqlDbType]::NVarChar,100); $cmd.Parameters['@Code'].Value = $code
    if (([string]$request.client).Length -gt 30) { throw 'Invalid client' }
    $null = $cmd.Parameters.Add('@Client',[System.Data.SqlDbType]::NVarChar,30); $cmd.Parameters['@Client'].Value = [string]$request.client
    $null = $cmd.Parameters.Add('@Pattern',[System.Data.SqlDbType]::NVarChar,220); $cmd.Parameters['@Pattern'].Value = $pattern
    $null = $cmd.Parameters.Add('@ReversePattern',[System.Data.SqlDbType]::NVarChar,220); $cmd.Parameters['@ReversePattern'].Value = $reversePattern
    $null = $cmd.Parameters.Add('@Normalized',[System.Data.SqlDbType]::NVarChar,100); $cmd.Parameters['@Normalized'].Value = ($parts -join '')
    if (@($request.excluded_orders).Count -gt 1000) { throw 'Exclusion limit' }
    foreach ($number in $request.excluded_orders) { if ($number -notmatch '^2026ARC[0-9]+$') { throw 'Invalid exclusion' } }
    $null=$cmd.Parameters.Add('@ExcludedOrdersJSON',[System.Data.SqlDbType]::NVarChar,-1)
    $cmd.Parameters['@ExcludedOrdersJSON'].Value=ConvertTo-Json -InputObject @($request.excluded_orders | Where-Object {$_}) -Compress
    $rd = $cmd.ExecuteReader(); $rows = @()
    while ($rd.Read()) {
        $row = [ordered]@{}
        for ($i=0; $i -lt $rd.FieldCount; $i++) { $row[$rd.GetName($i)] = if ($rd.IsDBNull($i)) { $null } else { $rd.GetValue($i) } }
        $rows += [pscustomobject]$row
    }
    @{ok=$true;folder=$folder;rows=@($rows)} | ConvertTo-Json -Depth 6 -Compress
} catch { @{ok=$false;rows=@();error='Lecture Sage indisponible'} | ConvertTo-Json -Compress }
finally { if ($cn) { $cn.Dispose() }; if ($secret) { $secret.Dispose() } }
