# Fixed parameterized SELECTs only. No user-supplied SQL or identifiers.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$cn=$null;$secret=$null
try {
 $inputData=[Console]::In.ReadToEnd() | ConvertFrom-Json
 $root=Split-Path $PSScriptRoot -Parent
 $credential=Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
 $secret=$credential.Password.Copy();$secret.MakeReadOnly()
 $cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=AGENT-article-readonly;ApplicationIntent=ReadOnly')
 $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($credential.UserName,$secret)
 $cn.Open()
 function Select-Fixed([string]$sql,[hashtable]$values) {
  $cmd=$cn.CreateCommand();$cmd.CommandTimeout=4;$cmd.CommandText=$sql
  foreach($key in $values.Keys){$p=$cmd.Parameters.Add($key,[System.Data.SqlDbType]::NVarChar,128);$p.Value=[string]$values[$key]}
  $rd=$null
  try {
   $rd=$cmd.ExecuteReader();$rows=[System.Collections.Generic.List[object]]::new()
   while($rd.Read()){$row=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows.Add([pscustomobject]$row)}
   return ,$rows.ToArray()
  } finally {if($rd){$rd.Dispose()};$cmd.Dispose()}
 }
 $out=[ordered]@{ok=$true;folder='TEST';source='SQL Server';connection_mode='TMS_OPTIONAL_ENCRYPTION';checked_at=[DateTime]::UtcNow.ToString('o')}
 $out.article=Select-Fixed 'SELECT TOP (1) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0,STOMGTCOD_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code' @{'@Code'=$inputData.code_article}
 $out.supplier_link=Select-Fixed 'SELECT TOP (1) ITMREF_0,BPSNUM_0 FROM TEST.ITMBPS WHERE ITMREF_0=@Code AND BPSNUM_0=@Supplier' @{'@Code'=$inputData.code_article;'@Supplier'=$inputData.code_fournisseur}
 $out.designation_matches=Select-Fixed 'SELECT TOP (5) ITMREF_0,ITMDES1_0 FROM TEST.ITMMASTER WHERE ITMDES1_0=@Label ORDER BY ITMREF_0' @{'@Label'=$inputData.designation}
 $out.category=Select-Fixed 'SELECT TOP (5) TCLCOD_0,STOFCY_0,STU_0,PUU_0,SAU_0,STOMGTCOD_0,LOTMGTCOD_0,ACCCOD_0 FROM TEST.ITMCATEG WHERE TCLCOD_0=@Category ORDER BY STOFCY_0' @{'@Category'=$inputData.categorie}
 $out.unit=Select-Fixed 'SELECT TOP (1) UOM_0 FROM TEST.TABUNIT WHERE UOM_0=@Unit' @{'@Unit'=$inputData.unite}
 $out.site=Select-Fixed 'SELECT TOP (1) FCY_0,LEGCPY_0 FROM TEST.FACILITY WHERE FCY_0=@Site' @{'@Site'=$inputData.site}
 $out.supplier=Select-Fixed 'SELECT TOP (1) BPSNUM_0 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=@Supplier' @{'@Supplier'=$inputData.code_fournisseur}
 $out.reference=Select-Fixed 'SELECT TOP (1) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code' @{'@Code'=$inputData.reference_article}
 $out | ConvertTo-Json -Depth 6 -Compress
} catch {
 # No raw exception, credentials, or connection string crosses the API boundary.
 @{ok=$false;code='sql_reader_unavailable'} | ConvertTo-Json -Compress
} finally {if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
