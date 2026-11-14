# Décisions bloquantes et installation du certificat existant sur VM 200

25 octobre 2026. CSR reçue et validée ; ne pas la régénérer. Aucun diagnostic supplémentaire, clé de production, certificat, autorité ou changement sur 200 effectué pendant cette préparation. Les profils et scripts de signature restent ceux déjà préparés, conditionnés aux paramètres PKI réels.

## Décisions à fournir avant émission

1. **Garde des clés CA** : administrateur responsable, équipement racine hors ligne/HSM et emplacement de l'émettrice, personnes autorisées, double contrôle si retenu, sauvegardes chiffrées et restauration. Aucune clé CA définitive sur 208 tant que sa garde n'est pas approuvée ; aucune CA TEST ONLY réutilisée. La clé serveur existante reste sur 200.
2. **Approbation de l'autorité privée** : noms de la nouvelle racine/émettrice, référence d'accord organisationnel, durées et politique d'émission/renouvellement. Une nouvelle racine privée n'est pas approuvée par le seul fait qu'elle signe un certificat. Les empreintes finales devront être authentifiées indépendamment avant distribution de confiance.
3. **CRL permanentes** : hôte HTTP existant approuvé et indépendant de Syracuse, URLs exactes CRL racine/émettrice et certificats CA, responsable de publication, disponibilité pour 208, calendrier avant nextUpdate, supervision et traitement des échecs. Pas de localhost de laboratoire, d'URL fictive ou de service temporaire. Aucune ouverture de port ni création de service implicitement autorisée.
4. **Maintenance Syracuse** : date/créneau Europe/Paris, opérateur, sauvegarde récupérable et retour arrière. L'affectation d'un certificat à une connexion active peut recharger/redémarrer Syracuse. La présente demande n'autorise pas ce changement actif.

Décisions consignables dans config/pki/production-governance.pending.json et production-publication.pending.json. Les champs restent null tant qu'aucun accord n'est fourni ; aucune émission avant leur validation. Pas de nouvel accès distant général nécessaire.

## Signature préparée hors de la VM 200

Entrée publique déjà disponible sur 208 : certs/incoming-production/sage-https.req, SHA256 fichier **62BB1D812991FE0CD0DB18E2541633F19F12557FFCC0CAEF2615B93E9C1CC3FC**. La signature réutilisera exactement cette CSR et sa clé publique. La clé privée serveur n'est pas transmise au signataire.

Les profils config/pki/ca-extension-profiles.cnf et issuer-openssl.cnf imposent AKI/SKI, SAN sage, EKU serverAuth, contraintes CA, KU adaptés et CRL ; les variables de publication ne pourront être renseignées qu'avec les URLs approuvées. Invoke-ApprovedIssuer.ps1 nécessite une CA effectivement provisionnée dans son environnement approuvé et bloque vm7/sage. Ce garde-fou reste en place ; il ne faut pas changer le nom de machine ou réutiliser le laboratoire pour le contourner. Si une garde de production sur 208 est explicitement choisie, il faudra une procédure nouvelle revue dans ce périmètre, pas un détournement de ce script.

Livraison publique attendue : **sage-issued.pem**, **issuing-ca.pem**, **root-ca.pem**, intermédiaires supplémentaires si présents, **issuing-ca.crl.pem**, **root-ca.crl.pem** et toute autre CRL de la chaîne, avec attestation/empreintes DER et URLs. La feuille doit correspondre à la CSR, contenir DNS:sage, CA:FALSE, serverAuth, SKI et AKI cohérent. Aucun de ces fichiers n'est prétendu émis à ce jour.

## Interventions exactes sur VM 200 après émission approuvée

### A. Rattacher la réponse à la clé existante

Placer les fichiers publics reçus dans le stockage d'exploitation protégé, par exemple le dossier existant `C:\Sage\HTTPS-NEW`. Les noms ci-dessous désignent les vrais fichiers livrés, sans certificat de test. Sous le contexte machine ayant créé la CSR :

```powershell
Set-Location -LiteralPath 'C:\Sage\HTTPS-NEW'
certreq.exe -accept -machine '.\sage-issued.pem'
if ($LASTEXITCODE -ne 0) { throw 'Acceptation échouée : arrêter, ne pas créer une nouvelle clé.' }
```

Cela accepte la réponse publique et la lie à la clé, sans modifier Syracuse. Vérifier avec l'administrateur la correspondance et la présence de clé. Ne pas accepter un conteneur privé mal identifié comme certificat public.

