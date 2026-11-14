param([ValidateSet('initial','details','rules','numbering','numbering2','numbering3','counter_values','profile_checks','final_checks','code_convention','identity_status')][string]$Phase='initial')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root=Split-Path $PSScriptRoot -Parent
$directory=Join-Path $root 'runtime/supplier-ob-audit'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$cred=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
$secret=$cred.Password.Copy();$secret.MakeReadOnly()
$cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;ApplicationIntent=ReadOnly;Application Name=AGENT-supplier-OB-SELECT-audit')
$cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
function Read-Only([string]$Query,[hashtable]$Values=@{}) {
 if($Query -notmatch '^SELECT\b' -or $Query -match '\b(INSERT|UPDATE|DELETE|MERGE|EXEC|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b'){throw 'SELECT_ONLY_BOUNDARY'}
 $cmd=$cn.CreateCommand();$cmd.CommandText=$Query;$cmd.CommandTimeout=15;$reader=$null
 foreach($key in $Values.Keys){$p=$cmd.Parameters.Add($key,[System.Data.SqlDbType]::NVarChar,128);$p.Value=[string]$Values[$key]}
 $watch=[Diagnostics.Stopwatch]::StartNew()
 try{
  $reader=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
  while($reader.Read()){$r=[ordered]@{};for($i=0;$i -lt $reader.FieldCount;$i++){$r[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}};$rows.Add([pscustomobject]$r)}
  return @{ok=$true;rows=$rows.ToArray();elapsed_ms=$watch.Elapsed.TotalMilliseconds}
 }catch{return @{ok=$false;code='read_unavailable';sql_error_number=if($_.Exception.InnerException){$_.Exception.InnerException.Number}else{$null};rows=@()}}
 finally{if($reader){$reader.Dispose()};$cmd.Dispose()}
}
$out=[ordered]@{at=[DateTime]::UtcNow.ToString('o');phase=$Phase;mode='OB_AND_TEST_SELECT_ONLY';sage_writes=0;results=@{}}
try {
 $cn.Open()
 if($Phase -eq 'identity_status'){
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_identity_addresses"]=Read-Only "SELECT * FROM $folder.BPADDRESS WHERE BPATYP_0=1 AND BPANUM_0 IN ('F10022','DROGUERIEPALME') ORDER BY BPANUM_0,BPAADD_0"
   $out.results["${folder}_identities"]=Read-Only "SELECT p.BPRNUM_0,p.BPRNAM_0,p.BPRSHO_0,p.ENAFLG_0 AS partner_active,p.BPSFLG_0,p.XICE_0,p.XIF_0,p.XRC_0,p.CRY_0,p.CUR_0,p.CREUSR_0,CONVERT(varchar(33),p.CREDATTIM_0,126) AS partner_created_at,p.UPDUSR_0,CONVERT(varchar(33),p.UPDDATTIM_0,126) AS partner_updated_at,s.BPSNUM_0,s.BPSNAM_0,s.BPSSHO_0,s.ENAFLG_0 AS supplier_active,s.BSGCOD_0,s.PTE_0,s.VACBPR_0,s.ACCCOD_0,s.BPAADD_0,s.CREUSR_0 AS supplier_created_by,CONVERT(varchar(33),s.CREDATTIM_0,126) AS supplier_created_at,s.UPDUSR_0 AS supplier_updated_by,CONVERT(varchar(33),s.UPDDATTIM_0,126) AS supplier_updated_at FROM $folder.BPARTNER p LEFT JOIN $folder.BPSUPPLIER s ON s.BPSNUM_0=p.BPRNUM_0 WHERE p.BPRNUM_0 IN ('F10022','DROGUERIEPALME') OR p.XICE_0=@Ice OR p.XIF_0=@Fiscal OR p.XRC_0=@Rc ORDER BY p.BPRNUM_0" @{'@Ice'='001850814000094';'@Fiscal'='20734927';'@Rc'='10909'}
   $out.results["${folder}_activation_menu"]=Read-Only "SELECT z.CODFIC_0,z.CODZONE_0,z.NOLIB_0,a.LANNUM_0,a.LANMES_0 FROM $folder.ATABZON z JOIN $folder.APLSTD a ON a.LANCHP_0=z.NOLIB_0 AND a.LAN_0='FRA' WHERE z.CODFIC_0 IN ('BPSUPPLIER','BPARTNER') AND z.CODZONE_0='ENAFLG' ORDER BY z.CODFIC_0,a.LANNUM_0"
  }
 }
 if($Phase -eq 'code_convention'){
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_formats"]=Read-Only "SELECT LEN(RTRIM(BPSNUM_0)) AS code_length,COUNT(*) AS supplier_count,MIN(RTRIM(BPSNUM_0)) AS first_lexical,MAX(RTRIM(BPSNUM_0)) AS last_lexical FROM $folder.BPSUPPLIER WHERE RTRIM(BPSNUM_0) LIKE 'F%' AND SUBSTRING(RTRIM(BPSNUM_0),2,15) NOT LIKE '%[^0-9]%' AND LEN(RTRIM(BPSNUM_0))>1 GROUP BY LEN(RTRIM(BPSNUM_0)) ORDER BY code_length"
   $out.results["${folder}_examples"]=Read-Only "SELECT TOP (15) BPSNUM_0,BPSNAM_0,BSGCOD_0,CREDATTIM_0 FROM $folder.BPSUPPLIER WHERE BPSNUM_0 LIKE 'F%' ORDER BY CREDATTIM_0 DESC,BPSNUM_0 DESC"
   $out.results["${folder}_requested_codes"]=Read-Only "SELECT BPSNUM_0,BPSNAM_0,BSGCOD_0 FROM $folder.BPSUPPLIER WHERE BPSNUM_0 IN ('F012','F0012','F10022','DROGUERIEPALME') ORDER BY BPSNUM_0"
  }
 }
 if($Phase -eq 'initial'){
  $out.results.tables=Read-Only "SELECT s.name AS folder,t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name IN ('OB','TEST') AND (t.name IN ('BPSUPPLIER','BPARTNER','BPADDRESS','CONTACT','CONTACTCRM','BPSCATEG','TABPAYTERM','TABPAYTYP','ATABZON','ATABLE','ATEXTRA','APLSTD','ACODNUM','ACODNUMSEQ','ADOVAL','ADOPAR','GACCCODE','TABVAC','TABVAT') OR t.name LIKE '%PAY%' OR t.name LIKE '%CONTACT%') ORDER BY s.name,t.name"
  $out.results.columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.column_id,c.name AS column_name,ty.name AS data_type,c.max_length,c.is_nullable,c.is_identity,c.is_computed,dc.definition AS default_definition FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id LEFT JOIN sys.default_constraints dc ON dc.object_id=c.default_object_id WHERE s.name IN ('OB','TEST') AND t.name IN ('BPSUPPLIER','BPARTNER','BPADDRESS','CONTACT','CONTACTCRM','BPSCATEG','TABPAYTERM','ATABZON','ATEXTRA','APLSTD','ACODNUM','ACODNUMSEQ','ADOVAL','ADOPAR') ORDER BY s.name,t.name,c.column_id"
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_supplier"]=Read-Only "SELECT * FROM $folder.BPSUPPLIER WHERE BPSNUM_0=@Code" @{'@Code'='F10022'}
   $out.results["${folder}_partner"]=Read-Only "SELECT * FROM $folder.BPARTNER WHERE BPRNUM_0=@Code" @{'@Code'='F10022'}
   $out.results["${folder}_recent_FR"]=Read-Only "SELECT TOP (8) BPSNUM_0,BPSNAM_0,BPSSHO_0,BSGCOD_0,CUR_0,PTE_0,VACBPR_0,ACCCOD_0,CREUSR_0,CREDATTIM_0 FROM $folder.BPSUPPLIER WHERE BSGCOD_0=@Category ORDER BY CREDATTIM_0 DESC,BPSNUM_0 DESC" @{'@Category'='FR'}
  }
 }
 if($Phase -eq 'details'){
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_addresses"]=Read-Only "SELECT * FROM $folder.BPADDRESS WHERE BPANUM_0=@Code" @{'@Code'='F10022'}
   $out.results["${folder}_contacts"]=Read-Only "SELECT * FROM $folder.CONTACT WHERE BPANUM_0=@Code" @{'@Code'='F10022'}
   $out.results["${folder}_contact_people"]=Read-Only "SELECT c.CNTNUM_0,c.CNTFULNAM_0,c.CNTFNA_0,c.CNTLNA_0,c.CNTEMA_0,c.CNTMOB_0 FROM $folder.CONTACTCRM c JOIN $folder.CONTACT l ON l.CCNCRM_0=c.CNTNUM_0 WHERE l.BPANUM_0=@Code" @{'@Code'='F10022'}
   $out.results["${folder}_category"]=Read-Only "SELECT * FROM $folder.BPSCATEG WHERE BSGCOD_0=@Category" @{'@Category'='FR'}
   $out.results["${folder}_payment"]=Read-Only "SELECT * FROM $folder.TABPAYTERM WHERE PTE_0=@Payment" @{'@Payment'='CHQ00'}
   $out.results["${folder}_dictionary"]=Read-Only "SELECT CODFIC_0,CODZONE_0,CODTYP_0,LONG_0,DIME_0,NOLIB_0,OBLIG_0,OPTION_0,ZERO_0,LIEN_0,VERIF_0 FROM $folder.ATABZON WHERE CODFIC_0 IN ('BPSUPPLIER','BPARTNER','BPADDRESS','BPSCATEG') AND CODZONE_0 IN ('ENAFLG','BPATYP','BPSNUM','BPSNAM','BSGCOD','CUR','PTE','VACBPR','ACCCOD','XICE','XIF','XRC','REFCOU','CREMOD','BPRNUM','BPRNAM','BPAADD') ORDER BY CODFIC_0,NUMLIG_0"
   $out.results["${folder}_counter"]=Read-Only "SELECT * FROM $folder.ACODNUM WHERE CODNUM_0 IN (SELECT REFCOU_0 FROM $folder.BPSCATEG WHERE BSGCOD_0=@Category)" @{'@Category'='FR'}
   $out.results["${folder}_numeric_F"]=Read-Only "SELECT TOP (12) BPSNUM_0,BPSNAM_0,BSGCOD_0,CREDATTIM_0,TRY_CONVERT(bigint,SUBSTRING(RTRIM(BPSNUM_0),2,14)) AS numeric_suffix FROM $folder.BPSUPPLIER WHERE BPSNUM_0 LIKE 'F%' AND TRY_CONVERT(bigint,SUBSTRING(RTRIM(BPSNUM_0),2,14)) IS NOT NULL ORDER BY numeric_suffix DESC,BPSNUM_0"
   $out.results["${folder}_fiscal_duplicates"]=Read-Only "SELECT p.BPRNUM_0,p.BPRNAM_0,p.XICE_0,p.XIF_0,p.XRC_0,s.BPSNUM_0,s.BPSNAM_0 FROM $folder.BPARTNER p LEFT JOIN $folder.BPSUPPLIER s ON s.BPSNUM_0=p.BPRNUM_0 WHERE p.XICE_0=@ICE OR p.XIF_0=@IF OR p.XRC_0=@RC OR p.BPRNAM_0 LIKE @Name OR p.BPRNUM_0=@Code" @{'@Code'='F10022';'@ICE'='001850814000094';'@IF'='20734927';'@RC'='10909';'@Name'='%PALMERAIE%'}
   $out.results["${folder}_menus"]=Read-Only "SELECT TOP (30) LANCHP_0,LANMES_0,LANNUM_0,LAN_0 FROM $folder.APLSTD WHERE LANCHP_0 IN (1,363) AND LAN_0 IN ('FRA','ENG') ORDER BY LANCHP_0,LANNUM_0,LAN_0"
  }
  $out.results.counter_tables=Read-Only "SELECT s.name AS folder,t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name IN ('OB','TEST') AND (t.name LIKE '%CODNUM%' OR t.name LIKE '%COUNTER%' OR t.name LIKE '%NUMERO%') ORDER BY s.name,t.name"
  $out.results.sql_sequences=Read-Only "SELECT s.name AS folder,q.name,q.current_value,q.increment,q.minimum_value,q.maximum_value,q.is_cycling FROM sys.sequences q JOIN sys.schemas s ON s.schema_id=q.schema_id WHERE s.name IN ('OB','TEST') ORDER BY s.name,q.name"
 }
 if($Phase -eq 'rules'){
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_rule_menus"]=Read-Only "SELECT LANCHP_0,LANNUM_0,LANMES_0 FROM $folder.APLSTD WHERE LANCHP_0 IN (223,943) AND LAN_0='FRA' ORDER BY LANCHP_0,LANNUM_0"
   $out.results["${folder}_mandatory_dictionary"]=Read-Only "SELECT z.CODFIC_0,z.CODZONE_0,z.NOLIB_0,z.OBLIG_0,a.LANNUM_0,a.LANMES_0 FROM $folder.ATABZON z LEFT JOIN $folder.APLSTD a ON a.LANCHP_0=z.NOLIB_0 AND a.LAN_0='FRA' WHERE z.CODFIC_0='ATABZON' AND z.CODZONE_0='OBLIG' ORDER BY a.LANNUM_0"
   $out.results["${folder}_counter_candidates"]=Read-Only "SELECT CODNUM_0,LNG_0,NIVDEF_0,NIVRAZ_0,TYP_0,POSTYP_0,POSTYP_1,POSLNG_0,POSLNG_1,POSCTE_0,POSCTE_1,SEQ_0,SEQTBL_0,SEQABR_0,SEQNBR_0 FROM $folder.ACODNUM WHERE CODNUM_0 LIKE '%BPS%' OR CODNUM_0 LIKE '%BPR%' OR CODNUM_0 LIKE '%SUP%' OR POSCTE_0='F' OR POSCTE_1='F' ORDER BY CODNUM_0"
   $out.results["${folder}_counter_parameters"]=Read-Only "SELECT CHAPITRE_0,PARAM_0,NAM_0,NIVDEF_0,VALDEF_0,OBJET_0 FROM $folder.ADOPAR WHERE PARAM_0 LIKE '%COU%' OR PARAM_0 IN ('SUPNUM','BPSNUM','BPRNUM','SUPCOU','BPSCOU') ORDER BY CHAPITRE_0,PARAM_0"
   $out.results["${folder}_namespaces"]=Read-Only "SELECT TOP (12) BPRNUM_0,BPRNAM_0,BPSFLG_0,TRY_CONVERT(bigint,SUBSTRING(RTRIM(BPRNUM_0),2,14)) AS numeric_suffix FROM $folder.BPARTNER WHERE BPRNUM_0 LIKE 'F%' AND TRY_CONVERT(bigint,SUBSTRING(RTRIM(BPRNUM_0),2,14)) IS NOT NULL ORDER BY numeric_suffix DESC,BPRNUM_0"
   $out.results["${folder}_labels"]=Read-Only "SELECT CODFIC_0,ZONE_0,IDENT1_0,IDENT2_0,TEXTE_0 FROM $folder.ATEXTRA WHERE LANGUE_0='FRA' AND ((CODFIC_0='BPSCATEG' AND IDENT1_0='FR') OR (CODFIC_0='TABPAYTERM' AND IDENT1_0='CHQ00'))"
   $out.results["${folder}_TEST_anomaly"]=Read-Only "SELECT p.BPRNUM_0,p.BPRNAM_0,p.BPSFLG_0,p.ENAFLG_0,p.XICE_0,p.XIF_0,p.XRC_0 FROM $folder.BPARTNER p WHERE BPRNUM_0='DROGUERIEPALME'"
  }
 }
 if($Phase -eq 'numbering'){
  $out.results.assignment_columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('OB','TEST') AND (t.name IN (SELECT t2.name FROM sys.tables t2 JOIN sys.columns c2 ON c2.object_id=t2.object_id WHERE c2.name='MANCOU_0') OR t.name LIKE '%NUM%' AND c.name IN ('CODNUM_0','VALEUR_0','CHRONO_0','NUMERO_0','COMPTEUR_0','SEQ_0')) ORDER BY s.name,t.name,c.column_id"
 }
 if($Phase -eq 'numbering2'){
  $out.results.tables=Read-Only "SELECT s.name AS folder,t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name IN ('OB','TEST') AND (t.name LIKE '%COU%' OR t.name LIKE '%NUM%') ORDER BY s.name,t.name"
  $out.results.columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('OB','TEST') AND t.name IN ('TABCOUAFF','TABCOU','ACOMCOU','NUMERO','AOBJET') ORDER BY s.name,t.name,c.column_id"
 }
 if($Phase -eq 'numbering3'){
  foreach($folder in 'OB','TEST'){$out.results["${folder}_assignments"]=Read-Only "SELECT * FROM $folder.TABCOUAFF"}
  $out.results.columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('OB','TEST') AND t.name='AVALNUM' ORDER BY s.name,c.column_id"
 }
 if($Phase -eq 'counter_values'){
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_values"]=Read-Only "SELECT CODNUM_0,SITE_0,PERIODE_0,COMP_0,VALEUR_0 FROM $folder.AVALNUM WHERE CODNUM_0 IN ('BPS','XBPS') ORDER BY CODNUM_0,SITE_0,PERIODE_0,COMP_0"
  }
 }
 if($Phase -eq 'profile_checks'){
  $out.results.columns=Read-Only "SELECT s.name AS folder,t.name AS table_name,c.name AS column_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name IN ('OB','TEST') AND t.name IN ('TABCUR','TABCOUNTRY','TABVACBPR','GACCCODE') ORDER BY s.name,t.name,c.column_id"
  foreach($folder in 'OB','TEST'){
   $out.results["${folder}_accounting"]=Read-Only "SELECT TOP (20) TYP_0,ACCCOD_0,COA_0,DES_0 FROM $folder.GACCCODE WHERE ACCCOD_0='STD' ORDER BY TYP_0,COA_0"
   $out.results["${folder}_dictionary_links"]=Read-Only "SELECT CODFIC_0,CODZONE_0,EXPLIEN_0,LIEN_0 FROM $folder.ATABZON WHERE CODFIC_0='BPSCATEG' AND CODZONE_0 IN ('ACCCOD','VACBPR','CUR','CRY','PTE')"
  }
 }
 if($Phase -eq 'final_checks'){
  $out.results.creation_time=Read-Only "SELECT BPSNUM_0,CREUSR_0,CONVERT(varchar(33),CREDATTIM_0,126) AS creation_time_sql FROM OB.BPSUPPLIER WHERE BPSNUM_0='F10022'"
  foreach($folder in 'OB','TEST'){$out.results["${folder}_customer"]=Read-Only "SELECT BPCNUM_0 FROM $folder.BPCUSTOMER WHERE BPCNUM_0='C06952'"}
 }
 $path=Join-Path $directory ($Phase+'.json');$out|ConvertTo-Json -Depth 14|Set-Content -LiteralPath $path -Encoding UTF8
 [Console]::WriteLine((@{evidence=$path;phase=$Phase;queries=$out.results.Count;writes=0}|ConvertTo-Json -Compress))
}finally{$cn.Dispose();$secret.Dispose()}
