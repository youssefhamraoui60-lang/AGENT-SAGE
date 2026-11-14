$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=New-TestSupplierSqlConnection -ConnectionString 'Data Source=tcp:sage,1433;Initial Catalog=x3v12' -CredentialFile (Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime/sql-reader-credential.clixml')
try {
 $cn.Open();$cmd=$cn.CreateCommand()
 $cmd.CommandText="SELECT t.name AS table_name,c.name AS column_name,HAS_PERMS_BY_NAME('TEST.'+t.name,'OBJECT','SELECT') AS can_select FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name='TEST' AND t.name IN ('STOCK','GACCENTRYD') ORDER BY t.name,c.column_id"
 $rd=$cmd.ExecuteReader();$rows=@()
 while($rd.Read()){$rows+=@{table=$rd.GetString(0);column=$rd.GetString(1);can_select=$rd.GetValue(2)}}
 $rd.Dispose();$cmd.Dispose();$rows | ConvertTo-Json
}finally{$cn.Dispose()}
