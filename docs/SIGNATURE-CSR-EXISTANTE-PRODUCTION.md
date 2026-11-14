# Signature de la CSR existante et installation Syracuse 8443

Préparation du 25 octobre 2026, VM 208. **Demande non soumise et aucun certificat émis.** Le pool POOL_AI_TEST avec AIAGT dans V12/TEST est confirmé par l'utilisateur ; ce constat n'a pas été revérifié par SOAP, toujours bloqué par TLS. Aucun changement du pool proposé.

## Seuls éléments encore requis pour soumettre à la PKI

1. Copier depuis la session RDP autorisée de 200 **seulement** `C:\Sage\HTTPS-NEW\sage-https.req` vers `C:\AGENT-SAGE-X3\certs\incoming-production\sage-https.req` sur 208. C'est un fichier public ; ne pas copier la clé machine, .key, .pfx, mot de passe ou sauvegarde privée.
2. Faire confirmer par l'administrateur l'empreinte **du fichier CSR original** sur 200, par canal indépendant. La commande de lecture unique est :

```powershell
Get-FileHash -LiteralPath 'C:\Sage\HTTPS-NEW\sage-https.req' -Algorithm SHA256
```

3. Obtenir le nom de l'autorité approuvée, sa chaîne publique et son empreinte racine DER confirmée, le portail/contact réel de soumission, la référence d'approbation et les URLs CRL/AIA exploitées. Une PKI indépendante de l'AD convient. Aucune URL, modèle AD CS, autorité ou preuve d'approbation n'est inventé. Ne pas demander une nouvelle CSR si celle-ci est valide.

**À ce stade, aucun accès OS distant ni installation supplémentaire sur 200 n'est nécessaire.** Après réception, l'agent fera les validations et la soumission via la procédure réellement autorisée du fournisseur ; aucune transmission à un prestataire arbitraire.

## Dossier préparé sur 208

- config/pki/production-certificate-request.json : profil demandé, CSR existante, décisions encore manquantes, confirmation utilisateur du pool ; aucun secret.
- scripts/pki/verify_received_production_csr.py : signature PKCS#10, empreinte source, CN/SAN sage, RSA >=3072 et signature SHA256. Accepte PEM ou DER. Une politique plus forte différente est examinée par la PKI, jamais convertie silencieusement.
- scripts/pki/stage_approved_tls_material.py : vérifie les fichiers publics retournés, l'approbation déclarée, les empreintes authentifiées, les signatures de CRL, la chaîne stricte/nom/usages/révocation et **la correspondance de clé publique certificat/CSR**. Ne crée pas de clé, n'installe aucune racine et ne modifie pas .env.
- certs/incoming-production : réception des seuls éléments publics. Les bundles candidats sont versionnés sous certs/approved-production après validation ; aucune version n'est activée automatiquement.

Commande exécutée par l'agent après réception du fichier et du vrai hash :

```powershell
& 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' 'C:\AGENT-SAGE-X3\scripts\pki\verify_received_production_csr.py' --csr 'C:\AGENT-SAGE-X3\certs\incoming-production\sage-https.req' --expected-file-sha256 EMPREINTE_FICHIER_CONFIRMEE_SUR_200
```

La valeur en majuscules est un paramètre à renseigner avec le vrai hash, pas une empreinte fictive à accepter. Si CSR DER, conserver l'original et son hash ; normaliser une copie publique PEM avec OpenSSL pour les contrôles ultérieurs. Aucun nouveau matériel de clé.

## Profil à transmettre à la PKI

Certificat TLS serveur pour **Syracuse sage:8443**, clé déjà générée sur 200, sujet CN=sage, SAN DNS:sage, Basic Constraints CA:FALSE, KU digitalSignature/keyEncipherment pour RSA, EKU serverAuth, SKI feuille, AKI lié au SKI émetteur, signature SHA256 ou plus forte approuvée. CA avec SKI/contraintes et usages conformes ; chaîne complète et dates cohérentes. Durée souhaitée 365 jours à approuver, limitée par l'émetteur.

Exiger CDP de CRL signées et, selon la hiérarchie, AIA/caIssuers réels, publication indépendante de Syracuse, fraîcheur et supervision. Pas d'URL localhost, pas de réutilisation de sagex3 défectueuse sans correction approuvée, pas de PKI TEST ONLY. Une autorité publique peut refuser le nom court sage ; ne pas inventer un FQDN ni modifier le DNS pour contourner ce refus. L'administrateur doit choisir une PKI interne approuvée ou une évolution de nom explicitement autorisée.

## Fichiers publics exacts à obtenir au retour

Les noms ci-dessous sont des **noms de livraison convenus**, pas des fichiers prétendument déjà reçus.

