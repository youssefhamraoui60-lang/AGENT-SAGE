# Exécution en RDP sur le serveur Sage 200

Préparé le 24/10/2026. Aucun nouvel essai WinRM/DCOM. Ce guide organise les interventions déjà définies ; il ne rejoue pas le diagnostic général.

**Limites :** les changements AIAGT/TEST sont autorisés. Les connexions/certificats actifs Syracuse et tout redémarrage attendent l’accord sur la fenêtre. Aucun save d’article n’est autorisé. Ne pas modifier la politique d’exécution PowerShell pour lancer ces scripts : faire utiliser une méthode approuvée/signature si la politique locale le demande.

## 1 — Consultation locale, sans modification Sage

### Préparer les fichiers

Depuis la VM 208, copier uniquement ces deux scripts dans un dossier d’intervention choisi sur le serveur 200 via le transfert de fichiers RDP approuvé :

- `C:\AGENT-SAGE-X3\scripts\sage_rdp_consultation.ps1`
- `C:\AGENT-SAGE-X3\scripts\sage_rdp_backup.ps1`

Les commandes ci-dessous supposent leur copie dans `C:\SageOps`. Ce dossier est un exemple de travail, pas une installation de service. S’il n’existe pas, le créer via l’Explorateur après validation de l’emplacement ; adapter le chemin si nécessaire. Les fichiers du projet restent sur 208.

Ouvrir Windows PowerShell dans votre session RDP autorisée sur **sage / 192.168.9.200**, avec les droits de consultation nécessaires. Exécuter cette ligne unique :

```powershell
& 'C:\SageOps\sage_rdp_consultation.ps1'
```

Le script vérifie qu’il s’exécute sur l’IP attendue. Il consulte le service Syracuse, ses dépendances Windows déclarées, les listeners 8124/8443/443, les connexions établies et les métadonnées des certificats Windows. Il ne lance aucune commande distante, SOAP, arrêt/redémarrage, changement de confiance ou configuration. Sans ReportPath, il n’écrit aucun rapport sur disque.

Résultats à relever : état Syracuse ; occupation et PID de 8443 ; connexion 8124 ; dépendances Windows ; état du pare-feu. **L’absence de dépendance Windows ne prouve pas l’absence de dépendance applicative.** Des connexions TCP ne donnent ni le nombre d’utilisateurs ni l’inventaire des intégrations.

### Contrôle graphique avant intervention

Dans le navigateur local du serveur, ouvrir `http://localhost:8124` avec votre compte d’administration autorisé :

1. **Hôtes / Hosts**, hôte `sage`, tableau Connections : conserver une capture/export de toutes les lignes, certificats référencés, réglages d’authentification et processus. Consulter les informations détaillées/de fonctionnement de l’hôte. **Ne pas modifier/enregistrer une connexion.**
2. **Configuration des pools SOAP classiques** : relever endpoint, utilisateur, taille, locale, tags et état de POOL_AI_TEST. Faire confirmer ses consommateurs par l’exploitation ; les canaux actuellement vides ne prouvent pas qu’il est inutilisé.
3. Relever avec l’exploitation les utilisateurs et intégrations dépendant de Syracuse : consommateur, responsable, dossier, URL, pool éventuel, interruption/reprise prévues. Utiliser son suivi des sessions et les informations d’hôte ; ne pas exporter de cookies ou d’identifiants secrets.
4. **Certificats**, entrée `sage`, puis **Certificats d’autorités** : relever références, SAN, dates, chaîne, présence de clé et erreurs signalées. Le certificat Syracuse peut exister même si LocalMachine\My est vide.

Exporter **uniquement** les parties publiques du certificat serveur et de la CA/intermédiaires, une par fichier CER/DER/PEM. Aucun PFX/P12, clé ou passphrase. Exemple de noms choisis localement : `C:\SageOps\sage-public.cer` et `C:\SageOps\ca-public.cer`.

