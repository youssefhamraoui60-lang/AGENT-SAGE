$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null;$rd=$null
try{
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=15
 $cmd.CommandText=Get-SupplierSqlText 'supplier_reference_labels.sql'
 $rd=$cmd.ExecuteReader();$rows=@()
 while($rd.Read()){$rows+=@{kind=$rd.GetString(0).Trim();code=$rd.GetString(1).Trim();label=$rd.GetString(2).Trim()}}
 $answer=@{ok=$true;rows=$rows;source=((Get-SupplierTarget)+'.ATEXTRA');writes=0}
}catch{$answer=@{ok=$false;code='reference_labels_unavailable'}}
finally{if($rd){$rd.Dispose()};if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
$answer | ConvertTo-Json -Depth 5 -Compress
