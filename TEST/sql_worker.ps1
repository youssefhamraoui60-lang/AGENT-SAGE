# Private chat transport: fixed SQL file, typed parameters; no model-generated SQL.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$cn=$null;$cmd=$null;$reader=$null;$started=$false
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
try {
 $request=[Console]::In.ReadToEnd() | ConvertFrom-Json
 if($request.folder -cne (Get-SupplierTarget) -or $request.execute -isnot [bool]){throw 'Invalid TEST request'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$started=$true
 $permissions=@(Get-TestSupplierSqlPermissions $cn)
 if(@($permissions | Where-Object {Test-SupplierSqlPermissionMissing $_}).Count -gt 0){
  $answer=@{ok=$false;code='sql_permissions_missing';folder=(Get-SupplierTarget);started=$true;permissions=$permissions}
  [Console]::WriteLine(($answer | ConvertTo-Json -Depth 8 -Compress));return
 }
 $cmd=$cn.CreateCommand();$cmd.CommandTimeout=60
 $cmd.CommandText=Get-SupplierSqlText 'create_supplier.sql'
 $sizes=@{Nom=100;NomCourt=30;ICE=15;IF=30;RC=30;Adresse=100;Ville=50;Telephone=30;Fax=30;Paiement=10;Categorie=10;CodeComptable=10;RegimeTaxe=10;Devise=10;TypeLibelle=3;CodeModele=30;Pays=3;Statut=1}
 foreach($name in $sizes.Keys){
  $value=$request.parameters.$name
  if($null -eq $value -or ([string]$value).Length -gt $sizes[$name]){throw "Invalid parameter: $name"}
  $p=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::NVarChar,$sizes[$name]);$p.Value=[string]$value
 }
 foreach($name in 'Adresse2','Adresse3'){
  $value=[string]$request.parameters.$name
  if($value.Length -gt 50){throw "Invalid address line: $name"}
  $p=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::NVarChar,50);$p.Value=$value
 }
 $p=$cmd.Parameters.Add('@UseAddressLines',[System.Data.SqlDbType]::Bit);$p.Value=((Get-SupplierTarget) -cin @('TEST','OB'))
 $p=$cmd.Parameters.Add('@DateRegularite',[System.Data.SqlDbType]::DateTime)
 $p.Value=[datetime]::ParseExact($request.parameters.DateRegularite,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)
 $p=$cmd.Parameters.Add('@TypeMontant',[System.Data.SqlDbType]::Int);$p.Value=[int]$request.parameters.TypeMontant
 $p=$cmd.Parameters.Add('@Execute',[System.Data.SqlDbType]::Bit);$p.Value=$request.execute
 $p=$cmd.Parameters.Add('@AllowDuplicates',[System.Data.SqlDbType]::Bit);$p.Value=($request.allow_duplicates -eq $true)
 $p=$cmd.Parameters.Add('@ApprovedDuplicateCodes',[System.Data.SqlDbType]::NVarChar,-1);$p.Value=ConvertTo-Json -InputObject @($request.approved_duplicate_codes | Where-Object {$_}) -Compress
 $reader=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
 do {
  while($reader.Read()){
   $row=[ordered]@{}
   for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}elseif($reader.GetValue($i) -is [datetime]){$reader.GetDateTime($i).ToString('s')}else{$reader.GetValue($i)}}
   $rows.Add([pscustomobject]$row)
  }
 } while($reader.NextResult())
 $answer=@{ok=$true;rows=$rows.ToArray();folder=(Get-SupplierTarget);executed=$request.execute}
 if(-not $request.execute){
  $reader.Dispose();$reader=$null
  $cmd.CommandText=Get-SupplierSqlText 'preparation_diagnostics.sql'
  $reader=$cmd.ExecuteReader();$warnings=@()
  while($reader.Read()){
   if(-not $reader.IsDBNull(1)){
    $warnings+=@{code=[string]$reader['duplicate_code'];name=[string]$reader['duplicate_name'];ice_match=[int]$reader['ice_match'];fiscal_match=[int]$reader['fiscal_match'];rc_match=[int]$reader['rc_match'];name_match=[int]$reader['name_match']}
   }
  }
  $answer.duplicate_warnings=$warnings
 }
} catch {
 $errorNumber=$null;$inner=$_.Exception
 while($inner){if($inner -is [System.Data.SqlClient.SqlException]){$errorNumber=$inner.Number;break};$inner=$inner.InnerException}
 # Never expose credentials, server connection strings or supplier data in errors.
 $code=if(-not $started){'sql_connection_or_configuration_unavailable'}elseif($errorNumber -ge 50000){'sql_validation_rejected'}else{'sql_result_requires_readback'}
 $answer=@{ok=$false;code=$code;sql_error_number=$errorNumber;folder=(Get-SupplierTarget);started=$started}
 if($request.execute -eq $false -and $errorNumber -ge 50000 -and $cn.State -eq 'Open'){
  try {
   if($reader){$reader.Dispose();$reader=$null}
   $cmd.CommandText=Get-SupplierSqlText 'preparation_diagnostics.sql'
   $reader=$cmd.ExecuteReader();$diagnostics=[Collections.Generic.List[object]]::new()
   while($reader.Read()){
    $row=[ordered]@{}
    for($i=0;$i -lt $reader.FieldCount;$i++){$row[$reader.GetName($i)]=if($reader.IsDBNull($i)){$null}else{$reader.GetValue($i)}}
    $diagnostics.Add([pscustomobject]$row)
   }
   $answer.diagnostics=$diagnostics.ToArray()
   if($errorNumber -eq 50105){
    $reader.Dispose();$reader=$null
    $cmd.CommandText=Get-SupplierSqlText 'supplier_field_constraints.sql'
    $reader=$cmd.ExecuteReader();$constraints=@()
    while($reader.Read()){
     $field=[string]$reader['field'];$limit=if($reader.IsDBNull(5)){$null}else{[int]$reader['max_characters']}
     $length=([string]$request.parameters.$field).Length
     if($null -ne $limit -and $limit -ge 0 -and $length -gt $limit){$constraints+=@{field=$field;limit=$limit;length=$length}}
    }
    $answer.field_errors=$constraints
   }
  }catch{$answer.diagnostics_unavailable=$true}
 }
} finally {
 if($reader){$reader.Dispose()}
 if($cn -and $cn.State -eq 'Open' -and $request.execute -eq $false -and $answer){
  $probe=$cn.CreateCommand()
  try {
   $probe.CommandText="DECLARE @tc int=@@TRANCOUNT; DECLARE @xs int=XACT_STATE(); SELECT CONCAT(@tc, ':', @xs)"
   $answer.transaction_after=[string]$probe.ExecuteScalar()
  }catch{$answer.transaction_check_unavailable=$true}finally{$probe.Dispose()}
 }
 if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()};if($secret){$secret.Dispose()}
}
[Console]::WriteLine(($answer | ConvertTo-Json -Depth 8 -Compress))