```powershell
& 'C:\SageOps\sage_rdp_consultation.ps1' -PublicCertificate 'C:\SageOps\sage-public.cer' -PublicChain 'C:\SageOps\ca-public.cer'
```

Adapter seulement aux fichiers publics réellement exportés. Pour plusieurs intermédiaires : `-PublicChain @('C:\SageOps\intermediaire.cer','C:\SageOps\ca-public.cer')`.

Le rapport donne le **SHA-256 DER**, les extensions et une construction de chaîne avec révocation en mode cache/offline. L’ExtraStore n’accorde pas la confiance et n’installe pas de racine. Le moteur Windows peut utiliser ses magasins/caches habituels ; ce contrôle n’est pas une preuve du nom DNS, de révocation à jour ou de correspondance de clé privée. `UntrustedRoot`, `PartialChain` et `RevocationStatusUnknown` sont des résultats à traiter avec le responsable PKI, jamais des erreurs à ignorer. [ExtraStore Microsoft](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509chainpolicy.extrastore), [mode de révocation](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509chainpolicy.revocationmode).

Comparer hors bande les empreintes déjà relevées :

```text
Serveur : 8EA053B47994C560E9C094FA79635FE3A7238144148F43C9C998BD8986D03ED9
CA      : D2CA116411F5A3E6CF09AA661330CBB45E92B99B40BDEFB9E1D316E76A080F4F
Nom attendu : sage ; URL prévue https://sage:8443
```

Une différence arrête la validation ; ne pas remplacer automatiquement ces valeurs. La correspondance clé/certificat doit être confirmée localement par l’exploitation/PKI, puis par le handshake TLS après maintenance.

Pour conserver seulement le rapport public dans **un nouveau fichier** :

```powershell
& 'C:\SageOps\sage_rdp_consultation.ps1' -PublicCertificate 'C:\SageOps\sage-public.cer' -PublicChain 'C:\SageOps\ca-public.cer' -ReportPath 'C:\SageOps\consultation-avant-https.json'
```

Le fichier ne sera pas écrasé s’il existe. Vérifier le rapport avant transmission ; les adresses et comptes de service sont des informations internes. Envoyer le rapport et les seuls certificats publics, jamais les sauvegardes de configuration ou des secrets.

## 2 — Changements administratifs TEST autorisés

Appliquer depuis cette console locale la [fiche ADMIN-01](ADMIN-01-AIAGT-TEST.md), sans changement d’un dossier de production :

| Écran | Valeurs à appliquer après vérification d’absence/collision |
|---|---|
| GESAFT, dans TEST | AITST ; toutes fonctions et tous codes d’accès = Non |
| GESAFP | GESITM : consultation + C, pas M/S ; GESITF : consultation + C, site 201 seulement, pas M/S ; appliquer la mise à jour des autorisations croisées |
| GESAUS | AIAGT, actif, login AIAGT, connexion Web Services, profil AITST ; profil de menus minimal approuvé |
| Syracuse, utilisateur/groupes/rôles | AIAGT ; objets dédiés sans administration ; groupe limité à V12_TEST ; Endpoints login V12/TEST → AIAGT ; correspondances de rôles sans profil large |
| Pool | Si exclusivité confirmée : POOL_AI_TEST ; sinon pool dédié POOL_AIAGT_TEST. Endpoint V12/TEST, User AIAGT, fr-FR, initialisation/max 1, tags TEST existants |

Ne pas modifier un profil/groupe/pool partagé. La taille est par processus Web Services : valider licences/capacité avant démarrage du nouveau pool. Start/Update peut recycler ses canaux ; ne pas perturber les consommateurs du pool existant. Si l’exclusivité n’est pas démontrée, choisir le pool dédié dans le périmètre autorisé.

