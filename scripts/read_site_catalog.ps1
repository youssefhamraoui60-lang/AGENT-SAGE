# Fixed SELECTs; credentials remain DPAPI-local, no ERP writes.
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$cn=$null;$secret=$null
try {
 $cred=Import-Clixml (Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\sql-reader-credential.clixml')
 $secret=$cred.Password.Copy();$secret.MakeReadOnly()
 $cn=[Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;ApplicationIntent=ReadOnly')
 $cn.Credential=[Data.SqlClient.SqlCredential]::new($cred.UserName,$secret);$cn.Open()
 $cmd=$cn.CreateCommand();$cmd.CommandTimeout=5
 $cmd.CommandText='SELECT TOP (51) f.FCY_0,f.FCYNAM_0,f.LEGCPY_0,c.CPYNAM_0,f.WRHFLG_0 FROM TEST.FACILITY f LEFT JOIN TEST.COMPANY c ON c.CPY_0=f.LEGCPY_0 ORDER BY f.LEGCPY_0,f.FCY_0'
 $rd=$cmd.ExecuteReader();$rows=@()
 while($rd.Read()){$rows += @{site=$rd.GetValue(0).ToString().Trim();name=$rd.GetValue(1).ToString().Trim();company=$rd.GetValue(2).ToString().Trim();company_name=$rd.GetValue(3).ToString().Trim();stock_site=$rd.GetValue(4)}}
 $rd.Dispose();@{ok=$true;folder='TEST';sites=$rows}|ConvertTo-Json -Depth 5 -Compress
}catch{@{ok=$false;code='SITE_CATALOG_UNAVAILABLE'}|ConvertTo-Json -Compress;exit 1}
finally{if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}}
