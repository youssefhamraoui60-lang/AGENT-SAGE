# Procédure pratique sur le serveur Sage — diagnostic uniquement

Exécuter seulement la phase A maintenant. La phase B est un projet soumis à validation des résultats et autorisation des changements. Aucun logiciel ni connecteur à redévelopper. Ne pas envoyer de save, modify ou delete.

## Audit du script existant

scripts/inspect_sage_tls_host.ps1 relu : Get-NetIPAddress, Get-CimInstance, Get-NetTCPConnection, Get-NetFirewallProfile et Get-Command, sélection/formatage et sortie JSON uniquement. Pas d’installation, Set/New/Remove de configuration, lancement/arrêt de service, accès distant, lecture de mot de passe ou de clé privée. Les variables changent uniquement dans le processus PowerShell. La propriété HasPrivateKey des commandes ci-dessous indique une présence ; elle n’exporte pas la clé.

Le script refuse l’hôte si 192.168.9.200 n’est pas une adresse locale. Sa sortie seule n’inventorie pas les règles individuelles ni les certificats : compléter avec les étapes suivantes. La syntaxe a été vérifiée sur la VM agent ; le script n’a pas été exécuté sur le serveur Sage. Il ne prouve pas la correspondance clé/certificat ni la validité complète d’une chaîne TLS.

## Phase A — commandes de lecture à exécuter maintenant

Ouvrir Windows PowerShell sur **le serveur Sage 192.168.9.200**, pas sur 192.168.9.208. Utiliser une session autorisée pour les lectures administratives si nécessaire. Aucun changement d’ExecutionPolicy, aucun Unblock-File ni désactivation de protection demandé. Si une commande est refusée, transmettre le nom de la commande et le type d’erreur, sans contourner la restriction.

### A1 — confirmer l’hôte et le système

```powershell
hostname
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
Get-NetIPAddress -AddressFamily IPv4 |
    Select-Object InterfaceAlias,IPAddress,PrefixLength
```

Attendu : une interface 192.168.9.200. Sinon arrêter : nous devons corriger la cible avant toute autre étape.

Le script existant peut être exécuté si une copie approuvée a été placée à ce chemin sur le serveur :

```powershell
Get-Content -LiteralPath 'C:\AGENT-SAGE-DIAG\inspect_sage_tls_host.ps1'
& 'C:\AGENT-SAGE-DIAG\inspect_sage_tls_host.ps1'
```

Ce chemin est proposé ; il n’a pas été créé à distance. Le script source est dans C:\AGENT-SAGE-X3\scripts sur la VM agent. L’exécution est facultative si A1–A5 sont faites manuellement. Ne pas utiliser une commande qui télécharge et exécute du code automatiquement.

### A2 — services, ports et processus Syracuse

```powershell
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -match 'syracuse|sage' -or $_.DisplayName -match 'syracuse|sage' } |
    Select-Object Name,DisplayName,State,StartMode

$sageListeners = @(Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -In 8124,8443,443,22)
$sageListeners | Select-Object LocalAddress,LocalPort,OwningProcess
$sageListeners | Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
    Select-Object Id,ProcessName,Path
```

Attendu : 8124 en écoute, souvent un processus node lié à Syracuse. La présence de node ne suffit pas à identifier sa fonction : rapprocher le chemin, le service et l’administration Syracuse. Si 8443/443 est occupé, **ne rien arrêter** et transmettre l’identification du processus. Aucune ligne de commande de processus ni configuration brute n’est demandée car elle pourrait contenir des secrets.

### A3 — HTTP local sans identifiants ni appel SOAP d’écriture

```powershell
$sageWsdlUrl = 'http://127.0.0.1:8124/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl'
try {
    $sageHttpResult = Invoke-WebRequest -Uri $sageWsdlUrl -UseBasicParsing `
        -Method Get -MaximumRedirection 0 -TimeoutSec 15
    [pscustomobject]@{
        Status = [int]$sageHttpResult.StatusCode
        ContentType = $sageHttpResult.Headers['Content-Type']
        HasWsdlDefinitions = [bool]($sageHttpResult.Content -match '<(?:[A-Za-z0-9_]+:)?definitions\b')
    }
} catch {
    if ($null -ne $_.Exception.Response) {
        [pscustomobject]@{ Status = [int]$_.Exception.Response.StatusCode; HasWsdlDefinitions = $false }
    } else {
        [pscustomobject]@{ Status = 'NO_HTTP_RESPONSE'; ErrorType = $_.Exception.GetType().Name }
    }
}
```

200 + HasWsdlDefinitions=True : WSDL local disponible. 401/403 : service HTTP atteint mais authentification requise/refusée, pas preuve de panne. 3xx : redirection à examiner, ne pas suivre vers un hôte non validé. Pas de réponse : préciser l’erreur. Ne pas ajouter de mot de passe dans la commande ; ne pas transmettre le corps de page ni les en-têtes complets.

### A4 — règles réseau Windows effectives, y compris règles larges

```powershell
Get-NetConnectionProfile | Select-Object InterfaceAlias,NetworkCategory,IPv4Connectivity
Get-NetFirewallProfile -PolicyStore ActiveStore |
    Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction

