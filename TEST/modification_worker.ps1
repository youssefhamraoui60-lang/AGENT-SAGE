# Fixed TEST-only metadata/snapshot/update actions. Never accepts SQL text.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null;$rawResult=$null
try {
 $r=[Console]::In.ReadToEnd()|ConvertFrom-Json
 if($r.folder -cnotin @('TEST','OB') -or $r.folder -cne (Get-SupplierTarget)){throw 'Folder mismatch'}
 if($r.folder -ceq 'OB' -and $r.Resource -and $r.Resource -cnotin @('supplier','article')){throw 'Unsupported OB resource'}
 $file=switch -CaseSensitive ($r.action){'catalog' {'modification_catalog.sql'} 'snapshot' {'modification_snapshot.sql'} 'plan' {'modification_transaction.sql'} default {throw 'Unsupported action'}}
 if($r.execute -isnot [bool]){throw 'Explicit execution mode required'}
 if($r.action -cne 'plan' -and $r.execute){throw 'Read-only action'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=55
 $cmd.CommandText="SELECT CASE WHEN SUSER_SNAME()='sa' OR IS_SRVROLEMEMBER('sysadmin')=1 THEN 0 ELSE 1 END"
 if([int]$cmd.ExecuteScalar() -ne 1){throw 'Dedicated non-admin SQL account required'}
 $cmd.CommandText=Get-Content -LiteralPath (Join-Path $PSScriptRoot $file) -Raw -Encoding UTF8
 if($r.action -in @('snapshot','plan')){$scan=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'modification_dependency_scan.sql') -Raw -Encoding UTF8;$cmd.CommandText=$cmd.CommandText.Replace('-- DEPENDENCY_SCAN_HERE',$scan)}
 if($r.folder -ceq 'OB'){$cmd.CommandText=$cmd.CommandText.Replace('TEST','OB')}
 foreach($key in 'Resource','Code'){$p=$cmd.Parameters.Add('@'+$key,[Data.SqlDbType]::NVarChar,128);$p.Value=[string]$r.$key}
 $p=$cmd.Parameters.Add('@Plan',[Data.SqlDbType]::NVarChar,-1);$planJson=ConvertTo-Json -InputObject $r.plan -Depth 30 -Compress;if(-not $planJson){$planJson='{}'};$p.Value=$planJson
 $p=$cmd.Parameters.Add('@Execute',[Data.SqlDbType]::Bit);$p.Value=$r.execute
 $json=[string]$cmd.ExecuteScalar();if(-not $json){throw 'Missing result'};$rawResult=$json
}catch{
 $number=$null;$e=$_.Exception;while($e){if($e -is [Data.SqlClient.SqlException]){$number=$e.Number;break};$e=$e.InnerException}
 $result=@{ok=$false;folder=(Get-SupplierTarget);code='modification_sql_unavailable';sql_error_number=$number;executed=$false;retry_allowed=$false}
}finally{if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
if($rawResult){[Console]::WriteLine($rawResult)}else{[Console]::WriteLine(($result|ConvertTo-Json -Depth 40 -Compress))}
