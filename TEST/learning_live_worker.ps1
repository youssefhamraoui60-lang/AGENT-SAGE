# Fixed SELECT-only tools, TEST schema only. No memory values and no arbitrary SQL.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=$null;$cmd=$null;$rd=$null
try {
 $r=[Console]::In.ReadToEnd() | ConvertFrom-Json
 if($r.folder -cne 'TEST'){throw 'TEST only'}
 $cn=New-TestSupplierSqlConnection -ConnectionString $env:SAGE_SUPPLIER_SQL_CONNECTION_STRING -CredentialFile $env:SAGE_SUPPLIER_SQL_CREDENTIAL_FILE
 $cn.Open();$cmd=$cn.CreateCommand();$cmd.CommandTimeout=15
 foreach($key in 'code','site','company','ledger'){
  $value=[string]$r.$key;if($value.Length -gt 30){throw 'Oversized field'}
  $p=$cmd.Parameters.Add('@'+$key,[System.Data.SqlDbType]::NVarChar,30);$p.Value=$value
 }
 switch($r.kind){
  'stock' {
   if(-not $r.code -or -not $r.site){throw 'Article and site required'}
   $cmd.CommandText='SELECT s.ITMREF_0 AS Article,s.STOFCY_0 AS Site,s.STA_0 AS Statut,i.STU_0 AS Unite,SUM(s.QTYSTU_0) AS Quantite FROM TEST.STOCK s JOIN TEST.ITMMASTER i ON i.ITMREF_0=s.ITMREF_0 WHERE s.ITMREF_0=@code AND s.STOFCY_0=@site GROUP BY s.ITMREF_0,s.STOFCY_0,s.STA_0,i.STU_0'
  }
  'balance' {
   if(-not $r.code -or -not $r.company -or -not $r.ledger){throw 'Account company ledger required'}
   foreach($key in 'date_from','date_to'){
    $p=$cmd.Parameters.Add('@'+$key,[System.Data.SqlDbType]::Date);$p.Value=[datetime]::ParseExact($r.$key,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)
   }
   $cmd.CommandText='SELECT CPY_0 AS Societe,LED_0 AS Referentiel,ACC_0 AS Compte,CURLED_0 AS Devise,SNS_0 AS Sens,SUM(AMTLED_0) AS Montant,COUNT_BIG(*) AS Ecritures FROM TEST.GACCENTRYD WHERE CPY_0=@company AND LED_0=@ledger AND ACC_0=@code AND ACCDAT_0>=@date_from AND ACCDAT_0<DATEADD(day,1,@date_to) GROUP BY CPY_0,LED_0,ACC_0,CURLED_0,SNS_0'
  }
  'code' {
   if($r.code -notmatch '^F[0-9]{1,14}$'){throw 'Invalid supplier code'}
   $cmd.CommandText='SELECT @code AS Code,CASE WHEN EXISTS(SELECT 1 FROM TEST.BPARTNER WHERE BPRNUM_0=@code) OR EXISTS(SELECT 1 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=@code) OR EXISTS(SELECT 1 FROM TEST.BPADDRESS WHERE BPANUM_0=@code) THEN ''Utilise'' ELSE ''Absent au moment du controle, non reserve'' END AS Disponibilite'
  }
  default {throw 'Unknown read tool'}
 }
 if($cmd.CommandText -notmatch '^SELECT\b'){throw 'SELECT only'}
 $rd=$cmd.ExecuteReader();$rows=@()
 while($rd.Read()){
  $row=[ordered]@{}
  for($i=0;$i -lt $rd.FieldCount;$i++){
   $value=$rd.GetValue($i)
   $row[$rd.GetName($i)]=if($rd.IsDBNull($i)){$null}elseif($value -is [decimal]){$value.ToString([Globalization.CultureInfo]::InvariantCulture)}else{$value}
  }
  $rows+=,$row
 }
 $answer=@{ok=$true;rows=$rows;folder='TEST';source='Sage TEST lecture actuelle';checked_at=[datetime]::UtcNow.ToString('o');writes=0;training_excluded=$true}
}catch{$answer=@{ok=$false;code='live_read_unavailable_or_not_permitted';folder='TEST';writes=0;training_excluded=$true}}
finally{if($rd){$rd.Dispose()};if($cmd){$cmd.Dispose()};if($cn){$cn.Dispose()}}
$answer | ConvertTo-Json -Depth 6 -Compress