function Test-SageDiagnosticPort {
    param([object[]]$Values)
    foreach ($portSpec in $Values) {
        foreach ($part in ([string]$portSpec -split ',')) {
            $part = $part.Trim()
            if ($part -eq 'Any') { return $true }
            if ($part -match '^\d+$' -and [int]$part -in 8124,8443) { return $true }
            if ($part -match '^(\d+)-(\d+)$') {
                foreach ($target in 8124,8443) {
                    if ($target -ge [int]$Matches[1] -and $target -le [int]$Matches[2]) { return $true }
                }
            }
        }
    }
    return $false
}

$sageRuleReport = @(foreach ($rule in (Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound)) {
    $portFilters = @($rule | Get-NetFirewallPortFilter)
    $relevant = @($portFilters | Where-Object {
        [string]$_.Protocol -in 'TCP','6','Any','256' -and
        (Test-SageDiagnosticPort -Values @($_.LocalPort))
    })
    if ($relevant.Count -gt 0) {
        $addresses = $rule | Get-NetFirewallAddressFilter
        $application = $rule | Get-NetFirewallApplicationFilter
        $service = $rule | Get-NetFirewallServiceFilter
        [pscustomobject]@{
            Name = $rule.Name
            DisplayName = $rule.DisplayName
            Action = [string]$rule.Action
            Profile = [string]$rule.Profile
            Protocol = ($relevant.Protocol -join ',')
            LocalPort = ($relevant.LocalPort -join ',')
            LocalAddress = ($addresses.LocalAddress -join ',')
            RemoteAddress = ($addresses.RemoteAddress -join ',')
            Program = ($application.Program -join ',')
            Service = ($service.Service -join ',')
            PolicyStoreSourceType = [string]$rule.PolicyStoreSourceType
        }
    }
})
$sageRuleReport | ConvertTo-Json -Depth 5
```

Attendu : connaître Allow/Block, profils, programmes/services et sources pour 8124/8443, avec les règles Any/plages. Ne pas déduire un accès garanti de la seule présence d’une règle. Les politiques IPsec, les filtres applicatifs et les équipements réseau peuvent ajouter des contraintes. Les règles à ports dynamiques nommés nécessitent une revue complémentaire si présentes. Une règle Allow limitée à l’agent n’annule pas une Allow large existante. Ne rien créer, désactiver ou supprimer maintenant.

### A5 — métadonnées de certificats publics, sans exporter de clé

```powershell
Get-ChildItem -Path Cert:\LocalMachine\My |
    Select-Object Subject,Issuer,Thumbprint,NotBefore,NotAfter,HasPrivateKey,
        @{Name='DNS';Expression={($_.DnsNameList.Unicode -join ',')}},
        @{Name='EKU';Expression={($_.EnhancedKeyUsageList -join ',')}} |
    Format-List

Get-ChildItem -Path Cert:\LocalMachine\Root,Cert:\LocalMachine\CA |
    Where-Object { $_.Subject -match 'sage' -or $_.Issuer -match 'sage' } |
    Select-Object Subject,Issuer,Thumbprint,NotAfter |
    Format-List
