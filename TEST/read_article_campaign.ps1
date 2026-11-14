# Fixed SELECT only. No dynamic SQL, permissions or production access.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null
try {
 if((Get-SupplierTarget) -cne 'TEST'){throw 'TEST only'}
 $inputData=[Console]::In.ReadToEnd()|ConvertFrom-Json
 $codes=@($inputData.codes)
 if($codes.Count -gt 250 -or @($codes|Where-Object {$_ -cnotmatch '^CX[A-Z0-9]{1,18}$'}).Count){throw 'Invalid campaign identifiers'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=45
 $cmd.CommandText=@'
SET NOCOUNT ON;
SELECT (SELECT a.ITMREF_0 AS code,a.ITMDES1_0 AS designation,a.TCLCOD_0 AS category,a.STOMGTCOD_0 AS stock_mode,a.STU_0 AS unit,a.PURFLG_0 AS purchased,a.SALFLG_0 AS sold,
 (SELECT f.STOFCY_0 AS site FROM TEST.ITMFACILIT f WHERE f.ITMREF_0=a.ITMREF_0 ORDER BY f.STOFCY_0 FOR JSON PATH) AS sites,
 (SELECT COUNT(*) FROM TEST.ITMSALES s WHERE s.ITMREF_0=a.ITMREF_0) AS sales_records,
 (SELECT COUNT(*) FROM TEST.ITMBPS p WHERE p.ITMREF_0=a.ITMREF_0) AS supplier_records,
 (SELECT COUNT(*) FROM TEST.ATEXTRA t WHERE t.CODFIC_0='ITMMASTER' AND t.IDENT1_0=a.ITMREF_0 AND t.LANGUE_0='FRA') AS french_records
 FROM TEST.ITMMASTER a WHERE a.ITMREF_0 IN (SELECT value FROM OPENJSON(@Codes)) ORDER BY a.ITMREF_0 FOR JSON PATH);
'@
 $parameter=$cmd.Parameters.Add('@Codes',[Data.SqlDbType]::NVarChar,-1);$parameter.Value=ConvertTo-Json -InputObject $codes -Compress
 [Console]::WriteLine([string]$cmd.ExecuteScalar())
}finally{if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
