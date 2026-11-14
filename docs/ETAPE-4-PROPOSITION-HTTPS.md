# Proposition HTTPS — non appliquée

**Décision utilisateur du 19/10/2026 : aucune installation de service supplémentaire sur le serveur Sage.** La [nouvelle analyse minimale SOAP save](ETAPE-4-SOAP-SAVE-MINIMAL-SANS-INSTALLATION.md) remplace les projets Caddy/stunnel comme piste active : HTTPS natif Syracuse ou infrastructure sécurisée déjà existante, sous réserve de validation et autorisation des configurations. Aucun déploiement ni désactivation de protection effectué.

**Procédure actualisée après les constats serveur** : [installation TLS 8443 à approuver](ETAPE-4-INSTALLATION-TLS-8443-A-APPROUVER.md). Pare-feu Windows désactivé confirmé par l’utilisateur ; proposition Caddy avec ACL applicative source et politique réseau séparée pour interdire réellement les connexions TCP hors agent. Le modèle stunnel seul n’assure pas cette restriction. Aucun de ces changements n’est appliqué.

**Actualisation du 17/10/2026** : voir [le plan d’actions actuel](ETAPE-4-ACTIONS-AVANT-ECRITURE.md), incluant un candidat relais TLS indépendant sans redémarrage Syracuse. Les constats de certificat ci-dessous sont historiques, non une validation d’un listener TLS actuel. Le support `SAGE_SOAP_CA_BUNDLE` existe désormais dans FastAPI ; il reste non configuré en exploitation. Les références ci-dessous à son absence décrivent l’état initial et sont remplacées par cette actualisation. L’article manuel TSTAI2610174D94B4 a depuis été créé par l’utilisateur : ne pas le recréer. Les trois nouveaux codes de test figurent dans le plan actuel.

Cette proposition ne modifie aucun service, certificat, droit ou pare-feu. Toute activation côté Sage doit être autorisée et planifiée.

## Configuration constatée

- Hôte Syracuse `sage`, version déclarée `12.23.3.6-0`, deux processus Web Services enfants.
- Une seule connexion publiée : TCP 8124, active, SSL=false, serverCert=null.
- Certificat interne `sage`, clé privée déclarée présente sur le serveur; aucun téléchargement de clé privée effectué.
- Certificat public examiné : SAN DNS `sage`, valable du 26/02/2026 au 24/02/2036, autorité émettrice interne.
- Depuis la VM agent, `sage` se résout vers 192.168.9.200 (nom canonique retourné : sage.local).
- SAN `sage` ne couvre ni l'IP 192.168.9.200 ni le nom sage.local. Utiliser l'URL avec le nom exact `sage`, ou obtenir un certificat avec les SAN adéquats pour un FQDN approuvé.
- Vérification complémentaire en lecture seule : signature du certificat `sage` vérifiée avec la CA publique `ca`, signature de la CA auto-signée vérifiée, CA=true pour l'autorité et CA=false pour le certificat serveur; dates valides pour les deux.
- Certificat serveur RSA 2048 bits, signature SHA-256/RSA; KeyUsage inclut signature numérique et chiffrement de clé. Aucune extension EKU n'a été observée dans le dump public; l'usage réel sera confirmé par un handshake TLS normal avant exploitation.
- La CA n'a pas été retrouvée par empreinte exacte dans les magasins Windows ROOT/CA consultés ni dans le bundle par défaut de Requests. Aucune installation de confiance n'a été effectuée.
- Les parties publiques ont été obtenues par HTTP : la cohérence cryptographique de la chaîne ne prouve pas son authenticité. Faire confirmer les empreintes par un canal d'administration indépendant avant de faire confiance à cette CA.
- Révocation, confiance de bout en bout, état réel de la clé privée et correspondance clé/certificat sur le serveur restent à vérifier. La présence d'une clé déclarée ne démontre pas à elle seule sa correspondance cryptographique.
- Aucun listener TLS joignable sur 443/8443, ni TLS sur 8124 lors des tests. Aucun reverse proxy n'est identifié dans les informations exposées; un proxy externe non communiqué reste possible.