```

Thumbprint Windows ci-dessus est normalement SHA1 ; ne pas le confondre avec les empreintes SHA256 des diagnostics antérieurs. SAN attendu : nom exact utilisé dans l’URL. OID EKU serveur TLS : 1.3.6.1.5.5.7.3.1. Aucun EKU affiché ne suffit pas à conclure automatiquement à une incompatibilité. HasPrivateKey=True ne prouve ni l’accès du futur compte relais ni la correspondance effective clé/certificat.

Les certificats internes Syracuse peuvent être stockés hors du magasin Windows. Une liste vide ne prouve pas leur absence. Dans l’administration Syracuse, consulter seulement les pages **Hôtes** et **Certificats** : hôte sage, connexions/ports SSL, certificat affecté, SAN/dates/émetteur/empreinte publique du certificat sage et de la CA. Ne pas cliquer sur sauvegarder, importer/exporter une clé ou modifier une connexion. Ne pas ouvrir ni transmettre nodelocal.js, .env, fichiers PEM contenant PRIVATE KEY ou PFX/P12.

### A6 — informations métier à consulter sans changement

Dans l’administration Sage, relever le compte HTTP/Syracuse et l’utilisateur X3 **effectif** associé à POOL_AI_TEST, solution V12, dossier TEST, état des canaux, éventuels autres consommateurs. Aucun mot de passe. Consulter les profils/restrictions existants pour savoir si un compte technique TEST dédié existe déjà ; ne pas en créer maintenant.

Relever les droits effectifs pour GESITM/ITM, GESBPS/BPS et GESITF/ITF, lecture/création/modification séparées, société/site 201, codes d’accès et limitations dossier. Relever les mappings WS_ARTICLE/WS_FOURNIS/WS_AR_SITE, catégories/numérotation/champs conditionnels. La présence de CREATE dans getDescription ne remplace pas ces droits.

### A7 — résultats à transmettre et arrêt

Copier ici des blocs texte A1–A5 et les observations A6, après relecture. Si c’est trop long, enregistrer volontairement les sorties dans un fichier texte privé puis transmettre le contenu utile. Cette écriture de rapport est facultative ; les commandes ci-dessus ne créent aucun fichier.

Transmettre : version Windows, écoute/PID/chemin exécutable, statut HTTP et ContentType uniquement, règles pertinentes, métadonnées publiques des certificats, observations des droits/pool. Les noms DNS, IP privées et empreintes sont nécessaires au diagnostic ; masquer les informations sans rapport avec ce projet.

Ne transmettre ni mot de passe, clé privée, token local, cookie, en-tête Authorization, ligne de commande contenant un secret, ni fichier complet de configuration. Pour les captures, masquer les champs secrets. Un refus d’accès est un résultat à transmettre ; ne pas contourner les protections.

**S’arrêter ici et attendre mon analyse. Aucune installation ou modification n’est nécessaire pour cette phase.**

## Phase B — projet de mise en place, À NE PAS EXÉCUTER MAINTENANT

1. Après inventaire, faire approuver le paquet stunnel compatible avec le système, vérifier authenticité/version et préparer son emplacement isolé sur le serveur Sage. Aucun remplacement du service Syracuse ni utilisation d’un composant déjà partagé sans revue.
2. Faire approuver puis fournir un certificat dédié au relais, SAN sage ou FQDN approuvé, clé conservée sur le serveur et ACL minimales pour un compte système dédié. Confirmer la CA hors bande ; vérifier chaîne, validité et correspondance de la clé. Ne pas réutiliser/exporter automatiquement la clé Syracuse.
3. Faire approuver la règle limitée 192.168.9.208 → 192.168.9.200:8443 après examen des règles larges. Si l’isolation ne peut être obtenue sans modifier une règle partagée, nouvelle décision préalable.
4. Utiliser le modèle config/stunnel-sage-test.NOT-APPLIED.conf : TLS entrant 192.168.9.200:8443, amont 127.0.0.1:8124 uniquement, TLS 1.2/1.3, logs sans corps SOAP ni authentification. Valider le comportement du binaire retenu ; ne pas supposer l’existence d’une commande de test de configuration sans démarrage.
5. Lancer le seul processus pilote identifié après approbation. Ne pas installer de service automatique dans ce premier essai, ni redémarrer Syracuse. Surveiller sa disponibilité avant/pendant/après. Si le nom Host, les redirections ou Syracuse exigent un changement, arrêter et soumettre ce changement séparément.
6. Vérifier handshake TLS avec nom et chaîne, WSDL, puis getDescription/read via HTTPS. Aucun verify=False, -k ou repli HTTP automatique pour écrire. Conserver SAGE_WRITES_ENABLED=false.

Le relais ne filtre pas les méthodes ni les dossiers : le compte technique et les contrôles FastAPI assurent indépendamment TEST et l’approbation. Le segment HTTP restant est exclusivement loopback sur le serveur Sage.

### Compte technique TEST — procédure future sous responsabilité de l’administrateur Sage

1. Identifier la correspondance authentification Syracuse / utilisateur X3 du pool et vérifier si une identité dédiée exploitable existe déjà. Ne pas confondre compte système du relais et compte Sage métier.
2. Après accord, créer des identités dédiées non administrateur, noms compatibles avec les limites locales (exemples SVC_AI_TEST et AI_TEST à valider). Secrets générés et conservés localement, pas dans ce document. Renouveler les secrets exposés avec inventaire des consommateurs, sans changer aveuglément admin partagé.
3. Créer un profil spécifique sans copier les droits admin, limité au dossier TEST et aux fonctions nécessaires. Vérifier GESAUS/GESAFT/GESAFP ou écrans équivalents de l’installation : GESITM/ITM, GESBPS/BPS, GESITF/ITF. Séparer lecture, création et modification ; refuser suppression. Accorder seulement les dépendances de lecture réellement nécessaires, sans traitements génériques non examinés.
4. Restreindre l’accès Syracuse aux endpoints/rôles nécessaires et contrôler l’usage des pools. Un endpoint SOAP générique reçoit un alias de pool : limiter l’URL seule ne garantit pas TEST. Examiner les profils et tous les chemins d’accès du compte, sans tentative d’écriture hors TEST.
5. Vérifier société/site 201 et codes d’accès, catégorie NEG/numérotation manuelle/unités SAC/coefficient/comptabilité pour ITM, catégorie/pays/adresse/obligations BPS, règles et défauts ITF. Stocker les preuves datées sans secrets.
6. Affecter ce compte à POOL_AI_TEST uniquement après inventaire et accord : le recyclage de canaux peut interrompre ce pool. S’il est partagé, proposer un pool TEST séparé après accord, sans modifier l’existant. Refaire alors configuration agent, empreintes et préparations pour le nouvel alias.
7. Valider les lectures HTTPS avec l’identité technique et vérifier l’utilisateur X3 réel dans les descriptions. Vérifier les trois couples publication/objet et TEST/V12. Droits publiés et lectures réussies ne prouvent pas à eux seuls la création autorisée : joindre la revue de profils.
8. Configurer les secrets/bundle CA/preuves uniquement dans l’agent après accord, recharger le seul backend local, conserver les écritures désactivées. Une activation technique ultérieure autorisée ne vaudra jamais approbation de création.

### Risques et retour arrière

| Changement futur | Risque | Retour arrière ciblé |
|---|---|---|
| Relais indépendant | Logiciel supplémentaire, ressources, nouvelle écoute ; compatibilité à confirmer | Arrêter le seul PID/chemin du pilote, jamais tous les stunnel ; ne pas toucher Syracuse |
| Certificat/clé/CA | Mauvais nom, confiance injustifiée, clé exposée | Retirer l’affectation du seul relais et restaurer le bundle client précédent ; pas de révocation d’une CA partagée |
| Nouvelle règle réseau | Exposition trop large, conflit de règles/GPO | Retirer seulement la règle nouvelle identifiée ; ne pas supprimer les règles existantes |
| Identités/profil/pool | Droits trop larges, interruption des consommateurs du pool | Désactiver les nouvelles identités/pool dédié après revue ; rétablir l’association précédente seulement si autorisé, sans réintroduire un secret exposé |
| Configuration agent | Erreur TLS, arrêt momentané de FastAPI | Restaurer sa configuration privée sauvegardée et garder les écritures désactivées ; aucun rollback métier automatique |

Les changements de connexions actives/certificats natifs Syracuse peuvent provoquer un redémarrage : ils ne sont pas inclus dans ce scénario de relais indépendant. [Documentation Sage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html). Le relais est fondé sur le [manuel officiel stunnel](https://www.stunnel.org/manual.html). Les règles effectives sont consultées avec [Get-NetFirewallRule / ActiveStore](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule?view=windowsserver2025-ps).

## Phase C — tests métier après accords séparés

Après validation technique, recontrôler doublons et champs, puis demander un accord spécifique pour TAI261017948E et un autre pour TB261017948E. React → FastAPI → une seule tentative SOAP save → read comparé → React/historique PostgreSQL.

Après création ITM, lire TAI261017948E / 201 : si Sage l’a créé automatiquement, afficher et comparer sans save supplémentaire ; sinon préparer sa création et demander un troisième accord. Toute modification de désignation/nom court/classe ABC exige ensuite un nouvel avant/après et une nouvelle approbation. Pas de retry automatique si résultat ambigu.

Vérification finale dans TEST : GESITM (TAI261017948E), GESBPS (TB261017948E), GESITF (TAI261017948E / 201). Aucune fiche ni statut de succès n’est présumé avant ces opérations réellement exécutées et confirmées.
