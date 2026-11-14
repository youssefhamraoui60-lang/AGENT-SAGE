# Explicit user-authorized TMS connection mode; SELECT only, TEST fixed.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$credential = Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
$password = $credential.Password.Copy(); $password.MakeReadOnly()
$connection = [System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=6;Application Name=AGENT-SAGE-X3-TEST-SELECT;ApplicationIntent=ReadOnly;Pooling=False')
$connection.Credential = [System.Data.SqlClient.SqlCredential]::new($credential.UserName,$password)
function Read-OnlyQuery {
    param([string]$Query,[hashtable]$Parameters)
    if ($Query -notmatch '^SELECT\b') { throw 'SELECT only' }
    $cmd=$connection.CreateCommand();$cmd.CommandTimeout=5;$cmd.CommandText=$Query
    foreach ($key in $Parameters.Keys) {
        $type=if ($Parameters[$key] -is [int]) {[System.Data.SqlDbType]::Int} else {[System.Data.SqlDbType]::NVarChar}
        $p=$cmd.Parameters.Add($key,$type);if ($type -eq [System.Data.SqlDbType]::NVarChar) {$p.Size=128};$p.Value=$Parameters[$key]
    }
    $reader=$null
    try {
        $reader=$cmd.ExecuteReader();$rows=[System.Collections.Generic.List[object]]::new()
        while ($reader.Read()) {
            $row=[ordered]@{}
            for ($i=0;$i -lt $reader.FieldCount;$i++) {$row[$reader.GetName($i)]=if ($reader.IsDBNull($i)) {$null} else {$reader.GetValue($i)}}
            $rows.Add([pscustomobject]$row)
        }
        return ,$rows.ToArray()
    } finally {if ($null -ne $reader) {$reader.Dispose()};$cmd.Dispose()}
}
$out=[ordered]@{checked_at=[DateTime]::UtcNow.ToString('o');connection_mode='EXPLICIT_TMS_OPTIONAL_ENCRYPTION';schema='TEST';sql_writes=0}
try {
    $connection.Open();$out.connected=$true
    $names=@('ITMMASTER','ITMFACILIT','BPSUPPLIER','BPCUSTOMER','BPARTNER','ITMCATEG','TABUNIT','FACILITY','BPSCATEG','BPCCATEG','ACODNUM','ACODNUMSEQ','ATEXTRA','AWEBSERVIC','AWEBSERDES','AOBJEXT','AOBJEXTD')
    $params=@{'@Folder'='TEST';'@Limit'=3000};$placeholders=@()
    for ($i=0;$i -lt $names.Count;$i++) {$key='@T'+$i;$params[$key]=$names[$i];$placeholders+=$key}
    # Only placeholder names are generated; schema/table values remain parameters.
    $out.columns=Read-OnlyQuery ('SELECT TOP (@Limit) t.name AS table_name,c.name AS column_name,ty.name AS data_type,c.max_length,c.is_nullable FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id WHERE s.name=@Folder AND t.name IN ('+($placeholders -join ',')+') ORDER BY t.name,c.column_id') $params
    $out.unique_keys=Read-OnlyQuery 'SELECT TOP (@Limit) t.name AS table_name,i.name AS index_name,i.is_primary_key,i.is_unique,c.name AS column_name,ic.key_ordinal FROM sys.indexes i JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id WHERE s.name=@Folder AND i.is_unique=@Unique AND ic.key_ordinal>@Zero AND t.name IN (@A,@B,@C,@D,@E) ORDER BY t.name,i.name,ic.key_ordinal' @{'@Limit'=100;'@Folder'='TEST';'@Unique'=1;'@Zero'=0;'@A'='ITMMASTER';'@B'='ITMFACILIT';'@C'='BPSUPPLIER';'@D'='BPCUSTOMER';'@E'='BPARTNER'}
    $out.foreign_keys=Read-OnlyQuery 'SELECT TOP (@Limit) p.name AS parent_table,pc.name AS parent_column,r.name AS referenced_table,rc.name AS referenced_column FROM sys.foreign_key_columns f JOIN sys.tables p ON p.object_id=f.parent_object_id JOIN sys.schemas s ON s.schema_id=p.schema_id JOIN sys.tables r ON r.object_id=f.referenced_object_id JOIN sys.columns pc ON pc.object_id=p.object_id AND pc.column_id=f.parent_column_id JOIN sys.columns rc ON rc.object_id=r.object_id AND rc.column_id=f.referenced_column_id WHERE s.name=@Folder AND p.name IN (@A,@B,@C,@D) ORDER BY p.name' @{'@Limit'=100;'@Folder'='TEST';'@A'='ITMMASTER';'@B'='ITMFACILIT';'@C'='BPSUPPLIER';'@D'='BPCUSTOMER'}
    $out.absence=[ordered]@{}
    $out.absence.article=Read-OnlyQuery 'SELECT TOP (@Limit) ITMREF_0 FROM TEST.ITMMASTER WHERE ITMREF_0=@Code' @{'@Limit'=1;'@Code'='AITEST001'}
    $out.absence.article_sites=Read-OnlyQuery 'SELECT TOP (@Limit) ITMREF_0,STOFCY_0 FROM TEST.ITMFACILIT WHERE ITMREF_0=@Code' @{'@Limit'=5;'@Code'='AITEST001'}
    $out.absence.supplier=Read-OnlyQuery 'SELECT TOP (@Limit) BPSNUM_0 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=@Code' @{'@Limit'=1;'@Code'='F_AITEST01'}
    $out.absence.customer=Read-OnlyQuery 'SELECT TOP (@Limit) BPCNUM_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@Code' @{'@Limit'=1;'@Code'='C_AITEST01'}
    $out.absence.partners=Read-OnlyQuery 'SELECT TOP (@Limit) BPRNUM_0 FROM TEST.BPARTNER WHERE BPRNUM_0 IN (@Supplier,@Customer)' @{'@Limit'=2;'@Supplier'='F_AITEST01';'@Customer'='C_AITEST01'}
    $out.article_category=Read-OnlyQuery 'SELECT TOP (@Limit) TCLCOD_0,STOFCY_0,ITMREFCOU_0,ITMCREMOD_0,STU_0,PUU_0,SAU_0,PUUSTUCOE_0,SAUSTUCOE_0,STOMGTCOD_0,LOTMGTCOD_0,ACCCOD_0,ABCCLS_0 FROM TEST.ITMCATEG WHERE TCLCOD_0=@Category ORDER BY STOFCY_0' @{'@Limit'=5;'@Category'='NEG'}
    $out.site=Read-OnlyQuery 'SELECT TOP (@Limit) FCY_0,CRY_0,LEGCPY_0,SALFLG_0,PURFLG_0,WRHFLG_0 FROM TEST.FACILITY WHERE FCY_0=@Site' @{'@Limit'=1;'@Site'='201'}
    $out.unit=Read-OnlyQuery 'SELECT TOP (@Limit) UOM_0,UOMDEC_0,UOMTYP_0 FROM TEST.TABUNIT WHERE UOM_0 IN (@Unit,@DefaultUnit)' @{'@Limit'=2;'@Unit'='SAC';'@DefaultUnit'='UN'}
    $out.supplier_categories=Read-OnlyQuery 'SELECT TOP (@Limit) BSGCOD_0,REFCOU_0,CREMOD_0,CRY_0,LAN_0,CUR_0,ACCCOD_0,VACBPR_0,PTE_0 FROM TEST.BPSCATEG ORDER BY BSGCOD_0' @{'@Limit'=5}
    $out.customer_categories=Read-OnlyQuery 'SELECT TOP (@Limit) BCGCOD_0,REFCOU_0,CREMOD_0,CRY_0,LAN_0,CUR_0,ACCCOD_0,VACBPR_0,PTE_0 FROM TEST.BPCCATEG ORDER BY BCGCOD_0' @{'@Limit'=5}
    $out.numbering=@()
    $counterCodes=@(@($out.article_category.ITMREFCOU_0)+@($out.supplier_categories.REFCOU_0)+@($out.customer_categories.REFCOU_0) | Where-Object {$_ -and ([string]$_).Trim()} | Sort-Object -Unique)
    foreach ($counterCode in $counterCodes) {
        $out.numbering+=Read-OnlyQuery 'SELECT TOP (@Limit) CODNUM_0,LNG_0,NIVDEF_0,NIVRAZ_0,TYP_0,NBPOS_0,CTLCHR_0,ZERO_0,SEQ_0 FROM TEST.ACODNUM WHERE CODNUM_0=@Counter' @{'@Limit'=1;'@Counter'=$counterCode}
    }
    $out.publication_table_candidates=Read-OnlyQuery 'SELECT TOP (@Limit) t.name AS table_name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=@Folder AND (t.name LIKE @Web OR t.name LIKE @Awe) ORDER BY t.name' @{'@Limit'=30;'@Folder'='TEST';'@Web'='%WEB%';'@Awe'='%AWE%'}
    $out.publications=Read-OnlyQuery 'SELECT TOP (@Limit) PUBLI_0,OBJET_0,TYPOBJ_0,VARIANTE_0,PRG_0,INVISIBLE_0,DATPUB_0 FROM TEST.AWEBSERVIC WHERE OBJET_0 IN (@Article,@Site,@Supplier,@Customer) OR PUBLI_0=@Import OR PRG_0=@Import ORDER BY OBJET_0,PUBLI_0' @{'@Limit'=30;'@Article'='ITM';'@Site'='ITF';'@Supplier'='BPS';'@Customer'='BPC';'@Import'='AOWSIMPORT'}
    $out.import_templates=Read-OnlyQuery 'SELECT TOP (@Limit) EXT_0,OBJ_0,ENAFLG_0,IMPORT_0,FONCTION_0,OPTUPD_0,OPTSPE_0,ENAWRK_0,TRTIMP_0,SPEIMP_0,SEPFLD_0,TYPFIL_0,TYPEXP_0,CHRNUM_0,FLDLIM_0 FROM TEST.AOBJEXT WHERE OBJ_0 IN (@Article,@Site,@Supplier,@Customer) ORDER BY OBJ_0,EXT_0' @{'@Limit'=30;'@Article'='ITM';'@Site'='ITF';'@Supplier'='BPS';'@Customer'='BPC'}
    $out.import_lines=Read-OnlyQuery 'SELECT TOP (@Limit) EXT_0,NUMLIG_0,SEL_0,TYP_0,BAL_0,FIL_0,FLD_0,OBL_0,COM_0,FMT_0,LNG_0,NUMTAB_0 FROM TEST.AOBJEXTD WHERE EXT_0 IN (@Customer,@Supplier,@Article) ORDER BY EXT_0,NUMLIG_0' @{'@Limit'=400;'@Customer'='BPC';'@Supplier'='BPS';'@Article'='ITMA'}
    $out.permissions=@()
    foreach ($objectName in 'TEST.ITMMASTER','TEST.ITMFACILIT','TEST.BPSUPPLIER','TEST.BPCUSTOMER') {
        $out.permissions+=Read-OnlyQuery 'SELECT @Object AS object_name,HAS_PERMS_BY_NAME(@Object,@Class,@Select) AS can_select,HAS_PERMS_BY_NAME(@Object,@Class,@Insert) AS can_insert,HAS_PERMS_BY_NAME(@Object,@Class,@Update) AS can_update,HAS_PERMS_BY_NAME(@Object,@Class,@Delete) AS can_delete' @{'@Object'=$objectName;'@Class'='OBJECT';'@Select'='SELECT';'@Insert'='INSERT';'@Update'='UPDATE';'@Delete'='DELETE'}
    }
    $out.status='PASS'
} catch {$out.status='FAILED';$out.error=$_.Exception.GetBaseException().Message}
finally {$connection.Dispose();$password.Dispose()}
$out | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath (Join-Path $root 'logs\four-creation-sql-discovery.json') -Encoding UTF8
[ordered]@{status=$out.status;connected=$out.connected;tables=@($out.columns.table_name | Sort-Object -Unique);column_count=@($out.columns).Count;absence=$out.absence;error=$out.error} | ConvertTo-Json -Depth 5