Conserver les captures/exports des droits effectifs sans mot de passe. Les valeurs locales du profil de menus et des tags doivent venir de l’installation, pas d’un exemple inventé. Contrôler les accès hérités aux autres endpoints/pools. Si le périmètre TEST ne peut pas être démontré, ne pas activer l’usage du compte dans l’agent.

**Recette locale avant HTTPS :** session AIAGT distincte dans le navigateur local ; lecture d’un article TEST et d’une fiche ITF/201 connus ; getDescription local dans le testeur SOAP, puis read seulement : USER=AIAGT, FOL=TEST, SOL=V12, objets ITM/ITF. Ne pas tester l’authentification AIAGT depuis 208 en HTTP réseau. Une lecture positive ne prouve pas C ; noter la création « configurée, non exercée ». Aucun save à blanc. Tests de refus et preuve de périmètre selon ADMIN-01, sans charger des fiches de production.

## Sauvegarde préalable — copies locales protégées uniquement

Avant la maintenance HTTPS, relever/exporter la configuration d’hôte et du pool avec l’exploitation ; identifier le **fichier de configuration effectif** Syracuse, par exemple nodelocal.js à son emplacement réel. Ne pas supposer un chemin d’installation ni créer ce fichier s’il est absent.

Choisir un dossier parent de sauvegarde local approuvé, hors synchronisation cloud/partage non approuvé. Le script suivant crée un **nouveau sous-dossier**, retire son héritage et limite les ACL au compte opérateur, SYSTEM et Administrateurs **avant** de copier les fichiers choisis. Il vérifie les hashes, sans modifier les sources. Il n’écrase aucun dossier existant et ne copie aucun conteneur de certificat.

Exécuter cette ligne unique et saisir les chemins réels demandés :

```powershell
$cfg=Read-Host 'Chemin du fichier de configuration effectif'; $hostExport=Read-Host 'Chemin de l export JSON de l hote'; $poolExport=Read-Host 'Chemin de l export JSON du pool'; $parent=Read-Host 'Dossier parent local de sauvegarde approuve existant'; & 'C:\SageOps\sage_rdp_backup.ps1' -ConfigurationFile @($cfg,$hostExport,$poolExport) -Destination (Join-Path $parent ('Syracuse-avant-HTTPS-'+(Get-Date -Format yyyyMMdd-HHmmss)))
```

Exporter par la fonction d’export approuvée de votre interface ; si elle n’est pas disponible, l’exploitation doit fournir sa méthode de sauvegarde supportée. Ne pas enregistrer une page HTML sous un faux JSON et ne pas improviser une requête MongoDB.

Conserver le manifest et le chemin de sauvegarde. **Cette copie n’est pas une sauvegarde MongoDB complète** : les paramètres d’administration Syracuse peuvent être stockés dans son référentiel. Faire confirmer la sauvegarde/restauration Syracuse existante et une méthode de récupération hors UI par l’exploitation **avant** d’autoriser le changement. Les fichiers peuvent contenir des secrets : ne transmettre ni les copies ni leur contenu au chat ou à l’agent.

## 3 — HTTPS : arrêt avant fenêtre autorisée

Ne pas cliquer Enregistrer/Start sur une nouvelle connexion active avant l’accord [AT-HTTPS](AT-HTTPS-8443-SAGE.md). Ne lancer aucune commande Restart-Service.

Pendant la fenêtre autorisée uniquement, appliquer [ADMIN-02](ADMIN-02-MAINTENANCE-HTTPS-SYRACUSE.md) : hôte sage, ajouter 8443 actif/SSL avec le certificat sage validé, conserver intégralement 8124. Aucun remplacement de certificat, changement de processus, pare-feu ou ACL non approuvé. Conserver toute exigence mTLS. L’enregistrement peut relancer Syracuse et interrompre les utilisateurs de tous les dossiers desservis. [Référence Sage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).

**NO-GO :** chaîne/clé/nom non validés, port occupé, sauvegarde ou récupération non confirmée, consommateur non couvert, absence de fenêtre ou absence d’opérateur habilité. Une CA non reconnue n’autorise pas un import global ni verify=False.

