# PEINTURE ACRYLIQUE BLANCHE 20 KG — correction du parcours

30 octobre 2026. Aucune création réelle ni modification de fiche Sage exécutée. Le parcours est corrigé et testé ; la validation finale d'un SAVE réel reste ouverte.

## Diagnostic confirmé

La demande originale et ses traces sont dans `reports/peinture-original-conversations.json`.

1. **Premier échec : attente Qwen, avant appel au modèle.** La conversation `c17d2f60-2c68-4a59-ba99-4323f8db9ce3` enregistre `ExtractionTimeout`, phase extracting, `ai_calls=0`, durée backend 15 076,569 ms. Le délai d'acquisition du verrou modèle dans `chat_model.extract` est de 15 s. Une autre conversation PEINTURE était alors en extraction : 60,2 s, dont 41,670 s de préremplissage, 1 535 tokens d'entrée, 95 de sortie. Ce n'était pas un JSON invalide ni un échec SQL. La reprise a réussi en 28,92 s, avec un seul message utilisateur et un seul article dans cette conversation.
2. **Format non reconnu par le parcours court.** `simple_initial` ne traitait ni « un nouvel article », ni la liste « Désignation : … - Catégorie article : … », ni la clause finale de gestion de stock. Ces demandes partaient vers le prompt général et son contexte volumineux.
3. **Erreur supplémentaire révélée par les essais Qwen forcés.** Malgré l'instruction métier, le modèle renvoyait `gestion_stock="0"`. Sage utilise le menu 215 : `1=Art non géré`, `2=Article géré`, `3=Art géré titre`. Pydantic refusait correctement 0. La sortie JSON courte n'imposait pas encore cet enum. Preuve brute et erreur de validation conservées dans `reports/peinture-qwen-schema-diagnostic.json` ; échecs initiaux dans `peinture-real-qwen-before.json`.
4. **Erreur sur une préparation métier refusée.** `article_execution.tax_review` appelait `.get()` sur `business_checks=None`, valeur produite par une préparation bloquée. Les tests stock/fournisseur conditionnels l'ont reproduite. Le contrôle traite maintenant ce résultat comme non validé ; aucune approbation ne devient possible.
5. **Interface incohérente et blocage trop générique.** La capture montre l'ancien texte « limité à EXT_POUDRE » et des boutons de relecture historiques. Cette phrase est absente du bundle actuellement servi. L'hypothèse d'un ancien onglet/bundle est compatible avec les faits, mais le cache du navigateur utilisateur n'a pas été inspecté. Le HTML du chat est désormais servi avec `Cache-Control: no-store, max-age=0`. Un onglet déjà ouvert doit être rechargé pour charger la nouvelle interface.

## Corrections effectuées

| Fichier / fonction | Résultat |
|---|---|
| `backend/app/services/chat_article_requests.py`, `simple_initial`, nouveau `labelled_initial` | Extraction littérale des deux formulations et des listes à puces ; désignation conservée, NEG/UN/201/20/stock 1 explicitement extraits. Champs inconnus ou contradictoires renvoyés au modèle, jamais ignorés silencieusement. |
| `backend/app/services/chat_model.py`, `single_article_schema`, `extract` | Schéma court avec enum stock Sage, prompt explicite. Pas d'augmentation des délais. Le parcours normal couvert ne consomme aucun appel Qwen ; les essais forcés vérifient séparément le vrai modèle. |
| `backend/app/services/article_execution.py`, `tax_review`, `security_controls`, `describe`, `blocked_message` | Gestion sûre des validations absentes ; contrôles réellement échoués accompagnés de libellés et d'actions. Aucune donnée de connexion ni aucun secret exposé. |
| `backend/app/services/conversation_chat.py`, `compose` | Motifs techniques explicites et suppression de l'instruction de relecture historique pour le parcours général. La relecture reste distincte de l'approbation d'écriture. |
| `frontend/src/GeneralArticleActions.jsx`, `GeneralArticleActions` | Blocage lisible, détails des contrôles et des règles refusées. Le bouton de préparation disparaît tant que la sécurité est fermée ; aucune invitation infinie à confirmer le brouillon. |
| `frontend/src/analysisJobs.js`, `analysisStatus` ; `ChatApp.jsx`, `ChatApp` | « Création bloquée — action nécessaire », « Données exactes prêtes à approuver » ou « Création vérifiée », selon l'état courant. |
| `backend/app/main.py`, `log_request` | HTML du chat non conservé comme ancienne version ; assets JS nommés par empreinte. |
| `backend/tests/test_peinture_creation.py` et scripts navigateur/Qwen dédiés | Régressions et preuves décrites ci-dessous. |

