# Private persistent SELECT worker: one bounded .NET pool per managed process.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'chat_sql_queries.ps1')
$root=Split-Path $PSScriptRoot -Parent
$cred=Import-Clixml (Join-Path $root 'runtime/sql-reader-credential.clixml')
$secret=$cred.Password.Copy();$secret.MakeReadOnly()
$sqlCredential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
$connectionString='Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=True;Min Pool Size=0;Max Pool Size=1;Connection Lifetime=300;Application Name=AGENT-chat-pooled-SELECT;ApplicationIntent=ReadOnly'
try {
 while($null -ne ($line=[Console]::In.ReadLine())) {
  $cn=$null
  try {
   $batch=$line|ConvertFrom-Json
   if(@($batch.calls).Count -gt 60){throw 'Batch too large'}
   $cn=[System.Data.SqlClient.SqlConnection]::new($connectionString);$cn.Credential=$sqlCredential
   $open=[Diagnostics.Stopwatch]::StartNew();$cn.Open();$open.Stop();$results=@()
   foreach($call in $batch.calls) {
    $cmd=$cn.CreateCommand();$cmd.CommandTimeout=3;$rd=$null;$watch=[Diagnostics.Stopwatch]::StartNew()
    try {
     foreach($name in 'Status','Offset','PageSize','Code','Category','Pattern','NearPattern','Unit','Unit2','Site','Supplier','Label','Rate','Company','Level','Folder','Ice','Fiscal','Rc') {
      $value=[string]$call.args.$name;if($value.Length -gt 128){throw 'Oversized parameter'}
      $p=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::NVarChar,128);$p.Value=$value
     }
     $cmd.CommandText=Get-ChatSelectQuery $call.tool
     if($call.args.Folder -ceq 'OB' -and $call.tool -cnotin @('get_supplier_record','check_supplier_fiscal_duplicates','get_supplier_preparation_profile')){$cmd.CommandText=$cmd.CommandText.Replace('TEST.','OB.').Replace("'TEST'","'OB'")}
     $rd=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
     while($rd.Read()){$row=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows.Add([pscustomobject]$row)}
     $watch.Stop()
     $results+=@{id=$call.id;tool=$call.tool;ok=$true;rows=$rows.ToArray();source=$(if($call.args.Folder -eq 'OB'){'SQL OB'}else{'SQL TEST'});folder=$(if($call.args.Folder -eq 'OB'){'OB'}else{'TEST'});checked_at=[DateTime]::UtcNow.ToString('o');query_ms=$watch.Elapsed.TotalMilliseconds;connection_id=$cn.ClientConnectionId.ToString()}
    } catch {$results+=@{id=$call.id;tool=$call.tool;ok=$false;rows=@();code='tool_query_unavailable'}}
    finally {if($rd){$rd.Dispose()};$cmd.Dispose()}
   }
   $answer=@{ok=$true;results=@($results);writes=0;folder='TEST';connection_open_ms=$open.Elapsed.TotalMilliseconds}
  } catch {$answer=@{ok=$false;code='sql_unavailable';results=@();writes=0}}
  finally {if($cn){$cn.Dispose()}}
  [Console]::WriteLine(($answer|ConvertTo-Json -Depth 9 -Compress))
  [Console]::Out.Flush()
 }
} finally {$secret.Dispose();[System.Data.SqlClient.SqlConnection]::ClearAllPools()}