### Après changement

Sur 200, relancer le script de consultation sans modifier les règles : vérifier état du service, listeners 8124 et 8443, accès métier de référence et absence de régression avec l’exploitation. La présence d’un listener ne prouve pas TLS.

Sur **208**, une fois le certificat authentifié, configurer les valeurs privées localement et recharger seulement le backend agent :

```text
SAGE_SOAP_BASE_URL=https://sage:8443
SAGE_SOAP_USERNAME=AIAGT
SAGE_SOAP_PASSWORD=secret neuf saisi localement uniquement
SAGE_SOAP_POOL=alias TEST effectivement retenu
SAGE_SOAP_CA_BUNDLE=chemin du bundle public CA/intermediaires approuve si necessaire
SAGE_WRITES_ENABLED=false
```

Ne pas recopier littéralement les descriptions de valeurs dans .env. Ne pas faire confiance automatiquement à un bundle reçu sans confirmation indépendante. Le client vérifie la chaîne et le nom ; aucun repli HTTP pour écrire.

Depuis le projet sur 208, exécuter :

```powershell
Set-Location 'C:\AGENT-SAGE-X3'; & '.\backend\.venv\Scripts\python.exe' '.\scripts\verify_sage_after_rdp_maintenance.py' --article '15GR6514' --site-article 'A10/40' --expected-server-sha256 '8EA053B47994C560E9C094FA79635FE3A7238144148F43C9C998BD8986D03ED9'
```

Ces codes correspondent à des lectures existantes déjà validées ; si une fiche n’est plus disponible, faire choisir une autre fiche **connue TEST**, avec ITF sur 201. Utiliser l’empreinte ci-dessus seulement après confirmation indépendante par l’administrateur. Le script vérifie chaîne/nom, empreinte et TLS 1.2 minimum, puis les lectures AIAGT. Il teste aussi le refus FastAPI sans authentification et HTTP 423 avec un corps vide invalide, sans clé ni approbation de création. Il ne vérifie pas la révocation à jour et ne transforme pas C en droit de création exercé. Faire la recette complète ADMIN-01 et examiner les preuves de droits et PKI.

Le rapport doit afficher READ_ACCEPTANCE_PASS. FastAPI doit rester verrouillé pendant la recette (au minimum WRITES_DISABLED ; preuves éventuellement encore absentes). Après validation des preuves réelles et de l’activation technique, aucune création ne part sans l’approbation individuelle.

### Retour arrière

Si TLS, disponibilité ou périmètre échoue : arrêter la recette et garder les écritures désactivées. Si 8124/l’interface reste accessible, rétablir seulement l’export préalable ou retirer/désactiver la ligne 8443 selon la procédure opérateur autorisée ; un second rechargement peut survenir. Conserver les certificats existants et 8124.

Si l’interface est indisponible, utiliser la récupération hors UI préalablement validée avec l’exploitation/Sage. Ne pas éditer MongoDB ou restaurer tout son référentiel à l’aveugle : une restauration globale peut effacer des changements d’autres utilisateurs et dépasser l’accord initial. Aucune série de redémarrages improvisés. Rétablir les paramètres agent sauvegardés, sans remettre un secret exposé et sans autoriser d’écriture HTTP. Vérifier les accès initiaux et consigner l’horaire.

## Après les deux recettes seulement

Je pourrai préparer un article unique avec nouveau code absent, valeurs métier revues, XML et UUID/digest ; vous demanderez/accorderez une approbation **spécifique** avant un seul save FastAPI. Ensuite : statut/messages, SOAP read, SELECT SQL paramétré TEST, comparaison et affichage React. Une réponse ambiguë entraîne seulement des relectures, jamais un renvoi automatique. Aucun article-site supplémentaire n’est inclus dans cet essai unique.