Les numéros de lignes et empreintes finales figurent dans `reports/peinture-validation-summary.json`. Le parcours général CPJ existant, ses approbations, son SAVE unique et sa relecture sont réutilisés ; les restrictions de sécurité n'ont pas été supprimées. La publication réelle s'appelle **WS_ARTICLE**, au singulier (`sage_gateway.RESOURCES['articles']`). WS_AR_SITE est une publication distincte.

## Données métier réellement vérifiées

Preuves SELECT TEST et descriptifs existants : `reports/peinture-references.json` et `peinture-site-publication.json`.

| Information | Constat |
|---|---|
| Désignation | PEINTURE ACRYLIQUE BLANCHE 20 KG, conservée sans réécriture. |
| Code proposé | `PEINTURE-ACRYLIQUE-B`, 20 caractères, format accepté par le validateur. Absent au SELECT exact. Proposition non réservée, pas un numéro attribué par Sage. Le descriptif existant limite ITMREF à 20 caractères ; disponibilité à recontrôler avant SAVE. |
| Catégorie, unité, site | NEG, UN et 201 retrouvés. Site 201 / société 20 / OULD BOUAZZA. |
| TVA | Taux T20 à 20 % retrouvé ; détermination active MAR_T20, niveau T20, régime MAR. Le défaut NEG est aussi T20. Cela reste insuffisant pour certifier l'applicabilité fiscale à cette peinture ; aucune règle fiscale n'est inventée. |
| Stock | Le descriptif SOAP expose STOMGTCOD en entrée, menu 215, valeur 1 « Art non géré ». L'article historique EXT_POUDRE est effectivement NEG/UN et STOMGTCOD=1, alors que la catégorie a un défaut 2. Le défaut n'est donc pas une preuve d'interdiction de la valeur 1. Ce précédent n'est pas promu en règle générale autorisant toute création. |
| Fournisseur | Non précisé et non inventé. Le champ BPSNUM existe dans la publication et n'est pas marqué OBL dans ce descriptif. Cela ne certifie pas toutes les règles conditionnelles de Sage. Le moteur accepte son absence si la règle de catégorie revue le rend facultatif et bloque si elle le rend obligatoire ; les deux branches sont testées. |
| Comptabilité | ACCCOD vide dans la catégorie consultée et dans l'exemple historique EXT_POUDRE. Aucun code comptable ni compte général déduit. Les obligations conditionnelles restent soumises au référentiel métier revu et à Sage. |
| Existence | Le SELECT de `TEST.ITMMASTER` ne retrouve pas le code proposé ; l'article n'a pas été créé par cette campagne. |

## Article-site

La publication WS_AR_SITE expose les clés `ITF0_1.ITMREF` et `ITF0_1.STOFCY`. Le descriptif existant expose notamment `ITF1_2.ABCCLS` ; il ne porte pas ici de marquage OBL permettant de déduire toutes les obligations métier. Ces champs nécessitent un modèle de site revu ; aucune valeur n'est inventée.

Le parent PEINTURE est absent : **aucune préparation exécutable ni aucun SAVE article-site n'est tenté**. Après un futur parent créé et relu, le workflow effectue une nouvelle recherche de l'enfant avant toute proposition. S'il existe déjà, il ne recrée pas de fiche. Sinon, préparation, approbation exacte et relectures sont séparées.

Le SELECT actuel montre aussi EXT_POUDRE présent comme article maître, mais aucune fiche EXT_POUDRE/201. La présence d'un article ne garantit donc pas son rattachement à ce site. Aucun essai réel de cette campagne ne permet de certifier une création automatique article-site par WS_ARTICLE ; elle reste à vérifier après un futur SAVE autorisé, sans seconde création aveugle.

