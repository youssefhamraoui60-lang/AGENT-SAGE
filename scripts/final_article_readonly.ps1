$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root=Split-Path $PSScriptRoot -Parent
$cred=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
$secret=$cred.Password.Copy();$secret.MakeReadOnly()
$cn=[Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=AGENT-final-article-readonly;ApplicationIntent=ReadOnly')
$cn.Credential=[Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
function Read-Select([string]$sql){
 if($sql -notmatch '^SELECT '){throw 'SELECT only'}
 $cmd=$cn.CreateCommand();$cmd.CommandTimeout=15;$cmd.CommandText=$sql
 $rd=$cmd.ExecuteReader();$rows=@()
 try{while($rd.Read()){$r=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$r[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows+=[pscustomobject]$r}}finally{$rd.Dispose();$cmd.Dispose()}
 return ,$rows
}
try{
 $cn.Open()
 $out=[ordered]@{at=[DateTime]::UtcNow.ToString('o');mode='SELECT_ONLY';connection_mode='TMS_OPTIONAL_ENCRYPTION'}
 $out.columns=Read-Select "SELECT TABLE_NAME,COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='TEST' AND TABLE_NAME IN ('ITMMASTER','ITMBPS','ITMFACILIT','ITMCATEG','FACILITY','TABVAC','TABRATVAT','TABVAT','COMPANY') ORDER BY TABLE_NAME,ORDINAL_POSITION"
 $out.matches=Read-Select "SELECT TOP (150) * FROM TEST.ITMMASTER WHERE ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%NETTOY%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%DEGRAISS%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%ALCALIN%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%ENTRETIEN%' ORDER BY ITMREF_0"
 $out.f890=Read-Select "SELECT TOP (150) m.ITMREF_0,m.ITMDES1_0,m.ITMSTA_0,m.TCLCOD_0,b.* FROM TEST.ITMBPS b JOIN TEST.ITMMASTER m ON m.ITMREF_0=b.ITMREF_0 WHERE b.BPSNUM_0='F890' ORDER BY m.ITMREF_0"
 $predicate="ITMREF_0 IN (SELECT ITMREF_0 FROM TEST.ITMMASTER WHERE ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%NETTOY%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%DEGRAISS%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%ALCALIN%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%ENTRETIEN%')"
 $out.suppliers=Read-Select "SELECT TOP (500) * FROM TEST.ITMBPS WHERE $predicate ORDER BY ITMREF_0,BPSNUM_0"
 $out.sites=Read-Select "SELECT TOP (500) * FROM TEST.ITMFACILIT WHERE $predicate ORDER BY ITMREF_0,STOFCY_0"
 $out.categories=Read-Select "SELECT TOP (300) * FROM TEST.ITMCATEG WHERE TCLCOD_0 IN (SELECT TCLCOD_0 FROM TEST.ITMMASTER WHERE $predicate) ORDER BY TCLCOD_0,STOFCY_0"
 $out.facilities=Read-Select 'SELECT TOP (100) FCY_0,LEGCPY_0,CRY_0,WRHFLG_0,PURFLG_0,SALFLG_0 FROM TEST.FACILITY ORDER BY FCY_0'
 $out.tax=Read-Select "SELECT TOP (100) * FROM TEST.TABVAC WHERE VACBPR_0='MAR' OR COD_0='MAR_T20' ORDER BY COD_0"
 $out.rates=Read-Select "SELECT TOP (100) * FROM TEST.TABRATVAT WHERE VAT_0='T20' ORDER BY STRDAT_0 DESC"
 $out.candidate=Read-Select "SELECT TOP (1) ITMREF_0 FROM TEST.ITMMASTER WHERE ITMREF_0='TAI261026BCE415'"
 $out.maintenance_products=Read-Select "SELECT TOP (150) ITMREF_0,ITMDES1_0,ITMSTA_0,TCLCOD_0,STU_0,PUU_0,SAU_0,STOMGTCOD_0,VACITM_0 FROM TEST.ITMMASTER WHERE ITMSTA_0=1 AND (TCLCOD_0='FOURE' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%DETERG%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%DESINFECT%' OR ITMDES1_0 COLLATE Latin1_General_CI_AI LIKE '%ALCAL%') ORDER BY ITMREF_0"
 $out.f890_sites=Read-Select "SELECT TOP (100) ITMREF_0,STOFCY_0,STOMGTCOD_0 FROM TEST.ITMFACILIT WHERE ITMREF_0 IN (SELECT ITMREF_0 FROM TEST.ITMBPS WHERE BPSNUM_0='F890') ORDER BY ITMREF_0,STOFCY_0"
 $out.company=Read-Select 'SELECT TOP (100) CPY_0,LEG_0 FROM TEST.COMPANY ORDER BY CPY_0'
 $out.unit=Read-Select "SELECT TOP (1) UOM_0,UOMSYM_0,UOMDEC_0 FROM TEST.TABUNIT WHERE UOM_0='UN'"
 $out | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 (Join-Path $root 'logs/final-article-readonly.json')
 [pscustomobject]@{matches=$out.matches.Count;f890=$out.f890.Count;suppliers=$out.suppliers.Count;sites=$out.sites.Count;categories=$out.categories.Count} | ConvertTo-Json
}finally{$cn.Dispose();$secret.Dispose()}
