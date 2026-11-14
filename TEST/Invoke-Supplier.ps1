[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$DataPath,
 [Parameter(Mandatory=$true)][string]$ConnectionString,
 [System.Management.Automation.PSCredential]$Credential,
 [switch]$Create
)
$ErrorActionPreference='Stop'
$data=Get-Content -LiteralPath $DataPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($name in 'Adresse2','Adresse3'){
 if($null -eq $data.PSObject.Properties[$name]){$data | Add-Member -NotePropertyName $name -NotePropertyValue ''}
}
if(([string]$data.Adresse).Length -gt 50 -and -not $data.Adresse2 -and -not $data.Adresse3){
 $remaining=([regex]::Replace([string]$data.Adresse,'\s+',' ')).Trim()
 if($remaining.Length -gt 150){throw 'Adresse: capacite maximale 3 lignes de 50 caracteres; aucune troncature.'}
 $lines=@()
 for($slot=0;$slot -lt 3 -and $remaining.Length -gt 0;$slot++){
  $cut=[Math]::Min(50,$remaining.Length)
  if($cut -lt $remaining.Length -and [char]::IsHighSurrogate($remaining[$cut-1])){$cut--}
  if($cut -lt $remaining.Length){for($i=$cut-1;$i -ge 0;$i--){if($remaining[$i] -eq ' ' -and ($remaining.Length-$i-1) -le (2-$slot)*50){$cut=$i+1;break}}}
  $lines+=,$remaining.Substring(0,$cut);$remaining=$remaining.Substring($cut)
 }
 if($remaining){throw 'Adresse trop longue pour les lignes disponibles; aucune troncature.'}
 $data.Adresse=$lines[0];$data.Adresse2=if($lines.Count -gt 1){$lines[1]}else{''};$data.Adresse3=if($lines.Count -gt 2){$lines[2]}else{''}
}
$types=@{
 Nom=@('NVarChar',100); NomCourt=@('NVarChar',30); ICE=@('NVarChar',15)
 IF=@('NVarChar',30); RC=@('NVarChar',30); DateRegularite=@('DateTime',0)
 Adresse=@('NVarChar',100); Ville=@('NVarChar',50); Telephone=@('NVarChar',30)
 Adresse2=@('NVarChar',50); Adresse3=@('NVarChar',50)
 Fax=@('NVarChar',30); Paiement=@('NVarChar',10); Categorie=@('NVarChar',10)
 CodeComptable=@('NVarChar',10); RegimeTaxe=@('NVarChar',10); Devise=@('NVarChar',10)
 TypeMontant=@('Int',0); TypeLibelle=@('NVarChar',3); CodeModele=@('NVarChar',30); Pays=@('NVarChar',3); Statut=@('NVarChar',1)
}
foreach($name in $types.Keys){
 if($null -eq $data.PSObject.Properties[$name]){throw "Champ manquant: $name"}
 if($types[$name][1] -gt 0 -and ([string]$data.$name).Length -gt $types[$name][1]){throw "Valeur trop longue: $name"}
}
if($data.ICE -and $data.ICE -notmatch '^\d{15}$'){throw 'ICE: 15 chiffres si renseigne'}
if($data.TypeLibelle -cnotin @('HT','TTC')){throw 'TypeLibelle: HT ou TTC'}
. (Join-Path $PSScriptRoot 'SupplierSqlConnection.ps1')
$cn=New-TestSupplierSqlConnection -ConnectionString $ConnectionString -Credential $Credential
function Invoke-Plan([bool]$Execute){
 $cmd=$cn.CreateCommand()
 try {
  $cmd.CommandTimeout=60
  $cmd.CommandText=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'create_supplier.sql') -Raw -Encoding UTF8
  foreach($name in $types.Keys){
   $spec=$types[$name]
   $p=$cmd.Parameters.Add('@'+$name,[System.Data.SqlDbType]::$($spec[0]))
   if($spec[1] -gt 0){$p.Size=$spec[1]}
   $p.Value=if($name -eq 'DateRegularite'){[datetime]::ParseExact($data.$name,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)}elseif($name -eq 'TypeMontant'){[int]$data.$name}else{[string]$data.$name}
  }
  $p=$cmd.Parameters.Add('@Execute',[System.Data.SqlDbType]::Bit);$p.Value=$Execute
  $p=$cmd.Parameters.Add('@UseAddressLines',[System.Data.SqlDbType]::Bit);$p.Value=$true
  $p=$cmd.Parameters.Add('@AllowDuplicates',[System.Data.SqlDbType]::Bit);$p.Value=$false
  $p=$cmd.Parameters.Add('@ApprovedDuplicateCodes',[System.Data.SqlDbType]::NVarChar,-1);$p.Value='[]'
  $adapter=[System.Data.SqlClient.SqlDataAdapter]::new($cmd)
  try{$result=[System.Data.DataSet]::new();[void]$adapter.Fill($result)
   foreach($table in $result.Tables){$table | Select-Object * -ExcludeProperty RowError,RowState,Table,ItemArray,HasErrors}
  }finally{$adapter.Dispose()}
 }finally{$cmd.Dispose()}
}
try {
 $cn.Open()
 $permissions=@(Get-TestSupplierSqlPermissions $cn)
 if(@($permissions | Where-Object {Test-SupplierSqlPermissionMissing $_}).Count -gt 0){throw 'Droits SQL SELECT/INSERT/EXECUTE insuffisants; aucune insertion.'}
 Invoke-Plan $false
 if($Create){
  $data | ConvertTo-Json -Depth 5 | Write-Host
  Write-Host 'Le code F + 1 sera recalcule sous verrou. Cible: x3v12.TEST. Source modele: OB, lecture seule.'
  $answer=Read-Host 'Pour confirmer ces donnees et creer ce fournisseur, saisir exactement CREER TEST'
  if($answer -cne 'CREER TEST'){throw 'Creation annulee: confirmation absente'}
  Invoke-Plan $true
 }
}finally{$cn.Dispose()}
