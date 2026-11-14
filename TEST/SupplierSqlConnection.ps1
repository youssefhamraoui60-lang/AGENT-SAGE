# Scope of this certificate exception: the fixed supplier SQL in x3v12.TEST.
function Get-SupplierTarget {
 $target=$env:SAGE_SUPPLIER_TARGET_FOLDER
 if(-not $target){return 'TEST'}
 if($target -cnotin @('TEST','OB')){throw 'Invalid supplier folder'}
 return $target
}
function Get-SupplierSqlText {
 param([string]$Name)
 if($Name -cnotin @('permissions.sql','create_supplier.sql','preparation_diagnostics.sql','supplier_field_constraints.sql','supplier_reference_labels.sql','model_defaults.sql')){throw 'Invalid supplier SQL file'}
 $text=Get-Content -LiteralPath (Join-Path $PSScriptRoot $Name) -Raw -Encoding UTF8
 if((Get-SupplierTarget) -ceq 'OB'){$text=$text.Replace('TEST','OB')}
 return $text
}
function New-TestSupplierSqlConnection {
 param([string]$ConnectionString,[string]$CredentialFile,[System.Management.Automation.PSCredential]$Credential)
 if(-not $ConnectionString){$ConnectionString='Data Source=tcp:sage,1433;Initial Catalog=x3v12;Connect Timeout=5'}
 $builder=[System.Data.SqlClient.SqlConnectionStringBuilder]::new($ConnectionString)
 if($builder.InitialCatalog -cne 'x3v12'){throw 'Base imposee: x3v12'}
 # Explicit user-approved TEST exception; never changes the shared SQL reader.
 $builder['Encrypt']=$true
 $target=Get-SupplierTarget
 $builder['TrustServerCertificate']=($target -ceq 'TEST' -or ($target -ceq 'OB' -and $env:SAGE_SUPPLIER_OB_TRUST_SERVER_CERTIFICATE -ceq 'true'))
 $builder['Application Name']='AGENT-'+$target+'-Supplier-DirectSQL'
 $cn=[System.Data.SqlClient.SqlConnection]::new($builder.ConnectionString)
 if(-not $Credential -and $CredentialFile){$Credential=Import-Clixml -LiteralPath $CredentialFile}
 if($Credential){
  $secret=$Credential.Password.Copy();$secret.MakeReadOnly()
  $cn.Credential=[System.Data.SqlClient.SqlCredential]::new($Credential.UserName,$secret)
 }
 return $cn
}

function Get-TestSupplierSqlPermissions {
 param([System.Data.SqlClient.SqlConnection]$Connection)
 $cmd=$Connection.CreateCommand();$cmd.CommandTimeout=15;$reader=$null
 try {
  $cmd.CommandText=Get-SupplierSqlText 'permissions.sql'
  $reader=$cmd.ExecuteReader();$rows=[Collections.Generic.List[object]]::new()
  while($reader.Read()){
   $rows.Add([pscustomobject]@{object=$reader.GetString(0);can_select=[int]$reader.GetValue(1);can_insert=[int]$reader.GetValue(2);requires_insert=[int]$reader.GetValue(3);requires_select=[int]$reader.GetValue(4);can_execute=[int]$reader.GetValue(5);requires_execute=[int]$reader.GetValue(6)})
  }
  return $rows.ToArray()
 }finally{if($reader){$reader.Dispose()};$cmd.Dispose()}
}

function Test-SupplierSqlPermissionMissing {
 param($Row)
 return (($Row.requires_select -eq 1 -and $Row.can_select -ne 1) -or ($Row.requires_insert -eq 1 -and $Row.can_insert -ne 1) -or ($Row.requires_execute -eq 1 -and $Row.can_execute -ne 1))
}
