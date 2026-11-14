#requires -Version 5.1
# Reuse the approved Windows transport in the existing module's private scope.
Import-Module (Join-Path $PSScriptRoot 'SageTestSoap.psm1')
$script:Soap=Get-Module SageTestSoap

function Get-SageSiteDescription {
    & $script:Soap {
        $reply=Invoke-TestSoap getDescription '' WS_AR_SITE
        if ($reply.Status -ne 1 -or -not $reply.ResultXml) {throw 'SITE_DESCRIPTION_FAILED'}
        $doc=Read-SafeXml $reply.ResultXml
        foreach($pair in @(@('FOL','TEST'),@('SOL','V12'),@('PNA','WS_AR_SITE'),@('OBJ','ITF'))) {
            if($doc.DocumentElement.GetAttribute($pair[0]) -cne $pair[1]) {throw 'SITE_TARGET_NOT_TEST'}
        }
        return ,$doc
    }
}
function Get-SageTestArticleSite {
    param([Parameter(Mandatory)][string]$Code,[Parameter(Mandatory)][ValidateSet('201','202','209')][string]$Site)
    $null=Get-SageSiteDescription
    & $script:Soap {
        param($Code,$Site)
        Assert-Code $Code
        $keys='<objectKeys enc:arrayType="w:CAdxParamKeyValue[2]" xsi:type="enc:Array"><item><key>ITMREF</key><value>'+(Escape-Xml $Code)+'</value></item><item><key>STOFCY</key><value>'+$Site+'</value></item></objectKeys>'
        $reply=Invoke-TestSoap read $keys WS_AR_SITE
        if ($reply.Status -eq 0 -and -not $reply.ResultXml -and @($reply.Messages | Where-Object {$_.Trim() -ceq 'Fiche inexistante'}).Count -gt 0) {
            return [pscustomobject]@{Code=$Code;Site=$Site;Status=0;Exists=$false;Fields=@{};Messages=$reply.Messages}
        }
        if($reply.Status -ne 1 -or -not $reply.ResultXml) {throw 'SITE_EXISTENCE_UNKNOWN'}
        $doc=Read-SafeXml $reply.ResultXml;$fields=@{}
        foreach($node in $doc.SelectNodes('//GRP/FLD')) {$fields[$node.ParentNode.GetAttribute('ID')+'.'+$node.GetAttribute('NAME')]=$node.InnerText}
        if($fields['ITF0_1.ITMREF'] -cne $Code -or $fields['ITF0_1.STOFCY'] -cne $Site) {throw 'SITE_READ_KEY_MISMATCH'}
        [pscustomobject]@{Code=$Code;Site=$Site;Status=1;Exists=$true;Fields=$fields;Messages=$reply.Messages}
    } $Code $Site
}
function New-SageTestArticleSitePlan {
    param([Parameter(Mandatory)][ValidateSet('EXT_POUDRE')][string]$Code,
          [Parameter(Mandatory)][ValidateSet('201','202','209')][string]$Site)
    $parent=Get-SageTestArticle -Code $Code
    if(-not $parent.Exists -or $parent.Fields['ITM0_1.TCLCOD'] -cne 'NEG' -or $parent.Fields['ITM3_1.STU'] -cne 'UN') {throw 'SITE_PARENT_NOT_CONFIRMED'}
    $description=Get-SageSiteDescription
    $before=Get-SageTestArticleSite -Code $Code -Site $Site
    if($before.Exists) {return [pscustomobject]@{Code=$Code;Site=$Site;Exists=$true;Read=$before}}
    if($description.SelectNodes('//MET[@ID="CREATE"]').Count -eq 0) {throw 'SITE_CREATE_NOT_PUBLISHED'}
    & $script:Soap {
        param($Code,$Site,$Description,$Parent)
        $fields=[ordered]@{'ITF0_1.TCLCOD'='NEG';'ITF0_1.ITMREF'=$Code;'ITF0_1.STOFCY'=$Site;'ITF0_1.STU'='UN';'ITF1_1.STOMGTCOD'=$Parent.Fields['ITM2_1.STOMGTCOD']}
        $doc=[Xml.XmlDocument]::new();$param=$doc.CreateElement('PARAM');$null=$doc.AppendChild($param);$groups=@{}
        foreach($path in $fields.Keys) {
            $group,$name=$path.Split('.');$value=[string]$fields[$path]
            $meta=$Description.SelectSingleNode('/ADXDOC/ADXDATA/GRP[@NAM="'+$group+'"]/FLD[@NAM="'+$name+'"]')
            if(-not $meta -or $meta.GetAttribute('MOD') -cne 'Input') {throw 'SITE_FIELD_MAPPING_CHANGED'}
            if($meta.GetAttribute('TYP') -eq 'Char' -and $value.Length -gt [int]$meta.GetAttribute('LEN')) {throw 'SITE_FIELD_TOO_LONG'}
            if($meta.HasAttribute('MEN') -and $Description.SelectNodes('/ADXDOC/ADXMEN/MNU[@NO="'+$meta.GetAttribute('MEN')+'"]/VAL[@IND="'+$value+'"]').Count -ne 1) {throw 'SITE_MENU_VALUE_INVALID'}
            if(-not $groups.ContainsKey($group)) {$g=$doc.CreateElement('GRP');$g.SetAttribute('ID',$group);$null=$param.AppendChild($g);$groups[$group]=$g}
            $f=$doc.CreateElement('FLD');$f.SetAttribute('NAME',$name);$f.InnerText=$value;$null=$groups[$group].AppendChild($f)
        }
        [pscustomobject]@{Code=$Code;Site=$Site;Company='20';Folder='TEST';Exists=$false;Fields=$fields;
            ObjectXml=$doc.OuterXml;Digest=(Get-Hash $doc.OuterXml);DescriptionHash=(Get-DescriptionHash $Description);SaveSent=$false}
    } $Code $Site $description $parent
}
function Invoke-SageTestArticleSiteCreation {
    param([Parameter(Mandatory)]$Plan,[Parameter(Mandatory)]$Approval)
    $fresh=New-SageTestArticleSitePlan -Code $Plan.Code -Site $Plan.Site
    if($fresh.Exists) {return [pscustomobject]@{Code=$Plan.Code;Site=$Plan.Site;State='ALREADY_EXISTS';SaveAttempts=0;ReadStatus=1;ReadConfirmed=$true}}
    & $script:Soap {
        param($Plan,$Fresh,$Approval)
        $expiry=[DateTimeOffset]::Parse([string]$Approval.ExpiresAt)
        if($Approval.Approved -ne $true -or $Approval.Folder -cne 'TEST' -or $Approval.Code -cne $Fresh.Code -or
            $Approval.Site -cne $Fresh.Site -or $Approval.Digest -cne $Fresh.Digest -or
            $Approval.DescriptionHash -cne $Fresh.DescriptionHash -or $Plan.Digest -cne $Fresh.Digest -or
            $expiry -le [DateTimeOffset]::UtcNow -or $expiry -gt [DateTimeOffset]::UtcNow.AddMinutes(15) -or
            [string]$Approval.Actor -notmatch '^chat:[0-9a-f-]{36}$') {throw 'SITE_HUMAN_APPROVAL_INVALID'}
        $directory=Join-Path $script:Root 'runtime\powershell-soap-attempts';$null=New-Item -ItemType Directory -Path $directory -Force
        $marker=Join-Path $directory ($Fresh.Code+'.site-'+$Fresh.Site+'.attempt.json')
        $claim=[ordered]@{Code=$Fresh.Code;Site=$Fresh.Site;Folder='TEST';Digest=$Fresh.Digest;SaveAttempts=1;At=[DateTime]::UtcNow.ToString('o')}
        $stream=[IO.File]::Open($marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$bytes=[Text.Encoding]::UTF8.GetBytes(($claim|ConvertTo-Json));$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
        $result=[ordered]@{Code=$Fresh.Code;Site=$Fresh.Site;Folder='TEST';SaveAttempts=1;SaveStatus=$null;State='UNCERTAIN';ReadConfirmed=$false;Messages=@();RetryAllowed=$false}
        try{$reply=Invoke-TestSoap save ('<objectXml>'+(Escape-Xml $Fresh.ObjectXml)+'</objectXml>') WS_AR_SITE;$result.SaveStatus=$reply.Status;$result.Messages=$reply.Messages}catch{}
        return [pscustomobject]@{Result=$result;Marker=$marker}
    } $Plan $fresh $Approval | ForEach-Object {
        $result=$_.Result;$marker=$_.Marker
        try {
            $read=Get-SageTestArticleSite -Code $fresh.Code -Site $fresh.Site
            $result['ReadStatus']=$read.Status;$result['ReadFields']=$read.Fields
            $matches=$read.Exists
            foreach($path in $fresh.Fields.Keys){if($read.Fields[$path] -cne [string]$fresh.Fields[$path]){$matches=$false}}
            $result.ReadConfirmed=$matches
            if($result.SaveStatus -eq 1 -and $matches){$result.State='CREATED_AND_READ_BACK'}
        }catch{$result['ReadError']='READBACK_UNAVAILABLE'}
        $result|ConvertTo-Json -Depth 9|Set-Content -LiteralPath ($marker+'.result.json') -Encoding UTF8
        [pscustomobject]$result
    }
}
Export-ModuleMember -Function Get-SageTestArticleSite,New-SageTestArticleSitePlan,Invoke-SageTestArticleSiteCreation