## Option A — HTTPS natif Syracuse

À faire examiner par l'administrateur Sage, sans application automatique :

| Paramètre de connexion | Proposition |
|---|---|
| Hôte | sage |
| Port HTTPS à réserver et approuver | 8443 |
| SSL | activé |
| Certificat serveur | sage, seulement après validation chaîne/usage/clé |
| Authentification certificat client | non requise pour le test avec Basic sous TLS; ne pas changer une politique mTLS existante |
| URL de base candidate | https://sage:8443 |
| Accès à autoriser | VM agent 192.168.9.208 et postes d'administration explicitement approuvés |

L'ajout ou la modification d'une connexion active/certificat peut entraîner un redémarrage Syracuse : prévoir une fenêtre et un retour arrière.
Conserver une copie de la configuration existante et prévoir le rétablissement des paramètres précédents en cas d'échec.
Ne pas modifier silencieusement les consommateurs HTTP existants ni leur authentification.
L'administrateur doit d'abord vérifier que 8443 est libre **sur le serveur**, les tests réseau depuis l'agent ne le démontrant pas.

Le listener Syracuse est commun au serveur, même si le test fonctionnel vise uniquement TEST. L'ajout d'une connexion ne peut donc pas être présenté comme sans impact possible sur les dossiers de production.

## Option B — reverse proxy déjà approuvé

Si un IIS/ARR, Nginx, HAProxy ou autre proxy est déjà administré, demander son URL et ses paramètres avant d'en créer un.
Terminaison TLS avec certificat correspondant au DNS approuvé; préserver le corps SOAP, Authorization, Content-Type et SOAPAction.
Router uniquement les deux chemins nécessaires :

```text
/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl
/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC
```

Pas de retry automatique ni de rejeu des POST SOAP. Ne pas journaliser Authorization ou les corps SOAP.
Limiter les accès à l'IP agent et aux administrateurs approuvés; éviter toute exposition Internet.
Si le proxy est sur le serveur Sage, l'amont HTTP peut rester sur loopback 127.0.0.1:8124.
Si l'amont traverse le réseau, le protéger également par TLS validé ou un tunnel approuvé : le simple chiffrement du lien agent-proxy ne protège pas ce second segment.
Un reverse proxy peut demander des réglages Syracuse d'origine/protocole; vérifier la documentation de la version avant modification, sans ajouter arbitrairement des en-têtes ou options nodelocal.

## HTTPS sans modification des services existants : verdict

Aucun chemin HTTPS existant utilisable n'est établi. **L'activation native exige une modification de la configuration Syracuse**; il est impossible de promettre zéro perturbation sur ce serveur partagé.
Un proxy dédié sur le serveur Sage pourrait théoriquement fournir TLS vers un amont loopback sans modifier le listener Syracuse 8124.
Ce scénario n'est pas encore validé : il faut vérifier un emplacement d'exécution isolé, un port libre, la gestion de la clé privée, les ressources,
les règles d'accès et l'absence d'effet sur un proxy/IIS déjà partagé. Il ajoute une configuration et un processus à autoriser, même s'il ne change pas Syracuse.
Un proxy situé uniquement sur la VM agent, puis HTTP en clair jusqu'au serveur Sage, ne satisfait pas à lui seul l'objectif de chiffrement réseau.

## Modifications précises à autoriser, séparément du test métier

| Changement proposé | Portée | Risque et retour arrière |
|---|---|---|
| Ajouter une connexion HTTPS Syracuse 8443 avec certificat `sage`, conserver 8124 inchangé | Serveur Syracuse partagé | Redémarrage/rechargement possible et interruption des sessions; fenêtre approuvée et sauvegarde de configuration. Retirer la nouvelle connexion peut provoquer un autre rechargement. |
| Autoriser 192.168.9.208 vers le port approuvé, si filtré | Règle d'accès réseau limitée | Nouvelle surface d'écoute; vérifier le port local et l'accès limité, retour arrière en retirant uniquement la nouvelle règle. Aucune règle actuelle modifiée ici. |
| Déclarer une CA publique vérifiée au seul client SOAP | Projet agent, bundle applicatif | Étend la confiance du client à une CA; confirmer son empreinte hors bande, éviter une installation globale. Revenir au réglage de vérification par défaut si nécessaire. |
| Adapter explicitement `session.verify` à ce bundle et changer l'URL en `https://sage:8443` | Backend local agent | Redémarrage du backend agent et erreur de connexion possible en cas de mauvaise chaîne; conserver l'ancien `.env` privé et le code avant modification. Pas de repli automatique HTTP pour une écriture. |

