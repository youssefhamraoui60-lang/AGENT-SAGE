# Read-only tool dispatcher. SQL text and TEST identifiers are fixed, never model-generated.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$cn=$null;$secret=$null;$results=@()
try {
 $batch=[Console]::In.ReadToEnd() | ConvertFrom-Json
 if(@($batch.calls).Count -gt 80){throw 'Batch too large'}
 $root=Split-Path $PSScriptRoot -Parent
 $cred=Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
 $secret=$cred.Password.Copy();$secret.MakeReadOnly()
 $cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=AGENT-chat-SELECT-only;ApplicationIntent=ReadOnly')
 $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret);$cn.Open()
 foreach($call in $batch.calls){
  $cmd=$cn.CreateCommand();$cmd.CommandTimeout=3
  foreach($name in 'Code','Category','Pattern','NearPattern','Unit','Unit2','Site','Supplier','Label','Rate','Company','Level'){
   $value=[string]$call.args.$name
   if($value.Length -gt 128){throw 'Oversized parameter'}
   $p=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::NVarChar,128);$p.Value=$value
  }
  $rd=$null
  try {
   $cmd.CommandText=switch($call.tool){
    'search_articles' {'SELECT TOP (5) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0,ACCCOD_0,VACITM_0 FROM TEST.ITMMASTER WHERE ITMDES1_0 LIKE @Pattern ESCAPE ''~'' AND (@Category='''' OR TCLCOD_0=@Category) ORDER BY ITMREF_0'}
    'get_recent_articles' {'SELECT TOP (5) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,ACCCOD_0,VACITM_0,CREDATTIM_0 FROM TEST.ITMMASTER WHERE (@Category='''' OR TCLCOD_0=@Category) ORDER BY CREDATTIM_0 DESC,ROWID DESC'}
    'check_article_duplicate' {'SELECT TOP (1) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code'}
    'get_article_categories' {'SELECT TOP (21) TCLCOD_0,TCLDES_0,STOFCY_0,STU_0,PUU_0,SAU_0,PUUSTUCOE_0,SAUSTUCOE_0,ACCCOD_0,VACITM_0,STOMGTCOD_0,LOTMGTCOD_0,ITMREFCOU_0 FROM TEST.ITMCATEG WHERE (@Category='''' OR TCLCOD_0=@Category) AND (@Label='''' OR TCLDES_0 COLLATE Latin1_General_CI_AI LIKE @Pattern ESCAPE ''~'' OR TCLDES_0 COLLATE Latin1_General_CI_AI LIKE @NearPattern ESCAPE ''~'') AND (@Site='''' OR STOFCY_0=@Site OR LTRIM(RTRIM(STOFCY_0))='''') ORDER BY CASE WHEN STOFCY_0=@Site AND @Site<>'''' THEN 0 ELSE 1 END,TCLCOD_0,STOFCY_0'}
    'get_units' {'SELECT TOP (3) UOM_0,UOMDEC_0,UOMSYM_0 FROM TEST.TABUNIT WHERE UOM_0 IN (@Unit,@Unit2) ORDER BY UOM_0'}
    'get_unit_conversions' {'SELECT TOP (3) UOM1_0,UOM2_0,COEUOM_0,REV_0 FROM TEST.TABCOEFF WHERE (UOM1_0=@Unit AND UOM2_0=@Unit2) OR (UOM1_0=@Unit2 AND UOM2_0=@Unit) ORDER BY UOM1_0'}
    'get_sites' {'SELECT TOP (51) f.FCY_0,f.FCYNAM_0,f.LEGCPY_0,c.CPYNAM_0,f.CRY_0,f.WRHFLG_0,f.PURFLG_0,f.SALFLG_0 FROM TEST.FACILITY f LEFT JOIN TEST.COMPANY c ON c.CPY_0=f.LEGCPY_0 WHERE @Site='''' OR f.FCY_0=@Site ORDER BY f.FCY_0'}
    'search_suppliers' {'SELECT TOP (5) s.BPSNUM_0,p.BPRNAM_0,p.BPRNAM_1 FROM TEST.BPSUPPLIER s LEFT JOIN TEST.BPARTNER p ON p.BPRNUM_0=s.BPSNUM_0 WHERE (@Supplier<>'''' AND s.BPSNUM_0=@Supplier) OR (@Supplier='''' AND @Label<>'''' AND (p.BPRNAM_0 LIKE @Pattern ESCAPE ''~'' OR p.BPRNAM_1 LIKE @Pattern ESCAPE ''~'' OR p.BPRNAM_0 LIKE @NearPattern ESCAPE ''~'')) ORDER BY CASE WHEN p.BPRNAM_0=@Label THEN 0 WHEN p.BPRNAM_0 LIKE @Pattern ESCAPE ''~'' THEN 1 ELSE 2 END,s.BPSNUM_0'}
    'get_supplier_article_references' {'SELECT TOP (5) ITMREF_0,BPSNUM_0,ITMREFBPS_0,PUU_0,PUUSTUCOE_0 FROM TEST.ITMBPS WHERE BPSNUM_0=@Supplier AND (@Code='''' OR ITMREF_0=@Code) ORDER BY ITMREF_0'}
    'get_accounting_categories' {'SELECT TOP (5) TYP_0,ACCCOD_0,COA_0,DES_0 FROM TEST.GACCCODE WHERE TYP_0=1 AND ((@Code<>'''' AND ACCCOD_0=@Code) OR (@Code='''' AND @Label<>'''' AND DES_0 LIKE @Pattern ESCAPE ''~'')) ORDER BY ACCCOD_0,COA_0'}
    'get_tax_rules' {'SELECT TOP (10) r.VAT_0,r.CPY_0,r.LEG_0,r.STRDAT_0,r.VATRAT_0,v.VATDES_0 FROM TEST.TABRATVAT r JOIN TEST.TABVAT v ON v.VAT_0=r.VAT_0 AND v.LEG_0=r.LEG_0 WHERE (@Code='''' OR r.VAT_0=@Code) AND (@Rate='''' OR r.VATRAT_0=TRY_CONVERT(decimal(9,3),@Rate)) AND r.STRDAT_0<=CAST(GETDATE() AS date) AND (@Company='''' OR r.CPY_0 IN (@Company,'''')) ORDER BY r.STRDAT_0 DESC,r.VAT_0'}
    'get_tax_determination' {'SELECT TOP (5) COD_0,LEG_0,ENAFLG_0,VACITM_0,VACBPR_0,VAT_0,VACDES_0 FROM TEST.TABVAC WHERE VACITM_0=@Level ORDER BY COD_0'}
    'get_article_site' {'SELECT TOP (1) ITMREF_0,STOFCY_0 FROM TEST.ITMFACILIT WHERE ITMREF_0=@Code AND STOFCY_0=@Site'}
    default {throw 'Unknown SELECT tool'}
   }
   $rd=$cmd.ExecuteReader();$rows=[System.Collections.Generic.List[object]]::new()
   while($rd.Read()){$row=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows.Add([pscustomobject]$row)}
   $results+=@{id=$call.id;tool=$call.tool;ok=$true;rows=$rows.ToArray();source='SQL TEST';checked_at=[DateTime]::UtcNow.ToString('o')}
  } catch {$results+=@{id=$call.id;tool=$call.tool;ok=$false;rows=@();code='tool_query_unavailable'}}
  finally {if($rd){$rd.Dispose()};$cmd.Dispose()}
 }
 @{ok=$true;results=@($results);writes=0;folder='TEST'} | ConvertTo-Json -Depth 8 -Compress
} catch {@{ok=$false;code='sql_unavailable';results=@();writes=0} | ConvertTo-Json -Compress}
finally {if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
