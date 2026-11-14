# Installation TLS 8443 — procédure soumise à autorisation

**Aucun changement appliqué.** Les commandes d’installation, de démarrage et de configuration décrites ici sont à exécuter seulement après autorisation spécifique. Aucun save, modify ou delete inclus. Les connecteurs, FastAPI et React restent ceux déjà développés.

## 1. État retenu et choix technique

Constats **fournis par l’utilisateur depuis le serveur** : Windows Server 2025, hôte sage/192.168.9.200 ; service Sage_Syracuse_-_NODE0 Running/Auto ; node PID 3536 sur 8124 au moment du contrôle ; 8443 et 443 sans écoute ; profil réseau Public ; pare-feu Windows désactivé sur les trois profils ; magasin LocalMachine/My vide. Le chemin du processus n’était pas visible. Certificat sage présent dans le stockage Syracuse, et parties publiques récupérées par l’agent. Ce sont des instantanés, pas une garantie de disponibilité future de 8443.

**Une règle Windows Allow n’a aucun effet de restriction tant que le pare-feu est désactivé.** Ne pas réactiver le pare-feu globalement pour ce pilote : cela exigerait l’inventaire des flux de production et une autre autorisation.

Le modèle stunnel initial chiffre le transport mais ne fournit pas à lui seul une ACL source Windows démontrée. Ne pas présumer que hosts.allow/hosts.deny Unix filtrent Windows. Deux solutions sont distinguées :

| Solution | Garantie | Validation requise |
|---|---|---|
| Relais HTTPS Caddy avec remote_ip 192.168.9.208/32 | Seules les requêtes HTTP issues de cette IP, aux chemins/méthodes admis, atteignent Syracuse ; autres requêtes rejetées sans amont | Configuration candidate + essais positifs/négatifs réels après accord |
| Filtrage réseau/vNIC/hyperviseur effectif | Seule l’IP agent peut établir TCP vers 8443 | Administrateur réseau/Sangfor : vérifier la fonction disponible et son application aux flux du même sous-réseau ; essai depuis un autre hôte |

**Le filtrage HTTP n’est pas un pare-feu TCP** : avec Caddy seul, une autre machine peut ouvrir TCP et négocier TLS avant son refus HTTP. Si l’exigence est « aucune connexion TCP hors agent », le filtre réseau est obligatoire avant lancement. Un pare-feu de passerelle peut être contourné par le trafic direct du même sous-réseau ; ne pas le déclarer effectif sans preuve. Je n’ai pas accès à la politique Sangfor pour confirmer son existence.

