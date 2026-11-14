# SOAP save depuis FastAPI — minimum nécessaire, sans nouveau service sur Sage

Analyse du **19 octobre 2026**. La nouvelle contrainte exclut l’installation de Caddy, stunnel ou autre service sur le serveur Sage. Les modèles antérieurs restent des documents historiques, non un plan d’installation à exécuter. Aucun changement de production ni écriture Sage réalisé.

Preuves : logs/step4-save-readiness.json, logs/step4-crud-prerequisites.json, logs/step4-save-guard-tests.xml. Les contrôles actuels sont réseau/SOAP/HTTP depuis l’agent, pas une session système administrateur sur Sage.

## 1. Différences réellement observées dans le WSDL

Les trois opérations utilisent le même endpoint CAdxWebServiceXmlCC et le même mécanisme RPC/encoded. Ce sont des POST HTTP SOAP, y compris read/query ; la différence n’est donc pas GET contre POST HTTP.

| Opération | Paramètres WSDL réels | Effet |
|---|---|---|
| read | callContext, publicName, objectKeys | Lit une fiche par clé |
| query | callContext, publicName, objectKeys, listSize | Recherche/liste limitée selon les clés de la publication |
| save | callContext, publicName, objectXml | Crée une fiche selon le mapping et les contrôles métier |

Dans les trois cas : langue FRA, pool POOL_AI_TEST, publication WS_ARTICLE ; le pool pointe vers V12/TEST. Pour save, ITMREF et les autres champs sont dans le XML objet PARAM/GRP/FLD, pas dans le paramètre objectKeys de read. save déclenche les obligations de création, valeurs par défaut, numérotation et contrôles conditionnels qui ne sont pas exercés par read.

Un HTTP 200 n’est pas à lui seul un succès métier : examiner statut/messages SOAP puis read et comparer les champs. En cas de résultat ambigu, aucune relance automatique. Ce n’est pas une opération idempotente garantie.

L’article manuel TSTAI2610174D94B4 a été **relu réellement le 19/10** : SOAP 1, existe, désignation ARTICLE TEST AGENT IA, catégorie NEG. Cela confirme l’existence de cette fiche, pas les droits d’un futur compte technique ni la conformité d’un autre jeu de données. Aucun nouveau save pour cet article.

## 2. Cause exacte de HTTP 423

`backend/app/api/sage_crud.py`, fonction writes_ready, appelle `security()` puis lève HTTPException(423) lorsque ready=false. Cette dépendance protège les routes POST/PATCH d’exécution et la route d’approbation. Le rejet intervient **avant** l’envoi SOAP. Ce 423 n’est pas une réponse Sage ni une incompatibilité de save.

État effectif contrôlé, cohérent avec GET /api/v1/sage/security :

| Code de blocage | Cause actuelle | Réglage/condition responsable |
|---|---|---|
| WRITES_DISABLED | Valeur effective false | SAGE_WRITES_ENABLED |
| VERIFIED_HTTPS_REQUIRED | URL effective http://192.168.9.200:8124 | SAGE_SOAP_BASE_URL doit actuellement être HTTPS sans identifiants intégrés |
| DEDICATED_TECHNICAL_ACCOUNT_REQUIRED | Identité HTTP administrateur ; identité X3 du pool également admin | Compte dédié non administrateur requis, identités HTTP et X3 liées aux preuves |
| VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED | Aucun chemin configuré ni fichier de politique chargé | SAGE_SECURITY_POLICY_FILE et preuves valides, date/périmètre/rotation d’identifiants |

SAGE_SOAP_CA_BUNDLE n’est pas configuré. Cette absence seule n’est pas un verrou si la CA est déjà reconnue ; avec une CA interne non reconnue il faut un bundle public explicitement approuvé. Le code TLS doit continuer à vérifier le certificat et son nom.

Après les conditions générales, d’autres contrôles s’appliquent par objet/action : droits et règles métier revus, préservation des clés manuelles, fichiers de preuve et leurs SHA256, empreinte de publication et de l’identité X3. Ces vérifications se trouvent dans services/sage_crud.py. Enfin l’approbation exacte, expirante et à usage unique est exigée dans execute().

