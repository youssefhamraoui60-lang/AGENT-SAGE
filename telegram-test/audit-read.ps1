# Evaluation only: hardcoded SELECT statements, OB production remains read-only.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$cn=$null;$secret=$null
try {
 $r=[Console]::In.ReadToEnd()|ConvertFrom-Json
 $cred=Import-Clixml (Join-Path $PSScriptRoot '../runtime/sql-reader-credential.clixml')
 $secret=$cred.Password.Copy();$secret.MakeReadOnly()
 $cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;Connect Timeout=5;ApplicationIntent=ReadOnly;Application Name=SOB-audit-SELECT-only')
 $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret);$cn.Open()
 $cmd=$cn.CreateCommand();$cmd.CommandTimeout=20
 $cmd.CommandText=switch($r.kind){
  'service_update_permissions' { 'SELECT V.TAB,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''UPDATE'') AS CAN_UPDATE,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''INSERT'') AS CAN_INSERT,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''DELETE'') AS CAN_DELETE FROM (VALUES(''SORDER''),(''SORDERP''),(''SORDERQ''),(''SVCRVAT'')) V(TAB)' }
  'permissions' { 'SELECT HAS_PERMS_BY_NAME(''OB.SORDER'',''OBJECT'',''SELECT'') AS orders,HAS_PERMS_BY_NAME(''OB.SORDERP'',''OBJECT'',''SELECT'') AS prices,HAS_PERMS_BY_NAME(''OB.SORDERQ'',''OBJECT'',''SELECT'') AS quantities,HAS_PERMS_BY_NAME(''OB.BPCUSTOMER'',''OBJECT'',''SELECT'') AS customers,HAS_PERMS_BY_NAME(''OB.ITMMASTER'',''OBJECT'',''SELECT'') AS articles' }
  'master_permissions' { 'SELECT V.TAB,HAS_PERMS_BY_NAME(''OB.''+V.TAB,''OBJECT'',''SELECT'') AS OB_SELECT,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''SELECT'') AS TEST_SELECT,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''INSERT'') AS TEST_INSERT,HAS_PERMS_BY_NAME(''TEST.''+V.TAB,''OBJECT'',''UPDATE'') AS TEST_UPDATE FROM (VALUES(''BPCUSTOMER''),(''BPARTNER''),(''BPADDRESS''),(''BPDLVCUST''),(''CONTACT''),(''CONTACTCRM''),(''ITMMASTER''),(''ITMFACILIT''),(''ITMSALES'')) V(TAB)' }
  'master_schema' { 'SELECT S.name AS dossier,T.name AS table_name,C.name AS column_name,Y.name AS data_type,C.max_length,C.precision,C.scale,C.is_nullable,C.is_identity,C.is_computed FROM sys.tables T JOIN sys.schemas S ON S.schema_id=T.schema_id JOIN sys.columns C ON C.object_id=T.object_id JOIN sys.types Y ON Y.user_type_id=C.user_type_id WHERE S.name IN (''OB'',''TEST'') AND T.name IN (''BPCUSTOMER'',''BPARTNER'',''BPADDRESS'',''BPDLVCUST'',''CONTACT'',''CONTACTCRM'',''ITMMASTER'',''ITMFACILIT'',''ITMSALES'') ORDER BY T.name,S.name,C.column_id' }
  'orders' { 'SELECT H.SOHNUM_0,H.ORDDAT_0,H.CREDATTIM_0,H.BPCORD_0,H.BPCNAM_0,H.REP_0,H.REP_1,H.SALFCY_0,H.CUR_0,H.ORDATI_0,H.XCOMM_0,H.CUSORDREF_0,P.SOPLIN_0,P.ITMREF_0,P.ITMDES1_0,P.SAU_0,P.NETPRIATI_0,Q.QTY_0 FROM OB.SORDER H JOIN OB.SORDERP P ON P.SOHNUM_0=H.SOHNUM_0 JOIN OB.SORDERQ Q ON Q.SOHNUM_0=P.SOHNUM_0 AND Q.SOPLIN_0=P.SOPLIN_0 AND Q.SOQSEQ_0=P.SOPSEQ_0 WHERE H.ORDDAT_0>=@Start AND H.ORDDAT_0<@End AND H.CPY_0=''20'' ORDER BY H.ORDDAT_0,H.SOHNUM_0,P.SOPLIN_0' }
  'test_orders_audit' { 'SELECT H.SOHNUM_0,H.ORDDAT_0,H.CREDATTIM_0,H.BPCORD_0,H.BPCNAM_0,H.REP_0,H.REP_1,H.SALFCY_0,H.CUR_0,H.ORDATI_0,H.XCOMM_0,H.CUSORDREF_0,P.SOPLIN_0,P.ITMREF_0,P.ITMDES1_0,P.SAU_0,P.NETPRIATI_0,Q.QTY_0 FROM TEST.SORDER H JOIN TEST.SORDERP P ON P.SOHNUM_0=H.SOHNUM_0 JOIN TEST.SORDERQ Q ON Q.SOHNUM_0=P.SOHNUM_0 AND Q.SOPLIN_0=P.SOPLIN_0 AND Q.SOQSEQ_0=P.SOPSEQ_0 WHERE H.ORDDAT_0>=@Start AND H.ORDDAT_0<@End AND H.CPY_0=''20'' ORDER BY H.ORDDAT_0,H.SOHNUM_0,P.SOPLIN_0' }
  'customers' { 'SELECT BPCNUM_0,BPCNAM_0,CUR_0,REP_0,REP_1,VACBPR_0,IME_0,BPAADD_0 FROM OB.BPCUSTOMER ORDER BY BPCNUM_0' }
  'test_customer_catalog' { 'SELECT BPCNUM_0,BPCNAM_0,CUR_0,REP_0,REP_1,VACBPR_0,IME_0,BPAADD_0 FROM TEST.BPCUSTOMER ORDER BY BPCNUM_0' }
  'test_article_catalog' { 'SELECT I.ITMREF_0,I.ITMDES1_0,I.SAU_0,I.STU_0,I.SAUSTUCOE_0,I.VACITM_0,CASE WHEN F.ITMREF_0 IS NULL THEN 0 ELSE 1 END AS SITE_OK FROM TEST.ITMMASTER I LEFT JOIN TEST.ITMFACILIT F ON F.ITMREF_0=I.ITMREF_0 AND F.STOFCY_0=''201'' ORDER BY I.ITMREF_0' }
  'customer_identities' { 'SELECT C.BPCNUM_0,B.BPRNAM_0,B.BPRSHO_0,B.XICE_0,B.XIF_0,B.XRC_0 FROM OB.BPCUSTOMER C JOIN OB.BPARTNER B ON B.BPRNUM_0=C.BPCNUM_0 ORDER BY C.BPCNUM_0' }
  'articles' { 'SELECT ITMREF_0,ITMDES1_0,SAU_0,STU_0,SAUSTUCOE_0,VACITM_0 FROM OB.ITMMASTER ORDER BY ITMREF_0' }
  'packaging' { 'SELECT DISTINCT I.ITMREF_0,I.STU_0,I.SAU_0,I.SAUSTUCOE_0,I.PCU_0,I.PCU_1,I.PCU_2,I.PCU_3,I.PCU_4,I.PCU_5,I.PCUSTUCOE_0,I.PCUSTUCOE_1,I.PCUSTUCOE_2,I.PCUSTUCOE_3,I.PCUSTUCOE_4,I.PCUSTUCOE_5 FROM OB.ITMMASTER I JOIN OB.SORDERP P ON P.ITMREF_0=I.ITMREF_0 JOIN OB.SORDER H ON H.SOHNUM_0=P.SOHNUM_0 WHERE H.ORDDAT_0>=@Start AND H.ORDDAT_0<@End AND H.CPY_0=''20''' }
  'representatives' { 'SELECT REPNUM_0,REPNAM_0 FROM OB.SALESREP ORDER BY REPNUM_0' }
  'article_sites' { 'SELECT ITMREF_0 FROM OB.ITMFACILIT WHERE STOFCY_0=''201''' }
  'test_customers' { 'SELECT DISTINCT H.BPCORD_0,CASE WHEN C.BPCNUM_0 IS NULL THEN 0 ELSE 1 END AS IN_TEST,C.CUR_0,C.IME_0,C.REP_0 FROM OB.SORDER H LEFT JOIN TEST.BPCUSTOMER C ON C.BPCNUM_0=H.BPCORD_0 WHERE H.ORDDAT_0>=@Start AND H.ORDDAT_0<@End AND H.CPY_0=''20'' ORDER BY H.BPCORD_0' }
  'test_articles' { 'SELECT DISTINCT P.ITMREF_0,CASE WHEN I.ITMREF_0 IS NULL THEN 0 ELSE 1 END AS IN_TEST,I.SAU_0,I.VACITM_0,I.DLVFLG_0,CASE WHEN F.ITMREF_0 IS NULL THEN 0 ELSE 1 END AS SITE_OK FROM OB.SORDER H JOIN OB.SORDERP P ON P.SOHNUM_0=H.SOHNUM_0 LEFT JOIN TEST.ITMMASTER I ON I.ITMREF_0=P.ITMREF_0 LEFT JOIN TEST.ITMFACILIT F ON F.ITMREF_0=P.ITMREF_0 AND F.STOFCY_0=''201'' WHERE H.ORDDAT_0>=@Start AND H.ORDDAT_0<@End AND H.CPY_0=''20'' ORDER BY P.ITMREF_0' }
  'created_test_orders' { 'SELECT H.SOHNUM_0,H.CUSORDREF_0,H.BPCORD_0,H.REP_0,H.CUR_0,H.ORDATI_0,P.SOPLIN_0,P.ITMREF_0,P.NETPRIATI_0,Q.QTY_0,Q.XBPS_0 FROM TEST.SORDER H JOIN OPENJSON(@ReferencesJSON) J ON H.CUSORDREF_0=J.value JOIN TEST.SORDERP P ON P.SOHNUM_0=H.SOHNUM_0 JOIN TEST.SORDERQ Q ON Q.SOHNUM_0=P.SOHNUM_0 AND Q.SOPLIN_0=P.SOPLIN_0 AND Q.SOQSEQ_0=P.SOPSEQ_0 ORDER BY H.SOHNUM_0,P.SOPLIN_0' }
  default { throw 'Unknown read query' }
 }
 foreach($n in @('Start','End')){$null=$cmd.Parameters.Add('@'+$n,[System.Data.SqlDbType]::Date);$cmd.Parameters['@'+$n].Value=if($n -eq 'Start'){if($r.start){[datetime]::ParseExact($r.start,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)}else{[datetime]'2026-11-07'}}else{if($r.end){[datetime]::ParseExact($r.end,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)}else{[datetime]'2026-11-10'}}}
 if($r.kind -eq 'created_test_orders'){
  if(@($r.references).Count -gt 1000){throw 'Reference limit'}
  foreach($reference in $r.references){if($reference -notmatch '^SOB-[a-f0-9]{16}$'){throw 'Invalid reference'}}
  $null=$cmd.Parameters.Add('@ReferencesJSON',[System.Data.SqlDbType]::NVarChar,-1)
  $cmd.Parameters['@ReferencesJSON'].Value=ConvertTo-Json -InputObject @($r.references) -Compress
 }
 $rd=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
 while($rd.Read()){$row=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows.Add([pscustomobject]$row)}
 @{ok=$true;rows=$rows.ToArray();writes=0}|ConvertTo-Json -Depth 6 -Compress
}catch{@{ok=$false;error=$_.Exception.GetType().Name;writes=0}|ConvertTo-Json -Compress}
finally{if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
