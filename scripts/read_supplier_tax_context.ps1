# Fixed, limited SELECTs only; no arbitrary SQL or Sage business writes.
$ErrorActionPreference='Stop'
$cn=$null;$secret=$null
try{
 $root=Split-Path $PSScriptRoot -Parent
 $credential=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
 $secret=$credential.Password.Copy();$secret.MakeReadOnly()
 $cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=AGENT-supplier-tax-readonly;ApplicationIntent=ReadOnly')
 $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($credential.UserName,$secret);$cn.Open()
 function Read-Fixed([string]$Query){
  $cmd=$cn.CreateCommand();$cmd.CommandTimeout=5;$cmd.CommandText=$Query
  [void]$cmd.Parameters.Add('@Code',[System.Data.SqlDbType]::NVarChar,15);$cmd.Parameters['@Code'].Value='F890'
  $reader=$cmd.ExecuteReader();$rows=@()
  try{while($reader.Read()){$row=[ordered]@{};for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}};$rows+=[pscustomobject]$row}}
  finally{$reader.Dispose();$cmd.Dispose()};return ,$rows
 }
 $columns=Read-Fixed "SELECT TABLE_NAME,COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='TEST' AND TABLE_NAME IN ('BPSUPPLIER','BPARTNER') AND COLUMN_NAME IN ('BPSNUM_0','BPRNUM_0','VACBPR_0','CRY_0','CUR_0')"
 $result=[ordered]@{ok=$true;folder='TEST';supplier='F890';source='SQL_READ_ONLY_EXISTING_CONNECTION_MODE';tables=@{}}
 foreach($table in @('BPSUPPLIER','BPARTNER')){
  $key=if($table -eq 'BPSUPPLIER'){'BPSNUM_0'}else{'BPRNUM_0'}
  $available=@($columns | Where-Object TABLE_NAME -eq $table | Select-Object -ExpandProperty COLUMN_NAME)
  $selected=@($key)+@(@('VACBPR_0','CRY_0','CUR_0') | Where-Object {$_ -in $available})
  if($key -in $available){$result.tables[$table]=Read-Fixed ('SELECT TOP (1) '+($selected -join ',')+' FROM TEST.'+$table+' WHERE '+$key+'=@Code')}
 }
 $result | ConvertTo-Json -Depth 6 -Compress
}catch{ @{ok=$false;code='supplier_tax_context_unavailable'} | ConvertTo-Json -Compress }
finally{if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