Proposition : Caddy isolé pour défense applicative, plus restriction réseau effective lorsque l’exigence TCP est retenue. Choix de Caddy limité au nouveau relais, aucun changement des applications existantes. La documentation définit remote_ip comme l’adresse du pair réseau ; aucun trusted_proxies ni PROXY protocol n’est configuré, un X-Forwarded-For envoyé par le client ne devient donc pas une autorisation. [Source Caddy](https://caddyserver.com/docs/caddyfile/matchers#remote-ip).

## 2. Changements exacts proposés

- Sur **sage** : ajouter uniquement un répertoire pilote `C:\AGENT-SAGE-TLS`, un binaire Caddy officiel vérifié et une configuration indépendante. Utiliser un compte système non administrateur dédié pour son exécution, sans droit Sage métier. Aucun nouveau service automatique dans le premier essai.
- Ajouter une écoute **IPv4 192.168.9.200:8443**, TLS 1.2/1.3, vers **127.0.0.1:8124** exclusivement. Pas d’écoute 80/443, pas d’ACME ni création de CA automatique, pas d’HTTP/3/UDP ou API d’administration Caddy.
- Autoriser seulement l’IP source **192.168.9.208**, GET du chemin WSDL et POST du chemin SOAP existants. Tous les autres accès HTTP refusés. Aucun routage vers l’administration Syracuse.
- Ne pas ajouter de retries au proxy ; un seul amont, `lb_retries 0`, `lb_try_duration 0s`. Garder la protection anti-rejeu FastAPI. [Source proxy Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
- Aucun changement du listener Syracuse 8124, service Syracuse, SQL Server, MongoDB, runtime Sage ou pare-feu Windows. L’accès HTTP 8124 existant n’est pas fermé dans ce pilote : sa sécurité globale relève d’un autre chantier approuvé.

Configuration prête à examiner : [Caddyfile-sage-test.NOT-APPLIED](../config/Caddyfile-sage-test.NOT-APPLIED). **Non exécutée et non validée avec un binaire Caddy dans cet environnement.** Elle doit être validée avec la version choisie et les fichiers certificat réels avant démarrage. Le modèle stunnel antérieur reste historique et ne doit pas être lancé en parallèle sur 8443.

## 3. Certificat vérifié

Préférer un **nouveau certificat dédié** signé par l’autorité interne approuvée : SAN DNS sage (ou FQDN approuvé, à modifier explicitement dans URL et modèle), usage serveur TLS, clé conservée exclusivement sur sage. L’administrateur choisit la durée et l’algorithme selon la politique locale. Ne pas générer une CA de confiance automatique ni demander une clé privée dans le chat.

Le certificat existant sage couvre le DNS sage mais pas l’IP 192.168.9.200 ni automatiquement sage.local. Il n’est pas dans LocalMachine/My et sa clé n’a pas été examinée. Sa réutilisation n’est autorisable qu’après vérification locale de la correspondance clé/certificat, droits d’usage et absence d’effet sur Syracuse. **Aucun export de cette clé n’est proposé par défaut.**

Fichiers proposés côté sage : `private/server-chain.pem` (certificat serveur puis intermédiaires requis) et `private/server-key.pem` (clé). ACL : lecture pour le compte relais et administrateurs autorisés, pas Users/Everyone ; compte relais sans droit d’écriture sur le binaire/configuration. Journaux dans un répertoire distinct avec droit d’écriture limité. Ne pas modifier les ACL des répertoires Syracuse.

L’administrateur doit comparer les empreintes par un canal indépendant, contrôler SAN, dates, usages, chaîne, politique de révocation et correspondance de la clé (preuve par clé publique, pas par export transmis). La CA a été récupérée par HTTP dans les diagnostics : cela ne constitue pas une preuve d’authenticité. Le bundle approuvé destiné à l’agent contient seulement les CA publiques. Il sera utilisé uniquement par `SAGE_SOAP_CA_BUNDLE`, sans import global Windows et sans verify=False. [TLS Caddy](https://caddyserver.com/docs/caddyfile/directives/tls).

## 4. Filtrage réseau à soumettre à l’administrateur

Objet exact : IPv4/TCP, destination vNIC/hôte **192.168.9.200**, port **8443** ; source autorisée **192.168.9.208/32** ; refus des autres sources pour **ce seul nouveau port** ; conserver les autres flux. Politique stateful si disponible. Aucun changement global de défaut ou de règle partagée sans nouvelle revue. IPv6 : le relais ne doit pas écouter sur une adresse IPv6.

L’administrateur doit fournir l’export ou la capture de la règle effective, sa portée/ordre et son point d’application. Vérifier le fonctionnement entre deux VM du même réseau, l’absence de NAT masquant les clients sous l’IP agent et l’absence de proxy intermédiaire. Un tiers utilisant l’IP de l’agent par NAT ne serait pas distingué par remote_ip : ne pas élargir l’allowlist pour faire passer le test. Si le réseau ne permet aucune ACL effective, présenter cette limite et demander une décision sur une protection additionnelle telle que mTLS ; ne pas prétendre avoir obtenu une restriction TCP.

## 5. Installation future et premier lancement — après autorisations

1. Recontrôler 8443 libre et WSDL local 8124 disponible, relever l’état et les PID existants. Si conflit, ne rien arrêter.
2. Faire approuver la version officielle Windows Caddy et vérifier authenticité/signature/checksum selon sa distribution. Aucun téléchargement exécuté par cette procédure préparatoire.
3. Préparer répertoires/binaire/configuration et ACL sous le nouveau compte d’exécution seulement. Installer les fichiers publics/privés approuvés, puis l’ACL réseau validée. Ne pas toucher aux paramètres de Syracuse.
4. Exécuter sous le futur compte relais, après accord et avec chemins réels :

```powershell
& 'C:\AGENT-SAGE-TLS\caddy.exe' version
& 'C:\AGENT-SAGE-TLS\caddy.exe' validate --config 'C:\AGENT-SAGE-TLS\Caddyfile' --adapter caddyfile
```

La validation charge les modules/certificats et vérifie leur accès ; ce n’est pas un test de la disponibilité réseau ou des droits métier. Elle ne doit pas être confondue avec le démarrage du proxy.

5. Après succès et autorisation de lancement du pilote :

```powershell
$relayProcess = Start-Process -FilePath 'C:\AGENT-SAGE-TLS\caddy.exe' `
    -ArgumentList @('run','--config','C:\AGENT-SAGE-TLS\Caddyfile','--adapter','caddyfile') `
    -WorkingDirectory 'C:\AGENT-SAGE-TLS' -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput 'C:\AGENT-SAGE-TLS\logs\stdout.log' `
    -RedirectStandardError 'C:\AGENT-SAGE-TLS\logs\stderr.log'
$relayProcess | Select-Object Id,ProcessName,StartTime
```

Cette commande doit être lancée dans la session du compte dédié ; elle n’installe pas de service et ne garantit pas la survie à une fermeture de session. Conserver PID, heure, chemin exact et association au pilote. Ne pas lancer sous admin par commodité si le compte prévu n’a pas été préparé. Pas de logs d’accès configurés ; ne pas activer debug, capture de corps ou Authorization. Protéger les journaux de fonctionnement et masquer les données non nécessaires avant partage.

6. Vérifier les écoutes : seulement le nouveau TCP 8443 IPv4 pour Caddy, sans nouvelle écoute 80/443/2019 ; Syracuse 8124 et son service restent inchangés. Vérifier la stabilité des lectures existantes avant/pendant/après. Si anomalie, arrêter le seul pilote.

## 6. Recette TLS/ACL sans écriture

Après installation autorisée, j’exécuterai depuis l’agent les lectures WSDL et SOAP existantes en utilisant HTTPS et le bundle vérifié. Les imports WSDL, Host transmis et endpoint doivent fonctionner sans redirection HTTP ou modification Syracuse ; sinon arrêt du pilote et revue, pas de contournement.

| Essai | Attendu |
|---|---|
| Agent 192.168.9.208 → https://sage:8443/chemin-WSDL?wsdl | TLS vérifié, HTTP 200 avec le compte autorisé |
| Agent → getDescription/read/query ITM/BPS/ITF | V12/TEST, objets attendus, lectures réelles réussies |
| Agent → chemin d’administration ou chemin non autorisé | Refus HTTP, aucun amont Syracuse pour ces requêtes |
| Autre machine existante, même sous-réseau → 8443 | Si ACL réseau : TCP refusé/non établi ; si ACL applicative seule : TCP/TLS possibles mais WSDL/SOAP refusés HTTP |
| Autre machine avec X-Forwarded-For: 192.168.9.208 | Toujours refusée, aucune confiance dans cet en-tête |
| Certificat dont nom/chaîne est incorrect | Refus du client, aucun verify=False |

Le test négatif exige un autre point réseau réel ; il ne doit pas être simulé par un simple en-tête depuis l’agent. Aucun nouvel hôte/VM à créer. L’absence de ce point de test doit être documentée, pas remplacée par un succès inventé. Aucune tentative de création Sage utilisée pour tester la sécurité.

## 7. Compte technique Sage X3 TEST — configuration future

Après autorisation distincte, le responsable Sage applique et documente :

1. Identifier l’authentification Syracuse réelle et l’utilisateur X3 métier effectif du pool. Compte système Caddy et compte métier Sage sont distincts.
2. Créer/valider des identités dédiées non administrateur, noms compatibles localement, sans copier le profil admin. Secrets renseignés localement, jamais en clair dans la procédure. Analyser les usages des anciens secrets exposés avant rotation, ne pas interrompre leurs consommateurs.
3. Profil limité au dossier **TEST** : accès Syracuse aux endpoints nécessaires et restrictions de pools ; côté X3, GESAUS/profil fonctions GESAFT et autorisations GESAFP ou écrans équivalents de l’installation. Aucun accès aux dossiers de production ou traitements génériques non nécessaires.

| Fonction / objet / publication | Droits à examiner | Limites |
|---|---|---|
| GESITM / ITM / WS_ARTICLE | Lecture, création ; modification distinctement approuvée | TEST, clés manuelles autorisées, catégorie NEG et règles actuelles |
| GESBPS / BPS / WS_FOURNIS | Lecture, création ; modification distinctement approuvée | TEST, numérotation/catégorie/pays/adresses obligatoires ; données Tiers partagées à examiner |
| GESITF / ITF / WS_AR_SITE | Lecture, création ; modification distinctement approuvée | TEST, site 201 et sociétés/codes d’accès autorisés |

4. Interdire suppression et options annexes non nécessaires. Contrôler les autres profils/groupes/rôles cumulés et accès indirects. Le SOAP générique reçoit le nom public et l’alias de pool dans le corps : le filtrage de chemin du proxy ne garantit pas à lui seul TEST ni ces trois objets.
5. Avant d’affecter ce compte à POOL_AI_TEST, inventorier ses consommateurs. Un changement d’utilisateur peut recycler les canaux : il ne nécessite pas ici un redémarrage Syracuse mais peut interrompre le pool. Si sa continuité est requise, proposer un pool TEST dédié avec nouvel alias, après accord, en conservant l’actuel. Ne pas inventer une isolation par compte qui n’est pas effectivement appliquée par la version installée.
6. Exports datés : utilisateur effectif, profils/options, restrictions dossier/site/pool, mappings, règles conditionnelles. Les droits d’écriture restent non prouvés par les seules lectures ou méthodes CREATE/MODIFY publiées. Refuser la bascule tant que le responsable métier n’a pas validé ces pièces.

La granularité précise des écrans/profils et le mécanisme de limitation aux pools doivent être vérifiés sur l’installation. Les exigences ci-dessus ne constituent pas des autorisations déjà configurées.

## 8. Configuration locale agent, après TLS et compte validés

Sauvegarder le .env privé. Changer uniquement l’URL vers `https://sage:8443`, le bundle CA public approuvé, les nouveaux secrets et éventuellement l’alias de pool approuvé. Désigner le dossier privé d’attestation par `SAGE_SECURITY_POLICY_FILE`. **SAGE_WRITES_ENABLED=false** durant la recette. Recharger uniquement FastAPI local ; vérifier TEST/V12, identité X3 non admin, trois publications et refus d’écriture HTTP 423.

L’activation ultérieure du drapeau reste une décision technique distincte. Les accords métier ne sont jamais remplacés par ce drapeau : approbations spécifiques à usage unique, digest et avant/après demeurent obligatoires. Refaire les préparations après changement de compte/pool/publication. Aucun repli automatique HTTP en écriture.

## 9. Impacts et retour arrière

| Changement | Impact/risque | Retour arrière |
|---|---|---|
| Binaire/configuration Caddy indépendants | Nouveau processus à maintenir, consommation de ressources ; compatibilité non encore testée | Vérifier PID, heure et chemin du pilote puis arrêter uniquement ce PID ; aucun Stop-Process -Name node/caddy global |
| Certificat et clé dédiés | Confiance incorrecte ou fuite de clé | Retirer l’affectation du seul relais ; révoquer uniquement un certificat dédié compromis selon la politique PKI, pas une CA/certificat Syracuse partagé |
| ACL réseau ciblée | Mauvaise portée/ordre pouvant affecter d’autres flux | Retirer/restaurer uniquement la nouvelle politique nommée et son état sauvegardé |
| Nouveau compte et pool | Droits excessifs, recyclage des canaux | Désactiver la nouvelle identité/pool dédié après vérification de ses usages ; restaurer l’association approuvée sans réintroduire un secret exposé |
| Paramètres FastAPI | Erreur TLS ou interruption locale lors du rechargement | Garder écritures désactivées, restaurer configuration privée approuvée ; aucune écriture compensatoire automatique |

Ni activation du pare-feu Windows, ni modification du certificat/listener Syracuse, ni redémarrage du serveur/Syracuse n’est inclus. L’arrêt du relais rend seulement son nouveau chemin HTTPS indisponible ; ne pas prétendre supprimer l’accès HTTP existant.

## 10. Autorisations à demander après revue

- A : choix Caddy et installation isolée/certificat/compte système/ACL, avec acceptation explicite de la portée du filtrage (TCP réseau ou refus HTTP applicatif).
- B : identités et droits Sage TEST, puis affectation au pool après inventaire de ses usages ; éventuel nouveau pool soumis séparément.
- C : configuration agent HTTPS en lecture seule, puis activation technique ultérieure des écritures si preuves satisfaites.
- Ensuite seulement : accord unique pour TAI261017948E, accord unique pour TB261017948E, read ITF TAI261017948E / 201 et accord éventuel s’il est absent. Modifications futures avec trois nouvelles approbations.

Une autorisation de préparer ce document ne vaut aucune de ces autorisations. Aucune création, modification ou suppression n’a été effectuée.