**HTTPS et compte technique sont ici des exigences de sécurité de notre application**, pas une propriété du protocole SOAP qui rendrait save impossible en HTTP. L’appel manuel a pu fonctionner en HTTP parce qu’il n’utilisait pas ce gate FastAPI. Cela n’autorise pas à enlever le gate.

## 3. Réutilisation du connecteur existant

Le chemin est déjà disponible : React → POST articles/prepare → PostgreSQL → approbation spécifique → POST articles → execute → Gateway.write_once → SOAP save → read → comparaison/historique → React.

- SageReader/ReadOnlyTransport conservent leur liste blanche getDescription/query/read.
- Gateway.write_once réutilise le client Zeep, le WSDL et l’authentification existants, puis un OneShotTransport distinct pour le seul save autorisé, au pool/publicName/XML exacts. Il n’est pas nécessaire d’ajouter save à la liste blanche globale de lecture.
- L’approbation est consommée en transaction avant l’essai et aucun retry automatique n’est prévu. Une réponse ambiguë conduit à une relecture, sans second save.

Préparation réelle via FastAPI du 19/10 : TAI261017948E, ARTICLE TEST AGENT IA FASTAPI, fiche absente par read ; UUID `0951cef1-2ee4-45c8-8b7c-fdf0e294b7ec`. Le contenu a été sérialisé **sans envoi** avec Zeep create_message contre le WSDL réel : examples/crud-api/articles-save-current-NOT-SENT.xml. Les anciens UUID sont des brouillons ; après changement d’identité/URL/publication, refaire une préparation avant accord.

Les valeurs NEG, statut 1, stock 2, lots 3, unités SAC et coefficients 1, ACCCOD CPJ35 sont structurées selon le mapping réel. Elles ne constituent pas une attestation de toutes les règles métier conditionnelles. Aucun « save à blanc » de validation.

## 4. Droits nécessaires et limites de vérification

La description WS_ARTICLE expose CREATE pour ITM dans TEST. Les droits nécessaires doivent être contrôlés sur l’utilisateur X3 **effectif du pool** : GESITM/ITM, option de création, autorisation Web Services et publication, restrictions dossier/société/site/codes d’accès, catégorie et numérotation. Pour une modification ultérieure, option distincte et nouvelle approbation. Pas de suppression.

Vérifier aussi l’identité Syracuse, ses groupes/rôles et les autres pools accessibles : le nom du dossier dans un formulaire ne garantit pas à lui seul TEST. Le profil du compte dédié ne peut pas être déduit d’un succès admin.

L’API REST des métadonnées ITM.$details a de nouveau retourné HTTP 500 pendant ce contrôle. Cela limite son usage pour inspecter les règles/droits ; cela ne démontre pas un blocage de SOAP, dont getDescription/read ont fonctionné. Les exports GESAUS/GESAFT/GESAFP ou écrans équivalents, mapping GESAWE et paramètres métier doivent être validés par le responsable Sage. Ne pas modifier les profils admin pour faire passer le test.

## 5. Transport sécurisé avec l’infrastructure existante

Contrôle du 19/10 : 8124 joignable ; 443 et 8443 non joignables ; aucun chemin HTTPS existant validé. Cela ne permet pas d’exclure un proxy d’entreprise à une autre adresse. L’absence de nouveau logiciel n’interdit pas une configuration autorisée d’un composant existant.

| Option sans installation sur Sage | Adaptation minimale | Limites et autorisations |
|---|---|---|
| **HTTPS natif du Syracuse déjà installé** | Faire examiner une connexion TLS supplémentaire (8443 candidat), certificat existant sage ou autre certificat approuvé ; conserver 8124 | Configuration de production partagée. La documentation annonce un redémarrage lors de modifications de connexions actives/certificats : fenêtre, sauvegarde et accord explicite, aucune promesse zéro interruption |
| Reverse proxy/load balancer **déjà exploité**, à une URL fournie par l’administrateur | Réutiliser son listener/certificat/routage SOAP | Le segment proxy→Sage doit lui aussi être protégé par TLS ou tunnel réseau validé ; TLS seulement agent→proxy puis HTTP réseau n’est pas suffisant. Existence et compatibilité non confirmées |
| VPN/IPsec ou tunnel **déjà disponible et administré** | Vérifier les extrémités et le chiffrement de tous les segments utiles | Un HTTP dans un VPN peut être chiffré au niveau réseau, mais le gate actuel exige HTTPS. Une exception de transport spécifique nécessiterait conception, preuve vérifiable et tests après accord ; ne pas déclarer simplement HTTP « sécurisé » ni désactiver globalement 423 |