### B. Préparer le format PEM chiffré requis par Syracuse

Si la clé est déjà en PEM chiffré compatible, ne pas l'exporter de nouveau. Sinon, après accord d'exportabilité, sélectionner le certificat accepté par son **empreinte Windows SHA-1 exacte**, confirmée à l'étape A (distincte des SHA-256 DER de confiance) :

```powershell
$empreinteWindows = Read-Host 'Empreinte Windows exacte du nouveau certificat accepté'
if ($empreinteWindows -notmatch '^[0-9A-Fa-f]{40}$') { throw 'Empreinte Windows invalide' }
$certificat = Get-Item -LiteralPath ('Cert:\LocalMachine\My\' + $empreinteWindows)
if (-not $certificat.HasPrivateKey) { throw 'Clé correspondante absente : arrêter' }
$pfx = 'C:\Sage\HTTPS-NEW\sage-https-production.pfx'
if (Test-Path -LiteralPath $pfx) { throw 'PFX existant : ne pas écraser' }
$protectionPfx = Read-Host 'Phrase secrète de transfert PFX' -AsSecureString
Export-PfxCertificate -Cert $certificat -FilePath $pfx -Password $protectionPfx -ChainOption EndEntityCertOnly | Out-Null
$protectionPfx.Dispose()
```

Le répertoire et l'export doivent être réservés aux opérateurs autorisés. Si la clé n'est pas exportable, **arrêter** et faire résoudre la compatibilité avec la garde approuvée ; aucune nouvelle clé/CSR automatiquement.

Pour la conversion, uniquement avec un OpenSSL **approuvé disponible dans le périmètre de 200**, sans installation ou téléchargement implicite :

```powershell
$opensslApprouve = Read-Host 'Chemin absolu de openssl.exe approuvé sur ce serveur'
if (-not (Test-Path -LiteralPath $opensslApprouve -PathType Leaf)) { throw 'Outil approuvé absent' }
if (Test-Path -LiteralPath '.\sage-https-production.key.pem') { throw 'Fichier clé existant : ne pas écraser' }
& $opensslApprouve pkcs12 -in '.\sage-https-production.pfx' -nocerts -out '.\sage-https-production.key.pem'
if ($LASTEXITCODE -ne 0) { throw 'Conversion échouée : arrêter' }
```

OpenSSL demande les phrases secrètes interactivement. **Ne jamais ajouter -nodes/-noenc ni -passin pass:...**. Si cet outil n'est pas disponible sur 200, faire approuver son utilisation portable/conversion dans le périmètre d'exploitation ; ne pas déplacer la clé vers 208. L'existence d'OpenSSL sur 208 ne vaut pas disponibilité sur 200.

### C. Importer un nouvel objet, sans toucher aux certificats internes

Dans Syracuse :

1. Administration → Certificats → Certificats des autorités de certification : ajouter uniquement les nouveaux certificats CA publics approuvés. Ne pas remplacer sagex3 ou les objets internes.
2. Administration → Certificats → Certificats : nouvel objet **non interne**, nom `sage_https_pki` si libre, Server/Hôte=`sage`. Importer `sage-issued.pem`, associer la clé PEM chiffrée correspondante, saisir sa phrase secrète uniquement dans le champ protégé et associer les CA exactes.
3. Pendant la fenêtre autorisée : Administration → Serveurs → Hôtes → sage → Connexions ; sur **la ligne 8443 existante**, remplacer seulement la référence du certificat serveur par le nouvel objet. Préserver 8124, Active/SSL, authentification client, pools et certificats internes. Ne pas enregistrer hors fenêtre : rechargement/redémarrage possible.

### D. Recette et retour arrière

L'exploitation vérifie les accès Sage existants. Fournir à 208 uniquement feuille/chaîne/CRL publiques et attestations : l'agent effectuera les contrôles stricts et de révocation, puis getDescription/read/query sous AIAGT. Aucun SAVE pendant cette recette ; HTTP 423 reste actif.

Si régression ou certificat refusé : réaffecter seulement 8443 à son ancienne référence et aux paramètres sauvegardés, avec le rechargement couvert par l'accord. Ne pas supprimer les anciens certificats, ni modifier 8124, SQL Server ou le runtime. Si l'interface est indisponible, employer la récupération d'exploitation prévalidée, pas une édition MongoDB improvisée. La clé PFX de transfert doit rester protégée puis être éliminée selon la procédure de garde ; aucune suppression automatique effectuée par l'agent.
