$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$cred = Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
$secret = $cred.Password.Copy(); $secret.MakeReadOnly()
$cn = [System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=6;Pooling=False;Application Name=AGENT-isolated-test-diagnostic')
$cn.Credential = [System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
$report = [ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');sql_writes=0;connection_mode='USER_AUTHORIZED_TMS_OPTIONAL_ENCRYPTION';queries=@();results=@{}}
function Read-Query([string]$sql,[hashtable]$parameters) {
    $report.queries += $sql
    $cmd=$cn.CreateCommand();$cmd.CommandTimeout=5;$cmd.CommandText=$sql
    foreach ($key in $parameters.Keys) {
        $p=$cmd.Parameters.Add($key,[System.Data.SqlDbType]::NVarChar,128);$p.Value=$parameters[$key]
    }
    $reader=$null
    try {
        $reader=$cmd.ExecuteReader();$rows=[System.Collections.Generic.List[object]]::new()
        while($reader.Read()) {
            $row=[ordered]@{}
            for($i=0;$i -lt $reader.FieldCount;$i++) {$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}}
            $rows.Add([pscustomobject]$row)
        }
        return ,$rows.ToArray()
    } finally {if($reader){$reader.Dispose()};$cmd.Dispose()}
}
try {
 $cn.Open();$report.connected=$true
 $report.results.dictionary_columns=Read-Query "SELECT TOP (400) t.name AS table_name,c.name AS column_name,ty.name AS data_type FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id WHERE s.name=@Folder AND t.name IN ('AOBJET','AOBJETD','AMSKZON','ATABLE','ATABZON','AOBJEXT','AOBJEXTD') ORDER BY t.name,c.column_id" @{'@Folder'='TEST'}
 $report.results.objects=Read-Query 'SELECT TOP (4) ABREV_0,NOMFIC_0,MODELE_0,TRTSPE_0,TRTSPV_0,IMPORT_0 FROM TEST.AOBJET WHERE ABREV_0 IN (@Itm,@Itf,@Bps,@Bpc) ORDER BY ABREV_0' @{'@Itm'='ITM';'@Itf'='ITF';'@Bps'='BPS';'@Bpc'='BPC'}
 $report.status='READ_ONLY_COMPLETED'
} catch {$report.status='BLOCKED';$report.error=$_.Exception.GetBaseException().Message}
finally {$cn.Dispose();$secret.Dispose()}
$report | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $root 'logs\sage-initialization-dictionary.json') -Encoding UTF8
[pscustomobject]$report | Select-Object status,error | ConvertTo-Json
