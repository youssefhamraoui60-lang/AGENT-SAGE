# Authorized historical TEST import. Source OB is SELECT-only. No existing row updated.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$cn=$null;$secret=$null
try {
 $r=[Console]::In.ReadToEnd()|ConvertFrom-Json
 if($r.mode -notin @('preview','create')){throw 'Invalid mode'}
 if($r.mode -eq 'create' -and $r.human_validated -ne $true){throw 'Human validation required'}
 if(@($r.clients).Count -lt 1 -or @($r.clients).Count -gt 100){throw 'Client limit'}
 foreach($code in $r.clients){if($code -notmatch '^C[0-9]{4,8}$'){throw 'Invalid client code'}}
 $cred=Import-Clixml (Join-Path $PSScriptRoot '../runtime/sql-reader-credential.clixml')
 $secret=$cred.Password.Copy();$secret.MakeReadOnly()
 $cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;Connect Timeout=5;Application Name=SOB-authorized-TEST-client-copy')
 $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret);$cn.Open()
 $cmd=$cn.CreateCommand();$cmd.CommandTimeout=45
 $cmd.CommandText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'copy-test-customers.sql'))
 $null=$cmd.Parameters.Add('@ClientsJSON',[System.Data.SqlDbType]::NVarChar,-1)
 $cmd.Parameters['@ClientsJSON'].Value=ConvertTo-Json -InputObject @($r.clients) -Compress
 $null=$cmd.Parameters.Add('@CommitCopy',[System.Data.SqlDbType]::Bit);$cmd.Parameters['@CommitCopy'].Value=($r.mode -eq 'create')
 $rd=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
 while($rd.Read()){$row=[ordered]@{};for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}};$rows.Add([pscustomobject]$row)}
 $rd.Close();@{ok=$true;rows=$rows.ToArray();committed=($r.mode -eq 'create')}|ConvertTo-Json -Depth 6 -Compress
}catch{
 $n=0;$e=$_.Exception;while($e){if($e -is [System.Data.SqlClient.SqlException]){$n=$e.Number;break};$e=$e.InnerException}
 @{ok=$false;code=$n;error=$_.Exception.Message;committed=$false}|ConvertTo-Json -Compress
}finally{if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