Le paramètre `SAGE_SOAP_CA_BUNDLE` est déjà implémenté dans `SageReader._client()` et transmis à `requests.Session.verify`. Il reste non configuré. Sans bundle, la vérification TLS standard reste active. Un fichier inexistant est refusé. Aucun certificat public récupéré par HTTP n'est installé automatiquement dans un magasin de confiance.

Empreintes DER SHA-256 à faire confirmer par l'administrateur :

```text
Serveur sage : 8E:A0:53:B4:79:94:C5:60:E9:C0:94:FA:79:63:5F:E3:A7:23:81:44:14:8F:43:C9:C9:98:BD:89:86:D0:3E:D9
CA interne  : D2:CA:11:64:11:F5:A3:E6:CF:09:AA:66:13:30:CB:B4:5E:92:B9:9B:40:BD:EF:B9:E1:D3:16:E7:6A:08:0F:4F
```

Une approbation de ces travaux techniques n'autoriserait aucune création d'article. Le `save` unique nécessite une confirmation distincte après les contrôles métier et TLS.

## Vérification côté agent avant toute création

1. Fournir uniquement le certificat public de l'autorité et les intermédiaires nécessaires; jamais la clé privée serveur.
2. Vérifier les empreintes via un canal d'administration fiable, le SAN, les dates, la chaîne et les usages.
3. Vérifier que le client Python utilise réellement cette chaîne de confiance. Le connecteur actuel désactive les proxys d'environnement (`trust_env=False`) : ne pas supposer que REQUESTS_CA_BUNDLE sera automatiquement lu.
4. Si l'autorité n'est pas déjà reconnue par Requests, préparer une configuration applicative explicite `session.verify=<bundle PEM approuvé>` et ses tests. Le support applicatif est déjà présent ; seule sa configuration autorisée reste à faire.
5. Ne jamais utiliser verify=False, -k ou l'acceptation automatique de certificats invalides.
6. Tester WSDL, getDescription et read via l'URL HTTPS approuvée; vérifier TEST/V12 dans la réponse, puis l'absence de TSTAI2610174D94B4.
7. Reconfigurer localement l'URL SOAP seulement après validation; un redémarrage du backend agent charge les variables. Cette reconfiguration reste à faire.
8. Demander une nouvelle confirmation humaine sur le XML final. Aucun test de save à blanc : save peut créer réellement.

## Éléments à fournir pour lever les autres blocages

- Export/validation du profil utilisateur X3 effectif (GESAUS), du profil fonctions (GESAFT), des autorisations fonctionnelles (GESAFP) pour GESITM/ITM, des options création et des restrictions d'accès/rôles.
- Export de GESAWE/WS_ARTICLE, des écrans et traitements spécifiques contrôlant la création, et des paramètres DIVE dans GESITG : compteur manuel/automatique, groupes statistiques, unités, fournisseur/site requis et valeurs initiales.
- Extraits de journaux Syracuse/X3 autour des requêtes REST en échec, avec horodatage et stack trace, secrets masqués. Les diagnostics hostDiagnoses consultés ne contiennent pas cette erreur.

## Sources officielles

- [Configuration des connexions de l'hôte](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).
- [Gestion des certificats](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_certificates.html).
- [Reverse proxy HTTP vers HTTPS](https://online-help.sagex3.com/erp/11/en-US/V7DEV/getting-started_how-to-set-up-the-web-server-to-make-it-work-in-https-mode.html) : principes généraux, documentation V11 à revalider pour la version Syracuse constatée.
