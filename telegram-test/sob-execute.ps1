$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$cn = $null; $secret = $null; $rd = $null
try {
    $r = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($r.mode -notin @('preview','create')) { throw 'Invalid mode' }
    if ([string]$r.reference -notmatch '^SOB-[a-f0-9]{16}$') { throw 'Invalid reference' }
    $cred = Import-Clixml (Join-Path $PSScriptRoot '../runtime/sql-reader-credential.clixml')
    $secret = $cred.Password.Copy(); $secret.MakeReadOnly()
    $cn = [System.Data.SqlClient.SqlConnection]::new('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=False;TrustServerCertificate=False;Connect Timeout=5;Pooling=False;Application Name=SOB-TEST-validated-order')
    $cn.Credential = [System.Data.SqlClient.SqlCredential]::new($cred.UserName,$secret)
    $cn.Open()
    $cmd = $cn.CreateCommand(); $cmd.CommandTimeout = 45
    $cmd.CommandText = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'sob-create.sql'))
    $null=$cmd.Parameters.Add('@AUTORISER_ECRITURE',[System.Data.SqlDbType]::Bit)
    $cmd.Parameters['@AUTORISER_ECRITURE'].Value=($r.mode -eq 'create')
    foreach ($name in @('CLIENT','REP_CODE','COMMENTAIRE','REFERENCE','LINES_JSON','EXPECTED_PLAN')) {
        $size = switch ($name) { 'CLIENT' {30} 'REFERENCE' {40} default {-1} }
        $null=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::NVarChar,$size)
        $value = switch ($name) {
            'CLIENT' {[string]$r.client}
            'REP_CODE' {[string]$r.representative}
            'COMMENTAIRE' {if($r.comment){[string]$r.comment}else{'SOB - creation TEST'}}
            'REFERENCE' {[string]$r.reference}
            'LINES_JSON' {ConvertTo-Json -InputObject @($r.lines) -Depth 5 -Compress}
            'EXPECTED_PLAN' {if ($r.expected_plan) {[string]$r.expected_plan} else {[DBNull]::Value}}
        }
        $cmd.Parameters['@'+$name].Value=$value
    }
    foreach ($name in @('DATE','LIVRAISON','EXPEDITION')) {
        $null=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::Date)
        $value = if ($name -eq 'DATE') {$r.order_date} else {$r.delivery}
        $cmd.Parameters['@'+$name].Value=[DateTime]::ParseExact($value,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)
    }
    $p=$cmd.Parameters.Add('@TOTAL_TTC_ATTENDU',[System.Data.SqlDbType]::Decimal)
    $p.Precision=27; $p.Scale=5
    $p.Value=[decimal]::Parse([string]$r.total,[Globalization.CultureInfo]::InvariantCulture)
    $rd=$cmd.ExecuteReader(); $rows=@()
    do {
        while ($rd.Read()) {
            $row=[ordered]@{}
            for ($i=0;$i -lt $rd.FieldCount;$i++) { $row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}else{$rd.GetValue($i)} }
            $rows += [pscustomobject]$row
        }
    } while ($rd.NextResult())
    @{ok=$true;rows=@($rows)} | ConvertTo-Json -Depth 8 -Compress
} catch {
    $sqlNumber = 0
    $exception = $_.Exception
    while ($exception) {
        if ($exception -is [System.Data.SqlClient.SqlException]) { $sqlNumber=$exception.Number; break }
        $exception=$exception.InnerException
    }
    @{ok=$false;code=$sqlNumber;error='Execution SOB impossible. Aucune relance automatique.'} | ConvertTo-Json -Compress
} finally {
    if ($rd) {$rd.Dispose()}
    if ($cn) {$cn.Dispose()}
    if ($secret) {$secret.Dispose()}
}