## Nouveau comportement de préparation

- Si sécurité ou règles bloquées : **BLOQUÉ**, liste des contrôles et action précise, sans bouton invitant à répéter la préparation. Les données demandées restent inchangées.
- Si les contrôles et règles revues sont satisfaits : préparation des données/XML exacts par le parcours général, puis **PRÊT À APPROUVER**. Une relecture du brouillon n'autorise aucun SAVE.
- Après approbation spécifique de cette version : une seule tentative, puis SOAP read et comparaison SQL. Une approbation expirée, une correction, un doublon apparu ou un refus empêche un faux succès/rejeu.
- Article-site : opération distincte après contrôle du parent et de l'absence d'enfant.

## Tests et mesures

**Résultats finaux : 1 537 tests backend réussis (14 nouveaux tests PEINTURE inclus), 3 ignorés et 3 tests locaux exécutés séparément avec succès ; 28 tests frontend réussis, build réussi.**

Les résultats définitifs sont enregistrés dans `reports/peinture-validation-summary.json` et les JUnit associés. Les échecs intermédiaires sont conservés.

- Deux formulations Qwen réelles forcées : **2/2 réussies au premier appel après correction**, sans retry ; 17,778 s et 19,072 s, 192/219 tokens d'entrée, 88/92 de sortie. Préparation seule, aucun SQL/SOAP dans ce script.
- Navigateur réel + backend + SELECT TEST : **ordinateur et mobile réussis**. Demande exacte puis « Créer l'article », un seul brouillon, aucun appel modèle, aucun endpoint d'approbation/SAVE. Deux échanges : 3,010 s et 3,948 s. Les données NEG/UN/201/20/stock 1 sont vérifiées dans la réponse persistée. `peinture-live-browser.json`.
- Le bundle servi contient les nouveaux contrôles et aucune ancienne phrase de limitation EXT_POUDRE. Preuve du cache-control, nom et SHA256 JS : `peinture-served-ui.json`.
- Tests contrôlés : extraction courte/listes, enum stock, fournisseur facultatif/obligatoire, stock autorisé/refusé, sécurité HTTP423, approbation valide/expirée, SAVE simulé réussi/refusé, comparaison SQL, parent absent, aucune création implicite de l'enfant.
- La suite CPJ reste exécutée, notamment les succès/refus article-site séparés, les corrections invalidant l'approbation et les cas de résultat ambigu. Le navigateur contrôlé du parcours général est relancé. Ces transports simulés ne constituent pas des créations Sage réelles.
- Non-régression backend complète, dont 1 000 scénarios de contrat, tests frontend et build exécutés. Les trois tests locaux de subprocessus exclus de la frontière ERP isolée sont exécutés séparément. La précédente campagne de 100 conversations n'est pas présentée comme une nouvelle exécution de ce correctif.

## Sécurité et résultat réel

Les contrôles actuels sont toujours :

| Contrôle | Action nécessaire |
|---|---|
| `CA_CRL_MATERIAL_REQUIRED` | Obtenir la CRL signée, valide et à jour de SAGE-CA-2, puis vérifier la chaîne et la révocation strictement. |
| `VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED` | Valider les droits et preuves du compte AIAGT et une politique limitée aux opérations TEST autorisées. |
| `WRITES_DISABLED` | Autoriser l'activation des écritures seulement après validation des autres prérequis et du référentiel métier. |

Demande administrative déjà prête : `docs/DEMANDE-ADMIN-PKI-AIAGT-20261030.md`. Pas de nouvelle sollicitation de CRL à l'utilisateur final. Aucun contournement TLS, révocation ou HTTP423. Aucun certificat/droit/politique modifié. Aucun service de production redémarré ; seul le backend local agent a été rechargé après vérification qu'aucune analyse récente n'était en cours.

**Résultat réel : PEINTURE-ACRYLIQUE-B non créé.** WS_ARTICLE et WS_AR_SITE sont intégrés au parcours général, mais l'exécution réelle stricte reste bloquée par les prérequis ci-dessus et la revue des règles applicables. Aucun succès de création réelle n'est revendiqué. Une approbation humaine des données finales sera nécessaire avant tout futur SAVE.
