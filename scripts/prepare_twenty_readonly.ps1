#requires -Version 5.1
# Preparation only: fixed SELECTs, getDescription and READ. No SAVE invocation.
[CmdletBinding()]param()
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root=Split-Path $PSScriptRoot -Parent
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$directory=Join-Path $root ('tests\ai-evaluation\real-20\preparation-'+$stamp)
$null=New-Item -ItemType Directory -Path $directory -Force
$report=[ordered]@{At=[DateTime]::UtcNow.ToString('o');Folder='TEST';Mode='READ_ONLY_PREPARATION';SaveAttempts=0;SqlWrites=0;Approved=$false;Items=@();Errors=@();EvidenceDirectory=$directory}
$cn=$null;$secret=$null
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'SageTestArticleSites.psm1') -Force
. (Join-Path $PSScriptRoot 'chat_sql_queries.ps1')
function Select-Preparation([string]$Sql,[hashtable]$Arguments) {
    $cmd=$cn.CreateCommand();$cmd.CommandTimeout=5;$rd=$null
    try {
        $cmd.CommandText=$Sql
        foreach($key in $Arguments.Keys){$p=$cmd.Parameters.Add('@'+$key,[Data.SqlDbType]::NVarChar,128);$p.Value=[string]$Arguments[$key]}
        $rd=$cmd.ExecuteReader();$rows=@()
        while($rd.Read()){
            $row=[ordered]@{}
            for($i=0;$i -lt $rd.FieldCount;$i++){$row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)}}
            $rows+=,[pscustomobject]$row
        }
        return ,$rows
    } finally {if($rd){$rd.Dispose()};$cmd.Dispose()}
}
try {
    $cred=Import-Clixml (Join-Path $root 'runtime\sql-reader-credential.clixml')
    $secret=$cred.Password.Copy();$secret.MakeReadOnly()
    # Preserve the existing reader's TLS policy; changing it requires approval.
    $cn=[Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;ApplicationIntent=ReadOnly')
    $cn.Credential=[Data.SqlClient.SqlCredential]::new($cred.UserName,$secret);$cn.Open()
    $report['SqlPermissions']=Select-Preparation "SELECT HAS_PERMS_BY_NAME(N'TEST',N'SCHEMA',N'SELECT') AS CanSelect, HAS_PERMS_BY_NAME(N'TEST',N'SCHEMA',N'INSERT') AS CanInsert, HAS_PERMS_BY_NAME(N'TEST',N'SCHEMA',N'UPDATE') AS CanUpdate, HAS_PERMS_BY_NAME(N'TEST',N'SCHEMA',N'DELETE') AS CanDelete, IS_SRVROLEMEMBER(N'sysadmin') AS IsSysadmin" @{}
    $report['SqlTablePermissions']=Select-Preparation "SELECT COUNT(*) AS TablesChecked, MAX(HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'INSERT')) AS AnyInsert, MAX(HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'UPDATE')) AS AnyUpdate, MAX(HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'DELETE')) AS AnyDelete FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=N'TEST'" @{}
    $report['SqlWritableTables']=Select-Preparation "SELECT TOP (50) t.name AS TableName, HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'INSERT') AS CanInsert, HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'UPDATE') AS CanUpdate FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=N'TEST' AND (HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'INSERT')=1 OR HAS_PERMS_BY_NAME(QUOTENAME(s.name)+N'.'+QUOTENAME(t.name),N'OBJECT',N'UPDATE')=1) ORDER BY t.name" @{}
    $report['Sites']=Select-Preparation (Get-ChatSelectQuery 'get_sites') @{Site=''}
    $report['Categories']=@()
    foreach($candidate in @('NEG','CADP')){$report.Categories+=Select-Preparation (Get-ChatSelectQuery 'get_article_categories') @{Category=$candidate;Label='';Pattern='%';NearPattern='%';Site=''}}
    $report['Units']=Select-Preparation (Get-ChatSelectQuery 'get_units') @{Unit='UN';Unit2='M2'}
    $report['ComparableM2']=Select-Preparation (Get-ChatSelectQuery 'search_articles') @{Category='NEG';Pattern='%XPS%'}
    $report['Supplier']=Select-Preparation (Get-ChatSelectQuery 'search_suppliers') @{Supplier='F1025';Label='';Pattern='%';NearPattern='%'}
    $report['Connection']=Connect-SageTestSoap
    $description=Get-SageTestDescription
    $description.Save((Join-Path $directory 'WS_ARTICLE-description.xml'))
    # This exported reader validates FOL/SOL/PNA/OBJ before the actual site READ.
    $null=Get-SageTestArticleSite -Code 'TESTAGENT005' -Site '201'
    $siteModule=Get-Module SageTestArticleSites
    $siteDescription=& $siteModule {Get-SageSiteDescription}
    $siteDescription.Save((Join-Path $directory 'WS_AR_SITE-description.xml'))
    $sites=@($report.Sites|Where-Object {$_.FCY_0.Trim() -in @('201','202','209')})
    if($sites.Count -eq 0){throw 'NO_VERIFIED_TEST_SITE'}
    $categories=@($report.Categories|Where-Object {$_.TCLCOD_0.Trim() -and $_.STU_0.Trim() -and $_.PUU_0.Trim() -and $_.SAU_0.Trim()})
    if($categories.Count -eq 0){throw 'NO_VERIFIED_TEST_CATEGORY'}
    for($i=0;$i -lt 20;$i++) {
        $code='TESTAGENT'+(5+$i).ToString('000')
        $site=$sites[$i%$sites.Count].FCY_0.Trim()
        $applicable=@($categories|Where-Object {$_.STOFCY_0.Trim() -eq '' -or $_.STOFCY_0.Trim() -eq $site})
        if($applicable.Count -eq 0){throw 'NO_APPLICABLE_CATEGORY_FOR_SITE'}
        $category=$applicable[$i%$applicable.Count]
        $name=if($i%2 -eq 0){'TEST IA RECETTE '+(1+$i).ToString('00')}else{'TEST IA RECETTE '+(1+$i).ToString('00')+' ARTICLE ET ARTICLE SITE CONTROLE'}
        $supplier=if($i%4 -eq 0 -and @($report.Supplier).Count -eq 1){'F1025'}else{''}
        $item=[ordered]@{Test=1+$i;Code=$code;Designation=$name;Folder='TEST';Site=$site;Category=$category.TCLCOD_0.Trim();StockUnit=$category.STU_0.Trim();PurchaseUnit=$category.PUU_0.Trim();SalesUnit=$category.SAU_0.Trim();SupplierCode=$supplier;StockManagement=[string]$category.STOMGTCOD_0;CategoryReference=$category;Status='1';ArticleCreation='NOT_ATTEMPTED';ArticleSiteCreation='NOT_ATTEMPTED';Readback='NOT_CREATED';Approved=$false;Blockers=@('EXACT_DATA_HUMAN_APPROVAL_REQUIRED','BUSINESS_RULES_REVIEW_REQUIRED','ARTICLE_SITE_CONNECTOR_SCOPE_EXT_POUDRE_ONLY')}
        if($item.Category -eq 'NEG' -and $i%5 -eq 0 -and @($report.ComparableM2|Where-Object {$_.STU_0.Trim() -eq 'M2' -and $_.PUU_0.Trim() -eq 'M2' -and $_.SAU_0.Trim() -eq 'M2'}).Count -gt 0){
            $item.StockUnit='M2';$item.PurchaseUnit='M2';$item.SalesUnit='M2';$item.Blockers+='UNIT_OVERRIDE_APPLICABILITY_REVIEW_REQUIRED'
        }
        try {
            $item['BeforeArticle']=Get-SageTestArticle -Code $code
            $item['BeforeSite']=Get-SageTestArticleSite -Code $code -Site $site
            if($item.BeforeArticle.Exists){$item.Blockers+= 'ARTICLE_ALREADY_EXISTS'}
            if($item.BeforeSite.Exists){$item.Blockers+= 'ARTICLE_SITE_ALREADY_EXISTS'}
            if(-not $item.BeforeArticle.Exists -and $item.StockUnit -eq $item.PurchaseUnit -and $item.StockUnit -eq $item.SalesUnit){
                $stockOverride=if($item.StockManagement -eq '1'){'1'}else{''}
                $plan=New-SageTestArticlePlan -Code $code -Designation $name -Category $item.Category -Unit $item.StockUnit -SupplierCode $supplier -StockManagement $stockOverride
                $item['ArticlePlan']=$plan
                [IO.File]::WriteAllText((Join-Path $directory ($code+'-article-NOT-SENT.xml')),$plan.ObjectXml,[Text.UTF8Encoding]::new($false))
            }else{$item.Blockers+='ARTICLE_XML_REQUIRES_REVIEWED_UNIT_MAPPING'}
            if($item.Category -ne 'NEG' -or $item.StockUnit -ne 'UN' -or $site -ne '201' -or $supplier){$item.Blockers+='CHAT_ARTICLE_CONNECTOR_SCOPE_NOT_APPLICABLE'}
        } catch {
            $message=$_.Exception.Message
            $item['Error']=if($message -cmatch '^[A-Z0-9_]+$'){$message}else{'PREPARATION_READ_FAILED'}
            $item.Blockers+='PREPARATION_INCOMPLETE'
        }
        $report.Items+=,[pscustomobject]$item
        $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $directory 'preparation.json') -Encoding UTF8
    }
} catch {
    $message=$_.Exception.Message
    $report.Errors+=if($message -cmatch '^[A-Z0-9_]+$'){$message}else{'READONLY_DIAGNOSTIC_FAILED'}
} finally {
    if($cn){$cn.Dispose()};if($secret){$secret.Dispose()};Disconnect-SageTestSoap
    $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $directory 'preparation.json') -Encoding UTF8
    @{directory=$directory;prepared=@($report.Items).Count;errors=$report.Errors;save_attempts=0}|ConvertTo-Json -Compress
}
