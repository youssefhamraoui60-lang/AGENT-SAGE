[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$credential=Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
$secret=$credential.Password.Copy();$secret.MakeReadOnly()
$target='AGENT_SAGE_X3_SANDBOX'
$cn=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=AGENT_SAGE_X3_SANDBOX;Encrypt=False;TrustServerCertificate=False;Connect Timeout=6;Pooling=False;Application Name=AGENT-isolated-creation-tests')
$cn.Credential=[System.Data.SqlClient.SqlCredential]::new($credential.UserName,$secret)
$report=[ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');database=$target;mode='TMS_OPTIONAL_ENCRYPTION';connected=$false;committed=$false;statements=@();objects=@();sage_writes=0}
$tx=$null
function Run-Sql([string]$sql,[hashtable]$values,[bool]$read=$false) {
    $cmd=$cn.CreateCommand();$cmd.CommandText=$sql;$cmd.CommandTimeout=10
    if($tx){$cmd.Transaction=$tx}
    foreach($key in $values.Keys){$p=$cmd.Parameters.Add($key,[System.Data.SqlDbType]::NVarChar,128);$p.Value=$values[$key]}
    $report.statements += [pscustomobject]@{sql=$sql;parameters=$values}
    $reader=$null
    try {
        if(-not $read){return $cmd.ExecuteNonQuery()}
        $reader=$cmd.ExecuteReader();$rows=[System.Collections.Generic.List[object]]::new()
        while($reader.Read()){
            $row=[ordered]@{}
            for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}}
            $rows.Add([pscustomobject]$row)
        }
        return ,$rows.ToArray()
    } finally {if($reader){$reader.Dispose()};$cmd.Dispose()}
}
try {
    $cn.Open();$report.connected=$true
    $identity=Run-Sql 'SELECT DB_NAME() AS database_name, SUSER_SNAME() AS login_name, HAS_PERMS_BY_NAME(DB_NAME(),@DbClass,@CreateTable) AS can_create_table, HAS_PERMS_BY_NAME(@Schema,@SchemaClass,@Alter) AS can_alter_schema, HAS_PERMS_BY_NAME(@Schema,@SchemaClass,@Insert) AS can_insert, HAS_PERMS_BY_NAME(@Schema,@SchemaClass,@Select) AS can_select, HAS_PERMS_BY_NAME(@Schema,@SchemaClass,@References) AS can_reference' @{'@DbClass'='DATABASE';'@CreateTable'='CREATE TABLE';'@Schema'='simulation';'@SchemaClass'='SCHEMA';'@Alter'='ALTER';'@Insert'='INSERT';'@Select'='SELECT';'@References'='REFERENCES'} $true
    $report.identity=$identity
    if($identity[0].database_name -cne $target){throw 'Wrong database: no writes permitted'}
    foreach($perm in 'can_create_table','can_alter_schema','can_insert','can_select','can_reference') {if($identity[0].$perm -ne 1){throw "Missing sandbox permission: $perm"}}
    $tx=$cn.BeginTransaction([System.Data.IsolationLevel]::Serializable)
    $ddl=@'
IF DB_NAME() <> N'AGENT_SAGE_X3_SANDBOX' THROW 51000, 'Wrong database', 1;
IF OBJECT_ID(N'simulation.Article',N'U') IS NULL
 CREATE TABLE simulation.Article(Code nvarchar(20) NOT NULL PRIMARY KEY,Designation nvarchar(100) NOT NULL,Category nvarchar(10) NOT NULL,Unit nvarchar(10) NOT NULL);
IF OBJECT_ID(N'simulation.ArticleSite',N'U') IS NULL
 CREATE TABLE simulation.ArticleSite(ArticleCode nvarchar(20) NOT NULL,Site nvarchar(10) NOT NULL CHECK(Site=N'201'),PRIMARY KEY(ArticleCode,Site),FOREIGN KEY(ArticleCode) REFERENCES simulation.Article(Code));
IF OBJECT_ID(N'simulation.Fournisseur',N'U') IS NULL
 CREATE TABLE simulation.Fournisseur(Code nvarchar(20) NOT NULL PRIMARY KEY,LegalName nvarchar(100) NOT NULL,Category nvarchar(10) NOT NULL,Country nvarchar(2) NOT NULL,Currency nvarchar(3) NOT NULL);
IF OBJECT_ID(N'simulation.Client',N'U') IS NULL
 CREATE TABLE simulation.Client(Code nvarchar(20) NOT NULL PRIMARY KEY,LegalName nvarchar(100) NOT NULL,Category nvarchar(10) NOT NULL,Country nvarchar(2) NOT NULL,Currency nvarchar(3) NOT NULL);
'@
    $null=Run-Sql $ddl @{}
    $cases=@(
        @{name='Article';query='SELECT Code,Designation,Category,Unit FROM simulation.Article WHERE Code=@Code';insert='INSERT INTO simulation.Article(Code,Designation,Category,Unit) VALUES(@Code,@Designation,@Category,@Unit)';values=@{'@Code'='AITEST001';'@Designation'='ARTICLE TEST CREATION API SAGE X3';'@Category'='NEG';'@Unit'='UN'}},
        @{name='ArticleSite';query='SELECT ArticleCode,Site FROM simulation.ArticleSite WHERE ArticleCode=@ArticleCode AND Site=@Site';insert='INSERT INTO simulation.ArticleSite(ArticleCode,Site) VALUES(@ArticleCode,@Site)';values=@{'@ArticleCode'='AITEST001';'@Site'='201'}},
        @{name='Fournisseur';query='SELECT Code,LegalName,Category,Country,Currency FROM simulation.Fournisseur WHERE Code=@Code';insert='INSERT INTO simulation.Fournisseur(Code,LegalName,Category,Country,Currency) VALUES(@Code,@LegalName,@Category,@Country,@Currency)';values=@{'@Code'='F_AITEST01';'@LegalName'='FOURNISSEUR TEST IA';'@Category'='FR';'@Country'='MA';'@Currency'='MAD'}},
        @{name='Client';query='SELECT Code,LegalName,Category,Country,Currency FROM simulation.Client WHERE Code=@Code';insert='INSERT INTO simulation.Client(Code,LegalName,Category,Country,Currency) VALUES(@Code,@LegalName,@Category,@Country,@Currency)';values=@{'@Code'='C_AITEST01';'@LegalName'='CLIENT TEST IA';'@Category'='CL';'@Country'='MA';'@Currency'='MAD'}}
    )
    foreach($case in $cases){
        $before=Run-Sql $case.query $case.values $true
        $status='EXISTANT'
        if($before.Count -eq 0){$null=Run-Sql $case.insert $case.values;$status='INSERE_SANDBOX'}
        $rows=Run-Sql $case.query $case.values $true
        if($rows.Count -ne 1){throw "Verification count failed: $($case.name)"}
        foreach($key in $case.values.Keys){$column=$key.Substring(1);if([string]$rows[0].$column -cne [string]$case.values[$key]){throw "Existing or inserted data differs: $($case.name).$column"}}
        $report.objects += [pscustomobject]@{object=$case.name;status=$status;row=$rows[0]}
    }
    $report.article_site_relation=Run-Sql 'SELECT a.Code,s.Site FROM simulation.Article a JOIN simulation.ArticleSite s ON s.ArticleCode=a.Code WHERE a.Code=@Code AND s.Site=@Site' @{'@Code'='AITEST001';'@Site'='201'} $true
    if($report.article_site_relation.Count -ne 1){throw 'Article/site relationship verification failed'}
    $tx.Commit();$tx.Dispose();$tx=$null;$report.committed=$true
    # Re-read after commit on the same database, outside the transaction.
    $report.persisted=@()
    foreach($case in $cases){$rows=Run-Sql $case.query $case.values $true;if($rows.Count -ne 1){throw 'Post-commit verification failed'};$report.persisted += [pscustomobject]@{object=$case.name;row=$rows[0]}}
    $report.status='SANDBOX_VERIFIED'
} catch {
    $report.error=$_.Exception.GetBaseException().Message
    if(-not $report.connected){
        $probe=[System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=master;Encrypt=False;TrustServerCertificate=False;Connect Timeout=6;Pooling=False;Application Name=AGENT-sandbox-existence-check')
        $probe.Credential=[System.Data.SqlClient.SqlCredential]::new($credential.UserName,$secret)
        try {
            $probe.Open();$cmd=$probe.CreateCommand();$cmd.CommandTimeout=5
            $cmd.CommandText='SELECT DB_ID(@Db) AS database_id,HAS_DBACCESS(@Db) AS has_access,CAST(SERVERPROPERTY(''ServerName'') AS nvarchar(128)) AS server_instance,SUSER_SNAME() AS login_name'
            $null=$cmd.Parameters.Add('@Db',[System.Data.SqlDbType]::NVarChar,128);$cmd.Parameters['@Db'].Value=$target
            $rd=$cmd.ExecuteReader()
            if($rd.Read()){$report.existence_probe=@{database_id=if($rd.IsDBNull(0)){$null}else{$rd.GetValue(0)};has_access=if($rd.IsDBNull(1)){$null}else{$rd.GetValue(1)};server_instance=$rd.GetValue(2);login_name=$rd.GetValue(3)}}
            $rd.Dispose();$cmd.Dispose()
        } catch {$report.existence_probe_error=$_.Exception.GetBaseException().Message}
        finally {$probe.Dispose()}
    }
    if($tx){try{$tx.Rollback();$report.rolled_back=$true}catch{$report.rollback_error=$_.Exception.GetBaseException().Message};$tx.Dispose();$tx=$null}
    $report.status=if($report.committed){'COMMITTED_VERIFICATION_ERROR'}else{'BLOCKED_OR_ROLLED_BACK'}
} finally {$cn.Dispose();$secret.Dispose()}
$report | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $root 'logs\SQL-SANDBOX-CREATION-RESULTS.json') -Encoding UTF8
[pscustomobject]$report | Select-Object checked_at,database,connected,committed,status,error,objects,identity,existence_probe | ConvertTo-Json -Depth 8