| Fichier | Contenu / usage |
|---|---|
| sage-issued.pem | Certificat serveur final PEM, signé pour la clé de la CSR existante |
| issuing-ca.pem | Certificat public PEM de l'autorité signant la feuille |
| intermediate-N.pem, si nécessaire | Tous les autres intermédiaires, dans l'ordre de chaîne |
| root-ca.pem | Racine publique PEM authentifiée et explicitement approuvée |
| issuing-ca.crl.pem | CRL signée actuelle de l'émetteur, couvrant la feuille |
| root-ca.crl.pem, si émettrice sous racine | CRL racine couvrant l'émettrice ; autres CRL pour chaque émetteur supplémentaire si chaîne plus longue |
| crl-N.pem, si nécessaire | CRL nécessaires aux autres niveaux non racine |
| pki-delivery.json ou attestation | Référence d'approbation, empreintes DER des certificats et hashes des fichiers, URLs CDP/AIA, dates/nextUpdate, responsable et fréquence de publication |

Si l'autorité livre DER/CER ou PKCS#7 publics, l'agent normalisera des copies PEM sans clé privée. Les CRL peuvent être livrées en DER puis converties en PEM. Le script de staging actuel couvre **racine + une émettrice** ; pour une chaîne plus longue ou une signature directe par racine, adapter le contrôleur à la chaîne réellement fournie avant activation, sans modifier la hiérarchie du fournisseur pour convenir à l'outil.

**Aucune clé privée ne doit être fournie à 208.** La clé correspondante existe sur 200 ; une nouvelle clé retournerait inutilement au début du processus.

## Opérations exactes nécessaires sur 200 après signature

1. Vérifier avec l'administrateur la réception publique, la signature, la chaîne et la correspondance à la demande existante. Si voie certreq : depuis le répertoire de réception autorisé, accepter le certificat signé sous l'identité/contexte machine d'origine :

```powershell
certreq.exe -accept -machine .\sage-issued.cer
```

Le nom doit être celui du fichier réel reçu. L'acceptation associe certificat et clé ; elle ne configure pas Syracuse. Si le certificat final est PEM, certreq accepte généralement son encodage base64 ; l'administrateur doit vérifier le format de réponse réel plutôt que renommer un conteneur privé en .cer.

2. Conserver la clé sur 200. Syracuse requiert le **certificat PEM**, la **clé privée correspondante** et sa phrase secrète, avec les références CA associées. Si la clé est dans le magasin machine Windows, exporter uniquement selon la politique approuvée vers un PFX **chiffré**, puis convertir sur le périmètre d'exploitation avec outil approuvé vers PEM **chiffré**. Saisie sécurisée des phrases secrètes, jamais dans une commande, .env, chat ou journal ; aucun -nodes/-noenc. Si la clé existante n'est pas exportable, arrêter et résoudre avec l'administrateur la compatibilité du stockage Syracuse : ne pas générer automatiquement une nouvelle CSR.

3. Après contrôle de la sauvegarde privée et approbation du créneau : Administration → Certificats → Certificats des autorités de certification, ajouter les nouveaux objets CA approuvés sans remplacer les objets internes. Administration → Certificats → Certificats, créer le nouvel objet non interne `sage_https_pki` si le nom est libre ; Hôte/Server=sage ; importer sage-issued.pem, la clé correspondante chiffrée, saisir sa phrase secrète dans le champ protégé et associer la chaîne CA exacte.

4. Pendant la fenêtre autorisée uniquement : Administration → Serveurs → Hôtes → sage → Connexions ; sur **la ligne 8443 existante**, remplacer seulement la référence certificat serveur par le nouvel objet. Conserver 8124, paramètres SSL/Active, authentification client et certificats internes. Ne pas désactiver mTLS si déjà imposé. L'enregistrement peut redémarrer/recharger Syracuse et affecter les utilisateurs : aucun changement hors créneau approuvé.

5. Vérifier les accès historiques avec l'exploitation. Transmettre à 208 seulement les éléments publics et leur attestation. L'agent contrôlera la chaîne stricte et la révocation, préparera les bundles CA/CRL et les activera seulement après validation de confiance ; ensuite préflight HTTPS sans authentification, puis recette AIAGT/getDescription/read/query. **Les CRL doivent être effectivement publiées et actualisées** : la présence d'une URL dans un certificat ne suffit pas. Le pool est confirmé opérationnel par l'utilisateur ; vérifier son identité effective dans getDescription après TLS, sans le reconfigurer arbitrairement.

6. En cas de régression dans la fenêtre, réaffecter uniquement 8443 à sa référence et paramètres sauvegardés, avec le rechargement couvert par l'accord. Préserver anciens certificats et 8124. Si l'interface est indisponible, utiliser le retour arrière d'exploitation prévalidé ; aucune édition MongoDB improvisée. Le retour à l'ancien certificat ne le rend pas conforme : l'agent reste bloqué, aucun repli HTTP pour écrire.

## État actuel et condition de sortie

CSR signalée sur 200 mais **non reçue sur 208** ; autorité/approbation/URLs de production non fournies ; aucune soumission possible à une autorité déterminée. La seule action de transfert nécessaire maintenant est la CSR **publique et son hash**, avec les coordonnées de la PKI approuvée. Aucun nouvel accès administrateur distant général n'est indispensable.

SAGE_WRITES_ENABLED=false ; HTTP 423 conservé. Aucun SOAP save autorisé ou exécuté. Cette préparation ne déclare pas HTTPS corrigé.
