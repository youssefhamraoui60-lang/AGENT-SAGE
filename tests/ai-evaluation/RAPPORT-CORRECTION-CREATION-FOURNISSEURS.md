# Correction fournisseurs : identité, activation et confirmation après SAVE

28 octobre 2026. OB exclusivement en lecture seule. Aucune création, activation, modification, fusion ou suppression Sage effectuée. Aucun changement de politique, certificat, permission ou configuration.

## 1. Anomalies vérifiées

Lectures réelles de `x3v12.OB` et `x3v12.TEST`, preuves brutes locales dans `runtime/supplier-ob-audit/identity_status.json` ; relecture par l'outil applicatif dans `reports/supplier-activation-live-sql.json`.

| Dossier / code | Nom fournisseur et tiers | Actif fournisseur BPSUPPLIER | Actif tiers BPARTNER | Résultat |
|---|---|---:|---:|---|
| OB / F10022 | DROGUERIE PALMERAIE | 2 Oui | 2 Oui | Fiche existante cohérente avec le nom demandé ; ce n'est pas une nouvelle création de la campagne |
| TEST / DROGUERIEPALME | erreur | 1 Non | 2 Oui | Nom différent de la demande et fournisseur inactif malgré tiers actif |
| OB et TEST / C06952 | DROGUERIE PALMERAIE | Aucune fiche BPSUPPLIER associée | 2 Oui | Tiers/client distinct, BPSFLG=1 ; correspondance ICE et IF à examiner avant nouvelle fiche |

F10022 et DROGUERIEPALME sont des clés distinctes dans des dossiers différents. Ne pas les confondre ni renommer automatiquement l'une vers l'autre. Le rapprochement fiscal ne prouve pas une identité technique unique. F10022 n'est pas proposé comme nouveau code.

F10022 : nom court `DROGUERIE` (espace final stocké), catégorie FR, pays MA, devise MAD, paiement CHQ00, régime MAR, comptable STD, adresse AD avec première ligne `134 LOT IMINWADAY H RDC`, ville vide. Création et modification par ADMIN. TEST DROGUERIEPALME : nom court vide, mêmes paramètres de catégorie/devise/paiement/régime/comptable ; adresse 50000, première ligne/libellé/ville vides, pays MA ; création et modification par ADMIN. Les horodatages source exacts sont conservés dans le fichier de preuve, séparément pour le tiers et le fournisseur. Ils décrivent l'état lu, sans attribuer l'origine de ces fiches à l'agent.

Les anciennes observations doivent être conservées avec leur date ; le statut du tiers ne démontre jamais l'activation du fournisseur. La capture et la relecture actuelle concordent sur l'inactivation du fournisseur TEST.

Horodatages SQL relus comme chaînes ISO sans conversion de fuseau : OB/F10022 créé le 2026-10-28 à 11:11:50, modifié à 11:13:19 ; TEST/DROGUERIEPALME créé à 13:33:34, modifié à 13:42:35. Fournisseur et tiers portent ces mêmes horaires dans chaque fiche observée ; auteur ADMIN. Cela ne suffit pas à identifier le logiciel ou l'opérateur à l'origine de la saisie.

## 2. Mapping Actif et fiscal

Le dictionnaire installé ATABZON relie ENAFLG de BPSUPPLIER et BPARTNER au menu local 1. APLSTD français confirme **1 Non, 2 Oui**. Le contrôle doit porter sur les deux tables. Ne pas confondre le mode de création BPSCATEG.CREMOD=2 (« Avec Validation », menu 223) avec ENAFLG.

| Information | SQL | Entrée SOAP TEST observée |
|---|---|---|
| Code | BPSUPPLIER.BPSNUM_0 / BPARTNER.BPRNUM_0 | BPS0_1.BPSNUM |
| Nom | BPSUPPLIER.BPSNAM_0 / BPARTNER.BPRNAM_0 | BPRS_1.BPRNAM, liste de deux chaînes, première ligne nominale |
| Intitulé court | BPSSHO_0 / BPRSHO_0 | BPRS_1.BPRSHO, 10 caractères |
| Actif | BPSUPPLIER.ENAFLG_0 et BPARTNER.ENAFLG_0 | BPS0_1.ENAFLG : 2 pour Oui |
| ICE | BPARTNER.XICE_0 | BPRS_1.XICE, chaîne 15 |
| IF | BPARTNER.XIF_0 | BPRS_1.XIF, chaîne 10 |
| RC | BPARTNER.XRC_0 | BPRS_1.XRC, chaîne 10 |
| Catégorie | BPSUPPLIER.BSGCOD_0 | BPS0_1.BSGCOD |
| Pays / devise | BPARTNER.CRY_0 / CUR_0 | BPRS_1.CRY / CUR |
| Paiement / régime / comptable | BPSUPPLIER.PTE_0 / VACBPR_0 / ACCCOD_0 | BPS2_2.PTE / BPS2_3.VACBPR / BPS2_1.ACCCOD |

