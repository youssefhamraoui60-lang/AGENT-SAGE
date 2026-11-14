# Narrow, read-only diagnostics authorized for the reported site/category/supplier errors.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$cred=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
$secret=$cred.Password.Copy();$secret.MakeReadOnly()
$cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=AGENT-chat-correction-SELECT')
$cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
$out=[ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');writes=0;queries=@();results=@{};errors=@{}}
function Read([string]$name,[string]$sql,[hashtable]$parameters=@{}) {
 $out.queries+=@{name=$name;sql=$sql;parameters=$parameters};$cmd=$cn.CreateCommand();$cmd.CommandText=$sql;$cmd.CommandTimeout=4;$r=$null
 foreach($key in $parameters.Keys){$p=$cmd.Parameters.Add($key,[System.Data.SqlDbType]::NVarChar,128);$p.Value=$parameters[$key]}
 try {$r=$cmd.ExecuteReader();$rows=@();while($r.Read()){$row=[ordered]@{};for($i=0;$i -lt $r.FieldCount;$i++){$row[$r.GetName($i)]=if($r.IsDBNull($i)){$null}else{$r.GetValue($i)}};$rows+=@([pscustomobject]$row)};$out.results[$name]=@($rows)}
 catch {$out.errors[$name]=$_.Exception.GetBaseException().Message}
 finally {if($r){$r.Dispose()};$cmd.Dispose()}
}
try {
 $cn.Open()
 Read 'sites_TEST' 'SELECT TOP (51) FCY_0,LEGCPY_0,CRY_0,WRHFLG_0,PURFLG_0,SALFLG_0 FROM TEST.FACILITY ORDER BY FCY_0'
 Read 'site_131_TEST' 'SELECT TOP (2) FCY_0,LEGCPY_0,WRHFLG_0 FROM TEST.FACILITY WHERE FCY_0=@Code' @{'@Code'='131'}
 Read 'site_131_article_sites' 'SELECT TOP (3) ITMREF_0,STOFCY_0 FROM TEST.ITMFACILIT WHERE STOFCY_0=@Code ORDER BY ITMREF_0' @{'@Code'='131'}
 Read 'category_rows' 'SELECT TOP (30) TCLCOD_0,TCLDES_0,STOFCY_0,STU_0,ACCCOD_0,VACITM_0 FROM TEST.ITMCATEG WHERE TCLCOD_0 IN (@A,@B) OR TCLDES_0 COLLATE Latin1_General_CI_AI LIKE @Label ORDER BY TCLCOD_0,STOFCY_0' @{'@A'='AR';'@B'='NEG';'@Label'='%NEGO%'}
 Read 'category_key' "SELECT TOP (20) i.name,i.is_unique,c.name AS column_name,ic.key_ordinal FROM sys.indexes i JOIN sys.index_columns ic ON i.object_id=ic.object_id AND i.index_id=ic.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id WHERE i.object_id=OBJECT_ID('TEST.ITMCATEG') AND ic.key_ordinal>0 ORDER BY i.name,ic.key_ordinal"
 Read 'supplier_F992' 'SELECT TOP (2) s.BPSNUM_0,p.BPRNAM_0,p.BPRNAM_1 FROM TEST.BPSUPPLIER s LEFT JOIN TEST.BPARTNER p ON p.BPRNUM_0=s.BPSNUM_0 WHERE s.BPSNUM_0=@Code' @{'@Code'='F992'}
 Read 'supplier_Modern' 'SELECT TOP (5) s.BPSNUM_0,p.BPRNAM_0,p.BPRNAM_1 FROM TEST.BPSUPPLIER s JOIN TEST.BPARTNER p ON p.BPRNUM_0=s.BPSNUM_0 WHERE p.BPRNAM_0 LIKE @Label OR p.BPRNAM_1 LIKE @Label ORDER BY s.BPSNUM_0' @{'@Label'='%Modern%'}
 Read 'XPS_references' 'SELECT TOP (3) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,ACCCOD_0,VACITM_0 FROM TEST.ITMMASTER WHERE ITMREF_0 IN (@A,@B,@C)' @{'@A'='E-XPS_8';'@B'='XPS_FO2500_40';'@C'='XPS_SL_40'}
 Read 'accounting' 'SELECT TOP (10) TYP_0,ACCCOD_0,COA_0,DES_0 FROM TEST.GACCCODE WHERE TYP_0=1 AND ACCCOD_0 IN (@A,@B)' @{'@A'='POLYSTYREN';'@B'='61110001'}
 Read 'tax_level_T20' 'SELECT TOP (10) COD_0,LEG_0,ENAFLG_0,VACITM_0,VACBPR_0,VAT_0,VACDES_0 FROM TEST.TABVAC WHERE VACITM_0=@Level ORDER BY COD_0' @{'@Level'='T20'}
 Read 'tax_T20' 'SELECT TOP (10) v.VAT_0,v.LEG_0,v.VATDES_0,r.CPY_0,r.STRDAT_0,r.VATRAT_0 FROM TEST.TABVAT v LEFT JOIN TEST.TABRATVAT r ON r.VAT_0=v.VAT_0 AND r.LEG_0=v.LEG_0 WHERE v.VAT_0=@Code ORDER BY r.STRDAT_0 DESC' @{'@Code'='T20'}
 Read 'facility_schemas' "SELECT TOP (20) s.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE t.name='FACILITY' ORDER BY s.name"
 foreach($row in $out.results.facility_schemas){if($row.name -eq 'TEST'){continue};$quoted='['+$row.name.Replace(']',']]')+']';Read ('site_131_'+$row.name) ('SELECT TOP (1) FCY_0 FROM '+$quoted+'.FACILITY WHERE FCY_0=@Code') @{'@Code'='131'}}
} finally {$cn.Dispose();$secret.Dispose()}
$out | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $root 'logs/chat-corrections-sql-diagnostic.json') -Encoding UTF8
Write-Output 'Read-only diagnostic saved: logs/chat-corrections-sql-diagnostic.json'
