# Dedicated fixed-query article transport, existing TEST SQL connection only.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null;$stage='request'
try {
 $request=[Console]::In.ReadToEnd()|ConvertFrom-Json
 if($request.folder -cnotin @('TEST','OB') -or $request.folder -cne (Get-SupplierTarget)){throw 'Folder mismatch'}
 if($request.action -ceq 'plan' -and $request.plan.folder -cne $request.folder){throw 'Plan folder mismatch'}
 if($request.action -cnotin @('catalog','plan')){throw 'Unsupported article operation'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$stage='command';$cmd=$cn.CreateCommand();$cmd.CommandTimeout=45
 if($request.action -ceq 'catalog'){
  $cmd.CommandText=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'article_catalog.sql') -Raw -Encoding UTF8
  foreach($key in 'Category','Code'){$p=$cmd.Parameters.Add('@'+$key,[Data.SqlDbType]::NVarChar,128);$p.Value=[string]$request.$key}
  $p=$cmd.Parameters.Add('@Stock',[Data.SqlDbType]::Int);$p.Value=[int]$request.Stock
 }else{
  if($request.execute -isnot [bool]){throw 'Explicit mode required'}
  $cmd.CommandText=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'article_transaction.sql') -Raw -Encoding UTF8
  $p=$cmd.Parameters.Add('@Plan',[Data.SqlDbType]::NVarChar,-1);$p.Value=ConvertTo-Json -InputObject $request.plan -Depth 25 -Compress
  $p=$cmd.Parameters.Add('@Execute',[Data.SqlDbType]::Bit);$p.Value=$request.execute
 }
 if($request.folder -ceq 'OB'){$cmd.CommandText=$cmd.CommandText.Replace('TEST.','OB.').Replace("'TEST'","'OB'").Replace("'TEST_APPLICATION_","'OB_APPLICATION_")}
 $stage='sql';$json=[string]$cmd.ExecuteScalar()
 if(-not $json){throw 'Missing SQL result'}
 $stage='decode';$result=$json|ConvertFrom-Json
}catch{
 $number=$null;$e=$_.Exception
 while($e){if($e -is [System.Data.SqlClient.SqlException]){$number=$e.Number;break};$e=$e.InnerException}
 $result=@{ok=$false;folder=(Get-SupplierTarget);sql_error_number=$number;code='article_sql_unavailable';stage=$stage;error_type=$_.Exception.GetType().Name;error_id=$_.FullyQualifiedErrorId;executed=$false;retry_allowed=$false}
}finally{if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
[Console]::WriteLine(($result|ConvertTo-Json -Depth 30 -Compress))
