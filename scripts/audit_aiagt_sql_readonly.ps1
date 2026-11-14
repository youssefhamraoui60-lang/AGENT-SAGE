param([ValidateSet('metadata','status')][string]$Phase='metadata')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$outdir=Join-Path $root 'tests/ai-evaluation/reports/soap-save-readiness-20261030'
New-Item -ItemType Directory -Path $outdir -Force | Out-Null
$cred=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
$secret=$cred.Password.Copy();$secret.MakeReadOnly()
$cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;ApplicationIntent=ReadOnly;Application Name=AGENT-AIAGT-SELECT-audit')
$cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
function Read-Only([string]$Query){
 if($Query -notmatch '^SELECT\b' -or $Query -match '\b(INSERT|UPDATE|DELETE|MERGE|EXEC|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b'){throw 'SELECT_ONLY_BOUNDARY'}
 $cmd=$cn.CreateCommand();$cmd.CommandText=$Query;$cmd.CommandTimeout=5;$reader=$null
 try{$reader=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new();while($reader.Read()){$r=[ordered]@{};for($i=0;$i -lt $reader.FieldCount;$i++){$r[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}};$rows.Add([pscustomobject]$r)};return @{ok=$true;rows=$rows.ToArray()}}
 catch{return @{ok=$false;code='read_unavailable';rows=@()}}
 finally{if($reader){$reader.Dispose()};$cmd.Dispose()}
}
$out=[ordered]@{at=[DateTime]::UtcNow.ToString('o');phase=$Phase;sql_writes=0;results=@{}}
try{
 $cn.Open()
 if($Phase -eq 'metadata'){
  $out.results.columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('X3','TEST') AND t.name IN ('AUTILIS','AFONCTION','AFTPRO','APROFIL','AUSERS','AUSER','AFCYPRO','AUTILPROF','AUSRPROF') ORDER BY s.name,t.name,c.column_id"
  $out.results.rights_tables=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('X3','TEST') AND (t.name LIKE 'AFCT%' OR t.name LIKE 'AFT%' OR t.name LIKE 'AFPRO%' OR t.name LIKE 'AFCY%') ORDER BY s.name,t.name,c.column_id"
 }
 if($Phase -eq 'status'){
  foreach($folder in 'X3','TEST'){
   $out.results["${folder}_AIAGT"]=Read-Only "SELECT USR_0,NOMUSR_0,LOGIN_0,ENAFLG_0,PRFFCT_0,PRFMEN_0,ALLACS_0,ACSUSR_0,CREUSR_0,UPDUSR_0,CONVERT(varchar(33),CREDATTIM_0,126) AS created_at,CONVERT(varchar(33),UPDDATTIM_0,126) AS updated_at FROM $folder.AUTILIS WHERE USR_0='AIAGT' OR LOGIN_0='AIAGT'"
   $out.results["${folder}_profiles"]=Read-Only "SELECT CODPRF_0,TYPPRF_0,MODULE_0,MENDEP_0 FROM $folder.APROFIL WHERE CODPRF_0 IN (SELECT PRFFCT_0 FROM $folder.AUTILIS WHERE USR_0='AIAGT' OR LOGIN_0='AIAGT') OR CODPRF_0='AITST'"
   $out.results["${folder}_function_profile"]=Read-Only "SELECT PRFCOD_0,ALLFCT_0,ALLACS_0,FILTRE_0 FROM $folder.AFCTFCT WHERE PRFCOD_0 IN (SELECT PRFFCT_0 FROM $folder.AUTILIS WHERE USR_0='AIAGT' OR LOGIN_0='AIAGT') OR PRFCOD_0='AITST'"
   $out.results["${folder}_function_rights"]=Read-Only "SELECT PRFCOD_0,FNC_0,FCYGRUCOD_0,FCYGRU_0,ACS_0,OPT_0 FROM $folder.AFCTPRF WHERE PRFCOD_0 IN (SELECT PRFFCT_0 FROM $folder.AUTILIS WHERE USR_0='AIAGT' OR LOGIN_0='AIAGT') OR PRFCOD_0='AITST'"
   $out.results["${folder}_site_rights"]=Read-Only "SELECT PRFCOD_0,FNC_0,FCY_0,OPT_0 FROM $folder.AFCTFCY WHERE (PRFCOD_0 IN (SELECT PRFFCT_0 FROM $folder.AUTILIS WHERE USR_0='AIAGT' OR LOGIN_0='AIAGT') OR PRFCOD_0='AITST') AND FNC_0 IN ('GESITM','GESBPS','GESITF','GESAUS','GESAFT')"
   $out.results["${folder}_menus"]=Read-Only "SELECT z.CODFIC_0,z.CODZONE_0,z.NOLIB_0,a.LANNUM_0,a.LANMES_0 FROM $folder.ATABZON z JOIN $folder.APLSTD a ON a.LANCHP_0=z.NOLIB_0 AND a.LAN_0='FRA' WHERE (z.CODFIC_0='AUTILIS' AND z.CODZONE_0 IN ('ENAFLG','ALLACS')) OR (z.CODFIC_0='AFCTFCT' AND z.CODZONE_0 IN ('ALLFCT','ALLACS')) ORDER BY z.CODFIC_0,z.CODZONE_0,a.LANNUM_0"
  }
 }
}finally{$cn.Dispose();$secret.Dispose()}
$target=Join-Path $outdir "aiagt-sql-$Phase.json"
$out|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $target -Encoding UTF8
@{evidence=$target;phase=$Phase;sql_writes=0}|ConvertTo-Json -Compress
