# Read-only, parameterized SQL inventory. Verified TLS by default.
# Explicit -UseTmsConnectionMode permits optional encryption as requested by user.
[CmdletBinding()]
param([string]$Article = 'CPJ35',[switch]$UseTmsConnectionMode)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$credentialPath = Join-Path $projectRoot 'runtime\sql-reader-credential.clixml'
$sqlCredential = Import-Clixml -LiteralPath $credentialPath
$sqlPassword = $sqlCredential.Password.Copy()
$sqlPassword.MakeReadOnly()
$connectionString = 'Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=True;TrustServerCertificate=False;Connect Timeout=6;Application Name=AGENT-SAGE-X3-readonly;ApplicationIntent=ReadOnly;Pooling=False'
if ($UseTmsConnectionMode) { $connectionString = $connectionString.Replace('Encrypt=True;','Encrypt=False;') }
$connection = [System.Data.SqlClient.SqlConnection]::new($connectionString)
$connection.Credential = [System.Data.SqlClient.SqlCredential]::new($sqlCredential.UserName,$sqlPassword)
$report = [ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');host='192.168.9.200';dns='sage';instance_browser='SAGEX3';port=1433;database='x3v12';connected=$false;tls_validation_required=$true;sql_write_statements=0;queries=@{}}
$report.tls_validation_required = -not [bool]$UseTmsConnectionMode
$report.connection_mode = if ($UseTmsConnectionMode) { 'TMS_OPTIONAL_ENCRYPTION_EXPLICIT_USER_REQUEST' } else { 'VERIFIED_TLS' }
function Invoke-SageSelect {
    param([string]$Query,[hashtable]$Parameters)
    if ($Query -notmatch '^SELECT\b') { throw 'Only fixed SELECT queries are permitted' }
    $command = $connection.CreateCommand()
    $command.CommandTimeout = 5
    $command.CommandText = $Query
    foreach ($key in $Parameters.Keys) {
        $value = $Parameters[$key]
        $type = if ($value -is [int]) { [System.Data.SqlDbType]::Int } else { [System.Data.SqlDbType]::NVarChar }
        $parameter = $command.Parameters.Add($key,$type)
        if ($type -eq [System.Data.SqlDbType]::NVarChar) { $parameter.Size = 128 }
        $parameter.Value = $value
    }
    $reader = $null
    try {
        $reader = $command.ExecuteReader()
        $rows = [System.Collections.Generic.List[object]]::new()
        while ($reader.Read()) {
            $row = [ordered]@{}
            for ($index=0; $index -lt $reader.FieldCount; $index++) {
                $row[$reader.GetName($index)] = if ($reader.IsDBNull($index)) { $null } else { $reader.GetValue($index) }
            }
            $rows.Add([pscustomobject]$row)
        }
        return ,$rows.ToArray()
    } finally { if ($null -ne $reader) { $reader.Dispose() }; $command.Dispose() }
}
try {
    $connection.Open()
    $report.connected = $true
    $report.server_version = $connection.ServerVersion
    $report.queries.identity = Invoke-SageSelect 'SELECT CAST(SERVERPROPERTY(@ServerProperty) AS nvarchar(128)) AS instance_name, DB_NAME() AS database_name, IS_ROLEMEMBER(@ReaderRole) AS is_datareader, IS_ROLEMEMBER(@WriterRole) AS is_datawriter' @{'@ServerProperty'='InstanceName';'@ReaderRole'='db_datareader';'@WriterRole'='db_datawriter'}
    $report.queries.tables = Invoke-SageSelect 'SELECT TOP (@Limit) s.name AS schema_name,t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE t.name IN (@Master,@Facility,@Category,@Units,@Supplier) ORDER BY s.name,t.name' @{'@Limit'=50;'@Master'='ITMMASTER';'@Facility'='ITMFACILIT';'@Category'='ITMCATEG';'@Units'='TABUNIT';'@Supplier'='BPSUPPLIER'}
    $report.queries.columns = Invoke-SageSelect 'SELECT TOP (@Limit) t.name AS table_name,c.name AS column_name,ty.name AS data_type,c.max_length,c.is_nullable FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id WHERE s.name=@Folder AND t.name IN (@Master,@Facility) ORDER BY t.name,c.column_id' @{'@Limit'=600;'@Folder'='TEST';'@Master'='ITMMASTER';'@Facility'='ITMFACILIT'}
    # Identifiers are fixed, not supplied by a request. Execute only after metadata confirms them.
    $masterColumns = @($report.queries.columns | Where-Object table_name -EQ 'ITMMASTER' | Select-Object -ExpandProperty column_name)
    $required = @('ITMREF_0','ITMDES1_0','TCLCOD_0','STU_0','PUU_0','SAU_0')
    $missing = @($required | Where-Object { $_ -notin $masterColumns })
    if ($missing.Count -eq 0) {
        $report.queries.article = Invoke-SageSelect 'SELECT TOP (@Limit) ITMREF_0,ITMDES1_0,TCLCOD_0,STU_0,PUU_0,SAU_0 FROM [TEST].[ITMMASTER] WHERE ITMREF_0=@Article' @{'@Limit'=1;'@Article'=$Article}
    } else { $report.article_query_status = 'Mapping requires metadata review; no speculative data query executed' }
    $report.queries.permissions = Invoke-SageSelect 'SELECT HAS_PERMS_BY_NAME(@Object,@Class,@Select) AS can_select,HAS_PERMS_BY_NAME(@Object,@Class,@Insert) AS can_insert,HAS_PERMS_BY_NAME(@Object,@Class,@Update) AS can_update,HAS_PERMS_BY_NAME(@Object,@Class,@Delete) AS can_delete' @{'@Object'='TEST.ITMMASTER';'@Class'='OBJECT';'@Select'='SELECT';'@Insert'='INSERT';'@Update'='UPDATE';'@Delete'='DELETE'}
    try {
        $report.queries.session_encryption = Invoke-SageSelect 'SELECT encrypt_option,net_transport,auth_scheme FROM sys.dm_exec_connections WHERE session_id=@@SPID AND @Check=1' @{'@Check'=1}
    } catch { $report.session_encryption_check = 'Not accessible with this account; no permissions changed' }
    $report.status = 'READ_ONLY_QUERIES_COMPLETED'
} catch {
    $message = $_.Exception.GetBaseException().Message
    $report.error_category = if ($message -match 'certificat|certificate') { 'TLS_CERTIFICATE_VALIDATION_FAILED' } else { $_.Exception.GetBaseException().GetType().Name }
    $report.status = 'CONNECTION_OR_QUERY_BLOCKED'
} finally { $connection.Dispose(); $sqlPassword.Dispose() }
$reportFile = if ($UseTmsConnectionMode) { 'logs\sql-server-tms-mode-tests.json' } else { 'logs\sql-server-readonly-tests.json' }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $projectRoot $reportFile) -Encoding UTF8
$report | ConvertTo-Json -Depth 8
