$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null;$reader=$null
try {
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=15
 $cmd.CommandText=Get-SupplierSqlText 'model_defaults.sql'
 $reader=$cmd.ExecuteReader();$rows=@()
 while($reader.Read()){
  $row=[ordered]@{}
  for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}}
  $rows+=,$row
 }
 $answer=@{ok=($rows.Count -eq 1);rows=$rows;source='OB.F103';writes=0}
}catch{$answer=@{ok=$false;code='supplier_model_defaults_unavailable'}}
finally{if($reader){$reader.Dispose()};if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
$answer | ConvertTo-Json -Depth 5 -Compress
