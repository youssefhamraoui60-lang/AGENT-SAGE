$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null
try {
 $file=$env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 if(-not $file){$file=Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime/sql-reader-credential.clixml'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $file
 $cn.Open()
 $rows=@(Get-TestSupplierSqlPermissions $cn)
 $missing=@($rows | Where-Object {Test-SupplierSqlPermissionMissing $_})
 $answer=@{ok=$true;folder=(Get-SupplierTarget);encrypted=$true;trust_server_certificate=((Get-SupplierTarget) -ceq 'TEST' -or $env:SAGE_SUPPLIER_OB_TRUST_SERVER_CERTIFICATE -ceq 'true');ready=($missing.Count -eq 0);permissions=$rows;writes=0}
}catch{
 $tls=($_.Exception.ToString() -match 'certificate|certificat|SSL|TLS')
 $answer=@{ok=$false;folder=(Get-SupplierTarget);ready=$false;code=if($tls){'sql_tls_validation_failed'}else{'sql_connection_or_permissions_unavailable'};writes=0}
}
finally{if($cn){$cn.Dispose()}}
$answer | ConvertTo-Json -Depth 5
