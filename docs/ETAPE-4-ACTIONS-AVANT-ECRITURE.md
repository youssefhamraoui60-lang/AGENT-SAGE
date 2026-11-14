# Actions à autoriser avant les tests d’écriture via FastAPI

Établi le 17 octobre 2026. Aucun changement de production ni aucune écriture Sage effectué.
Preuve actuelle : logs/step4-crud-prerequisites.json. Le terme « préparé » ne signifie pas « autorisé ».

## Contrôles actuels

| Contrôle depuis la VM agent | Résultat |
|---|---|
| TCP 192.168.9.200:8124 | Joignable, transport HTTP actuel |
| TCP 443, 8443 et 22 | Non joignables ; ne prouve ni absence d’installation ni port libre côté serveur |
| getDescription des trois publications | V12/TEST, objets ITM/BPS/ITF attendus, CREATE et MODIFY publiés |
| Identité X3 du pool | Toujours administrateur ; compte technique pas encore validé |
| read des trois codes proposés | Statut 0 « Fiche inexistante » pour chaque fiche |
| POST et PATCH sans approbation | Six réponses HTTP 423, avant tout appel SOAP d’écriture |
| Approbations / tentatives réelles enregistrées | 0 / 0 |
| Vérifications ciblées en simulation | 7 tests réussis : approbation absente/expirée, périmètre, état concurrent et verrouillage |

La présence de CREATE/MODIFY dans getDescription décrit la publication. Elle ne prouve pas les droits effectifs du futur compte. Les vérifications de droits restent **non réalisées pour ce compte inexistant/non configuré**. Aucune validation distante par save « à blanc » ne sera utilisée.

## Autorisation technique T1 — relais TLS isolé sur le serveur Sage

Proposition privilégiée pour conserver Syracuse sans redémarrage : un processus **stunnel** indépendant, sur le serveur 192.168.9.200, reçoit TLS sur 8443 et transmet uniquement vers son propre loopback 127.0.0.1:8124. Aucun changement du listener Syracuse, du pool actuel, du DNS ou des consommateurs HTTP existants dans cette action.

```text
FastAPI 192.168.9.208 → TLS vérifié https://sage:8443
                     → relais sur 192.168.9.200 → loopback HTTP 127.0.0.1:8124
```

Configuration reviewable : [stunnel-sage-test.NOT-APPLIED.conf](../config/stunnel-sage-test.NOT-APPLIED.conf). C’est un candidat non installé, non testé avec le binaire ni avec Syracuse. Il ne constitue pas une configuration validée.

Avant installation, l’administrateur du serveur Sage doit :

1. Vérifier le système du serveur, la compatibilité du paquet officiel et son authenticité, les ressources disponibles, l’absence d’autre relais géré réutilisable et la disponibilité **locale** de 8443. Consulter `Get-NetTCPConnection -LocalPort 8443` seulement si le serveur est Windows.
2. Émettre de préférence un certificat **dédié** au relais, SAN DNS `sage` (ou FQDN approuvé, avec adaptation explicite de l’URL), usage serveur TLS et clé conservée exclusivement sur ce serveur. Faire confirmer la CA et ses empreintes par un canal indépendant. Ne pas exporter automatiquement la clé privée Syracuse « sage ».
3. Préparer un compte d’exécution système dédié non administrateur après installation, ses ACL de lecture de clé et d’écriture du seul journal. Vérifier la correspondance clé/certificat et la chaîne. Les répertoires `C:/AGENT-SAGE-TLS/...` du modèle sont proposés côté serveur, pas créés.
4. Faire approuver et appliquer uniquement une autorisation TCP entrante **192.168.9.208 → 192.168.9.200:8443**. Examiner les règles existantes larges : une simple règle Allow limitée n’annule pas une autre règle Allow plus large. Si la restriction effective ne peut être garantie sans toucher l’existant, ne pas lancer le relais avant nouvelle décision.
5. Démarrer uniquement le nouveau processus après validation de la configuration par l’outil et des ACL. Aucun enregistrement de service automatique, redémarrage Windows/Syracuse, arrêt ou modification d’un service existant n’est inclus dans cette proposition.
6. Tester TLS puis WSDL/getDescription/read sans écriture. Vérifier que Host `sage:8443`, l’authentification et les réponses fonctionnent sans nouvelle configuration Syracuse. Si une adaptation Syracuse est nécessaire, arrêter le pilote et demander une autorisation séparée.