Le choix nécessitant le moins de changement applicatif est **HTTPS natif Syracuse**, s’il est approuvé : zéro nouvel exécutable/service, paramètres backend seulement. Il ne peut pas être activé sans modification serveur ni éventuel redémarrage. Sans modification autorisée de Syracuse et sans proxy/tunnel existant démontré, aucun transport sécurisé utilisable ne peut être affirmé aujourd’hui.

Un proxy TLS installé seulement sur l’agent puis HTTP jusqu’à Sage ne protège pas le réseau. Le magasin Windows vide n’exclut pas le certificat stocké par Syracuse. Le certificat sage doit être validé par nom DNS sage, chaîne et empreinte confirmée hors bande, dates/usages/clé ; ne pas utiliser l’IP dans l’URL si elle n’est pas dans son SAN.

## 6. Changements minimaux à approuver, sans refonte

1. Choisir et valider **un** transport sécurisé existant. Si HTTPS natif : conserver 8124, faire approuver listener TLS/certificat et l’impact de rechargement. Ne pas activer le pare-feu Windows globalement sans étude des flux ; filtrage limité au nouveau flux à examiner séparément sur l’infrastructure existante.
2. Configurer un compte technique TEST avec preuves de droits/règles. Inventorier les consommateurs avant changement d’utilisateur de POOL_AI_TEST ; recycler ses canaux peut interrompre ce pool. Un éventuel pool dédié est une autre modification à approuver, pas une installation de logiciel.
3. Configurer localement l’agent : SAGE_SOAP_BASE_URL vers l’URL HTTPS approuvée, SAGE_SOAP_CA_BUNDLE si nécessaire, secrets techniques privés, pool exact, SAGE_SECURITY_POLICY_FILE vers des preuves réelles. Garder SAGE_WRITES_ENABLED=false pendant les lectures de recette.
4. Tester TLS et getDescription/read/query, TEST/V12/identité, puis activer SAGE_WRITES_ENABLED uniquement après autorisation technique et preuves valides. Ce booléen seul ne suffit pas à autoriser un save.
5. Préparer de nouveau le XML final, lire l’absence exacte du code, présenter toutes les valeurs et demander l’accord humain pour cet UUID/digest uniquement. Enregistrer acteur/motif/expiration côté serveur. Aucun accord donné dans cette demande.
6. Après accord métier, une seule exécution via FastAPI ; read et comparaison de tous les champs, messages/statut SOAP et résultat dans PostgreSQL/React. Résultat ambigu : pas de retry. Si ITF est créé automatiquement après ITM, ne pas le recréer.

**Changements de code applicatif nécessaires avec HTTPS normal : aucun nouveau connecteur et aucune levée globale de protection.** Le transport d’écriture, les endpoints et l’approbation existent déjà ; le manque actuel porte sur les paramètres et leurs prérequis réels. Une adaptation supplémentaire ne serait justifiée que par un transport différent (par exemple VPN sans HTTPS), et n’est pas appliquée ici.

## 7. Validation réalisée et retour arrière proposé

Sept tests ciblés réussis : absence d’approbation, transport à usage unique, ambiguïté sans retry, preuves de sécurité et refus par défaut. Tests SOAP d’écriture simulés, pas Sage réel. Preuve : logs/step4-save-guard-tests.xml.

Le diagnostic réel conserve 0 approbation et 0 write_attempt_claimed. Seul un nouveau brouillon a été écrit dans PostgreSQL local. Aucun secret n’est affiché.

Retour arrière futur : garder écritures désactivées et restaurer les paramètres agent privés ; pour HTTPS natif, restaurer seulement les paramètres Syracuse sauvegardés dans une fenêtre autorisée, en tenant compte d’un nouveau redémarrage possible. Ne pas réintroduire de secret exposé, ne pas supprimer les fiches et ne pas envoyer une écriture compensatoire automatique.

Sources : [SOAP Sage X3, paramètres et opérations](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/api-guide_soap-web-services.html), [connexions TLS de l’hôte Syracuse et redémarrage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).