Les trois identifiants fournis se retrouvent dans F10022 OB et DROGUERIEPALME TEST. C06952 partage ICE et IF, sans RC renseigné. Aucun contrôle auprès de l'administration fiscale n'est revendiqué. IF n'est jamais code comptable. Aucune conversion numérique ne doit supprimer les zéros.

## 3. Corrections applicatives

- `backend/app/services/chat_supplier_preparation.py`, `literal_extract` et `prepare` : activation explicitement déclarée, catégorie/pays/devise structurés, rapprochements portant les deux états d'activation, écarts de nom explicites, refus du nom de substitution « erreur », intitulé court proposé séparément à confirmer. Les brouillons, historiques et identifiants restent conservés par `chat_partners.merge` ; aucune mutation d'une fiche existante.
- `backend/app/schemas/conversation_entities.py`, `PartnerPatch` : intitulé court borné à 10 caractères, identifiants fiscaux en chaînes ; activation conservée dans statut.
- `backend/app/services/chat_model.py`, `supplier_request_schema` et `extract` : schéma Qwen ciblé pour la création simple d'un fournisseur ; nom obligatoire, ICE/IF/RC obligatoires s'ils sont déclarés ; aucun champ article/index ou code comptable distracteur. Les demandes mixtes ou riches restent sur le schéma complet. Budget de sortie simple réduit à 400 tokens, sans augmenter le timeout.
- `scripts/chat_sql_queries.ps1`, `Get-ChatSelectQuery` : rapprochement frais avec activation fournisseur et tiers séparée ; nouvel outil `get_supplier_record` en SELECT paramétré, borné OB/TEST. `chat_tools` interdit les autres dossiers et ne met pas cette relecture en cache.
- `backend/app/services/supplier_xml.py`, `proposal` : XML relisible WS_FOURNIS selon description TEST vérifiée, BPRNAM sous forme liste, activation explicite, vrai code F numérique fourni et non dérivé du nom. Aucun SAVE. Champs requis non confirmés, dossier OB, mauvais mapping ou coordonnées non prises en charge : refus explicite au lieu d'omission silencieuse. L'XML n'est pas une certification des règles conditionnelles de la transaction.
- `backend/app/services/supplier_readback.py`, `verify` et `message` : après une tentative réellement autorisée, comparaison SOAP + SELECT frais TEST sur identité, nom, fiscalité déclarée, catégorie, pays, devise, activation des deux lignes et champs mappés. SAVE positif seul insuffisant ; réponse ambiguë jamais déclarée création réussie ; aucun réessai automatique. Téléphone/adresse ou seconde ligne de nom non vérifiés en SQL maintiennent un état incomplet.
- `backend/app/services/sage_crud.py`, `execute` : branche fournisseur create reliée à cette vérification ; statut précédemment succeeded rétrogradé unverified si preuve insuffisante. Approbation ponctuelle, consommation unique, sécurité et contrôles HTTP 423 existants conservés.
- React : `SupplierPreparation.jsx` signale l'inactivation et le nom incohérent ; `supplierResult.js` et `SupplierResult.jsx` n'affichent « créé et activé » qu'avec les preuves concordantes de l'opération réelle. Intégration au panneau CRUD et emplacement prévu sur la carte de fournisseur. Les cartes sans opération restent des brouillons. Aucun token technique demandé dans la conversation.

## 4. Essais Qwen réellement exécutés

Modèle local qwen2.5:7b, exécution CPU observée. Même campagne de trois messages, inférence forcée, aucun appel Sage ou SQL dans cet évaluateur.

| Cas | Avant : résultat / temps | Après schéma ciblé : résultat / temps | Tokens entrée / sortie après |
|---|---|---|---|
| Demande multiligne DROGUERIE PALMERAIE, ICE/IF/RC | Échec / 75,280 s | Conforme / 21,944 s | 193 / 91 |
| Demande avec Activation OUI, FR, MA, MAD | Échec / 22,510 s | Conforme / 25,704 s | 203 / 127 |
| Nom différent FOURNISSEUR SYNTHETIQUE ALPHA | Échec / 35,478 s | Conforme / 18,385 s | 192 / 92 |

Le deuxième cas n'est pas plus rapide ; l'amélioration vérifiée est la conformité de l'extraction. Les identifiants réutilisés dans le troisième message sont uniquement un stimulus d'extraction, jamais des données d'une nouvelle création réelle. Preuves : `reports/supplier-activation-real-qwen-before.json` et `reports/supplier-activation-real-qwen.json`, script `scripts/evaluate_supplier_activation_qwen.py`. Trois cas ne prouvent pas une fiabilité générale du modèle.

## 5. Tests contrôlés et navigateur

`backend/tests/test_supplier_activation_readback.py` : création active, inactivation de chaque rôle, nom erroné, mauvais code, fiscalité différente, absence SQL/SOAP, mauvais dossier, SAVE refusé/ambigu/avec avertissement, absence ou différence de paiement, pays/devise/catégorie, plusieurs lignes SQL, champs facultatifs absents, téléphone/adresse non encore mappés, panne SQL, rapprochements par ICE/IF/RC/nom, refus du nom « erreur », XML selon description réellement existante. Assertions sur le résultat métier et le message final ; aucun test simulé présenté comme création réelle.