Risques : nouveau logiciel/processus sur le serveur, surface d’écoute supplémentaire, gestion d’une clé et consommation de ressources. Le relais TCP ne filtre ni chemins SOAP ni dossiers : le confinement TEST doit être garanti aussi par les comptes/pools Sage et FastAPI. La dernière portion en clair est strictement loopback. Aucun deuxième hôte, proxy agent→Sage en HTTP ou déchiffrement réseau intermédiaire.

Retour arrière : arrêter **le seul processus pilote identifié par son PID et son chemin**, retirer seulement la nouvelle règle nominative si elle a été créée, conserver les fichiers de diagnostic privés. Ne pas lancer une commande globale d’arrêt stunnel qui toucherait un autre relais. L’écoute 8124 demeure intacte. La disponibilité Syracuse n’est pas garantie abstraitement : surveiller les lectures avant/pendant/après ; aucun redémarrage Syracuse prévu.

Le port SSH 22 n’étant pas joignable, aucun tunnel SSH déjà utilisable n’est établi. Installer/activer SSH ou IPsec serait une autre modification à autoriser. Le gate FastAPI actuel exige une URL HTTPS vérifiée : il ne faut pas le désactiver pour accepter un endpoint HTTP sous prétexte de tunnel.

Une connexion HTTPS **native** Syracuse n’est pas la solution retenue pour cette exigence sans interruption : la documentation Sage indique le redémarrage lors de modifications de connexions actives/certificats. [Source Sage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html). Fonctionnement et paramètres du relais : [manuel officiel stunnel](https://www.stunnel.org/manual.html) et [paquets officiels](https://www.stunnel.org/downloads.html).

## Autorisation technique T2 — compte Sage dédié et droits TEST

Demander au responsable Sage la création d’identités dédiées, par exemple `SVC_AI_TEST` côté Syracuse et `AI_TEST` côté X3 (noms à valider selon les limites locales). Aucun mot de passe dans le chat, les sources ou les rapports. Les identifiants exposés doivent être renouvelés avec analyse de leurs consommateurs ; ne pas changer aveuglément le mot de passe admin utilisé par d’autres services.

Définir les droits avec le responsable métier, sans copie de profil administrateur :

| Publication | Fonction / objet | Dossier | Options à vérifier individuellement |
|---|---|---|---|
| WS_ARTICLE | GESITM / ITM | TEST seulement | Lecture, création, modification ; pas suppression |
| WS_FOURNIS | GESBPS / BPS | TEST seulement | Lecture, création, modification ; pas suppression |
| WS_AR_SITE | GESITF / ITF | TEST seulement, site 201 si applicable | Lecture, création, modification ; pas suppression |

Vérifier l’utilisateur X3 effectif du pool, activation et accès Web Services, son profil fonctions (GESAUS/GESAFT/GESAFP ou écrans correspondants de l’installation), options effectives, restrictions de dossier/société/site et codes d’accès. Vérifier aussi les autorisations Syracuse, endpoints et groupes : aucune appartenance administrateur ni accès à un pool de production.

Le serveur SOAP générique accepte un alias de pool dans le corps : la restriction au seul endpoint URL ne suffit donc pas. Contrôler que l’identité technique ne peut utiliser d’autres pools/dossiers ni obtenir leurs droits. Documenter le périmètre et ne pas tester une création dans un autre dossier pour le démontrer.

**Conserver POOL_AI_TEST** est possible seulement après confirmation qu’aucun consommateur non concerné ne dépend de son identité admin et après autorisation de changement d’utilisateur. Ce changement peut recycler les canaux et interrompre les appels de ce pool. Si une absence totale d’interruption du pool est requise, proposer séparément un pool dédié TEST, sans modifier le pool existant ; aucun nouveau pool n’est créé ici. Le changement d’alias implique nouvelle configuration agent, nouvelles preuves et nouvelles préparations.

Preuves attendues : exports/captures datés et validés, identité effective, profil/options pour chacune des six combinaisons objet/action, mappings GESAWE des trois publications. Stocker sans secrets dans un répertoire privé `config/security-evidence/`. Aucun accès de consultation aux exports d’administration sur le serveur n’est disponible depuis cette session : ces preuves nécessitent l’intervention du responsable Sage.

## Autorisation technique T3 — vérification des règles et activation agent

Contrôler catégorie article NEG, numérotation manuelle, statut/stock/lots/unités SAC/coefficient/comptabilité ; catégorie fournisseur et pays réellement applicables, adresse/conditions/règles obligatoires ; site 201 autorisé et paramètres ITF. Une valeur observée sur une fiche ne démontre pas sa validité pour toute nouvelle création.

Relire ITM et ITF après une future création article : les paramètres peuvent créer automatiquement une fiche article-site. Si ITF existe déjà, ne pas envoyer save pour cette clé ; présenter sa fiche et préparer seulement une modification après accord. [Documentation Articles Sage](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESITM.htm), [Articles-sites](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESITF.htm).

Après T1/T2 et revue métier, la modification locale proposée est :

```dotenv
SAGE_SOAP_BASE_URL=https://sage:8443
SAGE_SOAP_CA_BUNDLE=C:/AGENT-SAGE-X3/config/security-evidence/approved-ca-bundle.pem
# SAGE_SOAP_USERNAME / PASSWORD : renseignés localement, jamais dans un document public.
SAGE_SECURITY_POLICY_FILE=C:/AGENT-SAGE-X3/config/sage-write-policy.local.json
SAGE_WRITES_ENABLED=false
```

Le support CA applicative existe déjà ; ne pas utiliser verify=False, -k ou un contournement de nom DNS. Conserver la confiance limitée au client SOAP, sans import global Windows. Valider d’abord les lectures sur HTTPS et TEST avec le nouveau compte ; ne pas activer les écritures pendant ce contrôle. Redémarrer uniquement FastAPI local après sauvegarde privée de son .env. Risque : indisponibilité momentanée de l’API agent si erreur TLS ; aucune relance d’écriture HTTP de secours.

Le dossier privé d’attestation doit porter les six autorisations distinctes (articles/suppliers/article-sites × create/update), les pièces et leurs SHA256, les empreintes de publication et des identités, cible exacte, expiration et revue des règles métier. L’exemple existant est volontairement inactif. Aucune attestation ne sera fabriquée pour contourner la vérification de droits.

La bascule finale SAGE_WRITES_ENABLED=true, une fois toutes les preuves validées, nécessite une autorisation technique distincte ; elle n’autorise aucune opération métier. Une approbation explicite et non réutilisable reste obligatoire pour chaque opération. Refaire les tests de refus sans jeton/avec faux jeton : ils doivent encore refuser sans produire de write_attempt_claimed ni appeler SOAP.

## Six demandes métier séparées — toutes en attente

Les détails exacts et XML sont dans [les fiches d’approbation](ETAPE-4-DEMANDES-APPROBATION.md). Aucune demande ci-dessous n’est exécutable tant que T1–T3 ne sont pas validées et qu’une nouvelle préparation n’a pas été revue.

| ID | Demande distincte | Dépendance |
|---|---|---|
| C-ITM | Une création TAI261017948E via POST articles | TLS + compte + droits/règles + read absent |
| C-BPS | Une création TB261017948E via POST suppliers | Même prérequis, indépendamment d’ITM |
| C-ITF | Une création TAI261017948E / 201 via POST article-sites | ITM créé et relu ; ITF encore absent |
| M-ITM | Une modification de la désignation TAI261017948E via PATCH | Après création vérifiée et nouvel avant/après |
| M-BPS | Une modification de BPRSHO de TB261017948E via PATCH | Après création vérifiée et nouvel avant/après |
| M-ITF | Une modification ABCCLS de TAI261017948E / 201 via PATCH | Après existence vérifiée et nouvel avant/après |

Après chaque accord spécifique : FastAPI seul exécute une tentative, SOAP read vérifie, React affiche et PostgreSQL conserve le résultat. Aucun retry si résultat ambigu : relecture seule et investigation.

## Codes et vérification manuelle future dans TEST

| Code / site | Navigation Sage X3 | Consultation React |
|---|---|---|
| TAI261017948E | Données de base > Articles > Articles, GESITM | /sage/?resource=articles&code=TAI261017948E |
| TB261017948E | Données de base > Tiers > Fournisseurs, GESBPS | /sage/?resource=suppliers&code=TB261017948E |
| TAI261017948E / 201 | Données de base > Articles > Articles-sites, GESITF | /sage/?resource=article-sites&code=TAI261017948E&site=201 |

Les trois fiches sont actuellement absentes ; ces liens ne constituent pas une preuve de création.
