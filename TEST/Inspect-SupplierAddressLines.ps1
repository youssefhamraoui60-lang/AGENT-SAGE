$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null
try {
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=15
 $cmd.CommandText="SELECT name,TYPE_NAME(system_type_id) AS data_type,CASE WHEN system_type_id IN(231,239) THEN max_length/2 ELSE max_length END AS max_characters FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.BPADDRESS') AND (name LIKE 'BPAADDLIG[_]%' OR name='CTY_0') ORDER BY name"
 $reader=$cmd.ExecuteReader();$rows=@()
 while($reader.Read()){$row=[ordered]@{};for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=$reader.GetValue($i)};$rows+=,$row}
 $reader.Dispose();$cmd.Dispose();@{ok=$true;rows=$rows;writes=0}|ConvertTo-Json -Depth 4 -Compress
} catch {@{ok=$false;code='address_metadata_unavailable';writes=0}|ConvertTo-Json -Compress}
finally {if($cn){$cn.Dispose()}}