`reports/supplier-activation-cycle-04.xml` : 61 réussites, incluant l'intégration PostgreSQL/API fournisseur. `reports/supplier-activation-cycle-03.xml` : 94 réussites sur le groupe fournisseur, performance et CRUD. Première régression complète `reports/supplier-activation-full-01.xml` : 1478 réussites, 3 ignorés, 3 tests sous-processus exclus. La seconde régression sur la version Qwen corrigée et les nouveaux tests figure dans `reports/supplier-activation-full-02.xml` ; consulter son total final avant d'en revendiquer un résultat.

Un essai ciblé exécuté hors du lanceur isolé a échoué sur une assertion de sécurité dépendante de l'environnement (`supplier-activation-cycle-02.xml`). Relancé avec les garde-fous réseau/Sage et le schéma PostgreSQL isolé : 94 réussites (cycle 03). Les artefacts d'échec restent conservés.

Frontend : `reports/supplier-activation-frontend.xml`, 28 tests réussis ; compilation Vite réussie. Navigateur réel ordinateur/mobile, backend réel et SELECT OB/TEST : `reports/supplier-ob-live-ui.json`, captures associées. Affichage fournisseur TEST inactif et nom différent, OB F10022 avec deux statuts actifs, réponses courtes conservant le brouillon ; aucune route d'approbation ou d'exécution appelée. La capture n'est pas une preuve de nouvelle création.

## 6. Démonstration honnête du parcours actuel

Utilisateur : « Bonjour, merci de créer un fournisseur : DROGUERIE PALMERAIE, ICE : 001850814000094, IF : 20734927, RC : 10909, Activation : OUI, Catégorie : FR, Pays : MA, Devise : MAD. »

Agent : brouillon conservé dans TEST, activation demandée ; fournisseur DROGUERIEPALME déjà présent, nom enregistré « erreur » différent, fournisseur inactif et tiers actif ; C06952 correspond également aux ICE/IF. Nouvelle création bloquée. Aucune modification automatique des fiches existantes.

Utilisateur : « créer le ».

Agent : demande comprise, mêmes identifiants et même brouillon conservés ; les doublons et blocages restent présents. Aucun SAVE ni activation effectué. Une relecture du brouillon n'est pas une approbation d'écriture.

Le texte « Fournisseur créé et activé avec succès » est couvert par des tests contrôlés avec code retourné F0012 et preuves synthétiques ; il n'est **pas** émis comme résultat d'une création réelle dans cette campagne. Le dossier OB ne reçoit jamais une nouvelle création.

## 7. Statut réel SOAP et limites

**SAVE réel : non exécuté. Zéro fournisseur créé ou activé par cette campagne.** Aucun jeu de données exact complet n'a reçu l'approbation spécifique requise.

Contrôle local de `sage_crud.security('suppliers','create')` : ready=false, WRITES_DISABLED, DEDICATED_TECHNICAL_ACCOUNT_REQUIRED, VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED. Aucune protection n'a été levée.

Une tentative autorisée de lecture SOAP de la fiche existante TEST/DROGUERIEPALME a été effectuée et arrêtée par `sage_crl_bundle_missing`, avant confirmation par le service. Preuve `reports/supplier-activation-live-soap-read.json`. La preuve actuelle d'activation est donc SQL + dictionnaire + capture fournie, pas une relecture SOAP réussie. Aucun certificat ou réglage TLS modifié pour contourner cet échec.

Restent bloqués : transport SOAP avec CRL disponible et validée, compte et preuves de sécurité autorisés, numérotation officiellement affectée ou saisie manuelle validée, obligations conditionnelles/adresses de la transaction, mapping complet téléphone/adresse et relecture SQL associée, approbation exacte du lot fictif, exécution et relecture réelle. Le chatbot reste un parcours de préparation pour les fournisseurs tant que ces conditions ne sont pas réunies. La présence de composants de résultat et d'un XML proposé ne rend pas le parcours de création opérationnel.

Les trois fournisseurs fictifs préparés précédemment restent à zéro création. Les vingt articles précédemment en attente ne sont toujours pas approuvés. Aucune correction des données OB/TEST existantes n'est autorisée implicitement par ce rapport.

## 8. Repères techniques

| Fichier | Fonction / ligne |
|---|---|
| backend/app/services/chat_model.py | supplier_request_schema : 108 ; extract : 126 |
| backend/app/services/chat_supplier_preparation.py | literal_extract : 6 ; prepare : 36 |
| backend/app/services/chat_partners.py | merge : 107 ; compose : 220 |
| backend/app/services/supplier_xml.py | proposal : 9 |
| backend/app/services/supplier_readback.py | verify : 19 ; message : 64 |
| backend/app/services/sage_crud.py | execute : 171 |

Les autres positions sont conservées dans `reports/supplier-activation-source-lines.json`. Le test `reports/supplier-verification-interruption.xml` confirme également qu'une exception de vérification après SAVE simulé est journalisée comme unverified et que l'approbation consommée ne permet pas un deuxième envoi.
