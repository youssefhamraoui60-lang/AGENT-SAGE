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
    $report.results.permissions=Read-Query "SELECT SUSER_SNAME() AS login_name,DB_NAME() AS database_name,IS_ROLEMEMBER(@Reader) AS datareader,IS_ROLEMEMBER(@Writer) AS datawriter,HAS_PERMS_BY_NAME(NULL,NULL,'CREATE ANY DATABASE') AS create_any_database,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CREATE DATABASE') AS create_database" @{'@Reader'='db_datareader';'@Writer'='db_datawriter'}
    $report.results.recent_articles=Read-Query 'SELECT TOP (3) ITMREF_0,TCLCOD_0,STU_0,ROWID FROM TEST.ITMMASTER ORDER BY ROWID DESC' @{}
    $report.results.recent_article_sites=Read-Query 'SELECT TOP (3) ITMREF_0,STOFCY_0,ROWID FROM TEST.ITMFACILIT ORDER BY ROWID DESC' @{}
    $report.results.reference_article=Read-Query 'SELECT TOP (1) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0,PUUSTUCOE_0,SAUSTUCOE_0,STOMGTCOD_0,LOTMGTCOD_0,ACCCOD_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code' @{'@Code'='TSTAI2610174D94B4'}
    $report.results.reference_sites=Read-Query 'SELECT TOP (20) i.ITMREF_0,i.STOFCY_0 FROM TEST.ITMFACILIT i INNER JOIN TEST.ITMMASTER m ON m.ITMREF_0=i.ITMREF_0 WHERE m.ITMREF_0=@Code ORDER BY i.STOFCY_0' @{'@Code'='TSTAI2610174D94B4'}
    $report.results.article_sample=Read-Query 'SELECT TOP (20) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0,STOMGTCOD_0,LOTMGTCOD_0,ACCCOD_0,ROWID FROM TEST.ITMMASTER ORDER BY ROWID DESC' @{}
    $report.results.joined_site_sample=Read-Query 'SELECT TOP (30) i.ITMREF_0,m.ITMDES1_0,m.TCLCOD_0,m.STU_0,i.STOFCY_0,i.ROWID AS site_rowid FROM TEST.ITMFACILIT i INNER JOIN TEST.ITMMASTER m ON m.ITMREF_0=i.ITMREF_0 ORDER BY i.ROWID DESC' @{}
    $report.results.related_tables=Read-Query "SELECT TOP (30) t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=@Folder AND t.name IN ('ITMMASTER','ITMFACILIT','ITMSALES','ITMBPS','ITMBPC','ATEXTRA','GACCCODE','ITMCATEG','TABUNIT','BPARTNER','BPSUPPLIER','BPCUSTOMER') ORDER BY t.name" @{'@Folder'='TEST'}
    $report.results.physical_requirements=Read-Query "SELECT TOP (10) t.name AS table_name,COUNT(*) AS columns_count,SUM(CASE WHEN c.is_nullable=0 THEN 1 ELSE 0 END) AS non_nullable_count,SUM(CASE WHEN c.default_object_id<>0 THEN 1 ELSE 0 END) AS sql_default_count,SUM(CASE WHEN c.is_identity=1 THEN 1 ELSE 0 END) AS identity_count FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id WHERE s.name=@Folder AND t.name IN ('ITMMASTER','ITMFACILIT','ITMSALES','ITMBPS','ITMBPC','BPARTNER','BPSUPPLIER','BPCUSTOMER') GROUP BY t.name ORDER BY t.name" @{'@Folder'='TEST'}
    $report.results.article_sales=Read-Query 'SELECT TOP (5) ITMREF_0 FROM TEST.ITMSALES WHERE ITMREF_0=@Code' @{'@Code'='TSTAI2610174D94B4'}
    $report.results.article_suppliers=Read-Query 'SELECT TOP (5) ITMREF_0 FROM TEST.ITMBPS WHERE ITMREF_0=@Code' @{'@Code'='TSTAI2610174D94B4'}
    $report.results.article_customers=Read-Query 'SELECT TOP (5) ITMREF_0 FROM TEST.ITMBPC WHERE ITMREF_0=@Code' @{'@Code'='TSTAI2610174D94B4'}
    $report.results.recent_suppliers=Read-Query 'SELECT TOP (3) BPSNUM_0,BSGCOD_0,ROWID FROM TEST.BPSUPPLIER ORDER BY ROWID DESC' @{}
    $report.results.recent_customers=Read-Query 'SELECT TOP (3) BPCNUM_0,BCGCOD_0,ROWID FROM TEST.BPCUSTOMER ORDER BY ROWID DESC' @{}
    $report.results.creation_columns=Read-Query "SELECT TOP (2000) t.name AS table_name,c.column_id,c.name AS column_name,ty.name AS data_type,c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,c.is_computed,c.generated_always_type,c.default_object_id,dc.definition AS default_definition FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id LEFT JOIN sys.default_constraints dc ON dc.object_id=c.default_object_id WHERE s.name=@Folder AND t.name IN ('ITMMASTER','ITMFACILIT','ITMSALES','ITMBPS','ITMBPC','BPARTNER','BPSUPPLIER','BPCUSTOMER','BPADDRESS','CONTACT','ATEXTRA') ORDER BY t.name,c.column_id" @{'@Folder'='TEST'}
    $report.results.visible_triggers=Read-Query "SELECT TOP (100) t.name AS table_name,tr.name AS trigger_name,tr.is_disabled,OBJECTPROPERTY(tr.object_id,'ExecIsInsertTrigger') AS on_insert,OBJECTPROPERTY(tr.object_id,'ExecIsUpdateTrigger') AS on_update FROM sys.triggers tr JOIN sys.tables t ON t.object_id=tr.parent_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=@Folder AND t.name IN ('ITMMASTER','ITMFACILIT','ITMSALES','BPARTNER','BPSUPPLIER','BPCUSTOMER','BPADDRESS','CONTACT','ATEXTRA') ORDER BY t.name,tr.name" @{'@Folder'='TEST'}
    $report.results.visible_checks=Read-Query "SELECT TOP (100) t.name AS table_name,cc.name,cc.definition,cc.is_disabled,cc.is_not_trusted FROM sys.check_constraints cc JOIN sys.tables t ON t.object_id=cc.parent_object_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=@Folder AND t.name IN ('ITMMASTER','ITMFACILIT','ITMSALES','BPARTNER','BPSUPPLIER','BPCUSTOMER','BPADDRESS','CONTACT','ATEXTRA') ORDER BY t.name,cc.name" @{'@Folder'='TEST'}
    $report.results.metadata_visibility=Read-Query "SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','VIEW DEFINITION') AS database_view_definition" @{}
    $report.status='READ_ONLY_COMPLETED'
} catch {$report.status='BLOCKED';$report.error=$_.Exception.GetBaseException().Message}
finally {$cn.Dispose();$secret.Dispose()}
$report | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $root 'logs\SQL-ISOLATED-PREREQUISITES.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
