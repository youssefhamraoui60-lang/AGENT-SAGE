# Fournisseur F10022 : observation OB, préparation vérifiée dans TEST

Vérification du 28 octobre 2026. OB a été exclusivement consulté. Aucune création Sage, aucun INSERT/UPDATE/DELETE, aucun changement de droits, certificat ou politique de sécurité. Les écritures locales concernent le code, les brouillons PostgreSQL de test et les preuves.

## Résultat et incident reproduit

La demande exacte « Bonjour, Merci de créer ce nouveau fournisseur : NOM : DROGUERIE PALMERAIE ICE: 001850814000094 IF : 20734927 RC : 10909 » est désormais extraite littéralement, sans appel au modèle. La variante « Crée un fournisseur DROGUERIE PALMERAIE, ICE 001850814000094, IF 20734927, RC 10909. » est également couverte. Les zéros initiaux de l'ICE sont conservés. Aucun capital, forme juridique, année ou code comptable n'est inventé.

L'échec historique de cette conversation était une extraction invalide, pas un timeout : le modèle avait omis le nom et produit notamment une forme SAS, une année 2023 et un code comptable correspondant à l'IF. Le garde-fou `partner_name_required` a rejeté ces données. Mesures conservées : un appel IA, HTTP 26 857,557 ms, extraction 26 872,951 ms, backend 26 919,847 ms ; chargement 4,6534 ms ; 1 270 tokens entrants, 141 sortants ; génération 26 625,681 ms. Preuve : `reports/supplier-original-extraction-failure.json`. Le chemin littéral corrigé utilise zéro appel IA pour ces formulations ; ce résultat ne démontre pas la qualité générale du modèle.

**Une création supplémentaire serait actuellement incorrecte : dans TEST, le fournisseur `DROGUERIEPALME`, nommé `erreur`, possède déjà ces ICE, IF et RC.** Le tiers/client `C06952`, nommé DROGUERIE PALMERAIE, possède également les mêmes ICE et IF. Cette correspondance entre rôles impose un examen ; aucune fusion, correction du nom ou création n'est exécutée automatiquement. Ces lignes préexistaient à la campagne ; leur origine n'est pas attribuée à l'agent.

## Mapping SQL réellement lu

Les lignes complètes de `OB.BPSUPPLIER` et `OB.BPARTNER` ont été consultées, ainsi que les métadonnées et les référentiels des deux dossiers. Les preuves brutes restent locales dans `runtime/supplier-ob-audit/`, non publiées avec le code. Leurs empreintes figurent dans `reports/supplier-ob-counter-safety.json`.

| Information | Colonne réelle | Valeur OB F10022 | Traitement du chatbot |
|---|---|---|---|
| Code fournisseur | BPSUPPLIER.BPSNUM_0 | F10022 | Identité existante, jamais copiée en nouveau code |
| Code tiers associé | BPARTNER.BPRNUM_0 | F10022 | Jointure fournisseur/tiers |
| Nom fournisseur | BPSUPPLIER.BPSNAM_0 | DROGUERIE PALMERAIE | Nom déclaré, rapprochement avec le tiers |
| Nom tiers | BPARTNER.BPRNAM_0 | DROGUERIE PALMERAIE | Prévisualisation du tiers |
| Nom court | BPSUPPLIER.BPSSHO_0 | DROGUERIE, espace final stocké | Ne pas tronquer/copier sans validation |
| ICE | BPARTNER.XICE_0 | 001850814000094 | Chaîne de 15 chiffres, recherche exacte |
| IF | BPARTNER.XIF_0 | 20734927 | Chaîne, maximum physique 10 caractères |
| RC | BPARTNER.XRC_0 | 10909 | Chaîne, maximum physique 10 caractères |
| Catégorie fournisseur | BPSUPPLIER.BSGCOD_0 | FR | Suggestion issue du dossier cible |
| Devise | BPSUPPLIER.CUR_0 | MAD | Référence cible contrôlée, non appliquée automatiquement |
| Condition paiement | BPSUPPLIER.PTE_0 | CHQ00 | Suggestion, applicabilité à confirmer |
| Régime taxe tiers | BPSUPPLIER.VACBPR_0 | MAR | N'est ni un taux TVA ni une validation fiscale externe |
| Code comptable | BPSUPPLIER.ACCCOD_0 | STD | N'est pas l'IF |
| Actif fournisseur et tiers | BPSUPPLIER/BPARTNER.ENAFLG_0 | 2 | Menu local 1 : 1 Non, 2 Oui |
| Rôle fournisseur | BPARTNER.BPSFLG_0 | 2 | Fournisseur Oui |
| Rôle client de F10022 | BPARTNER.BPCFLG_0 | 1 | Client Non pour ce tiers ; C06952 est distinct |
| Adresse par défaut | BPSUPPLIER/BPARTNER.BPAADD_0 | AD | Adresse à contrôler séparément |
| Auteur/date création | BPSUPPLIER.CREUSR_0/CREDATTIM_0 | ADMIN / 2026-10-28T11:11:50 | Audit observé, jamais reproduit comme saisie |

XICE est `nvarchar(15)`, XIF et XRC `nvarchar(10)`, dans les deux dossiers. Ils ne sont ni calculés ni identités et n'ont pas de défaut SQL observé. Leur SQL NOT NULL ne démontre pas une obligation de saisie métier : des chaînes vides existent. Les contrôles numériques implémentés sont des contrôles de forme et de cohérence interne ; aucune vérification DGI, registre du commerce ou authenticité juridique n'a été réalisée.

## Activation, adresses, contacts et paiement

Le dictionnaire installé ATABZON rattache ENAFLG au menu local 1 ; APLSTD confirme 1 Non et 2 Oui. **Ne pas confondre CREMOD=2**, qui utilise le menu 223 et signifie « Avec Validation ». La documentation Sage décrit l'activité du fournisseur comme une condition d'utilisation dans les documents : [GESBPS V12](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESBPS.htm).

Une adresse OB.BPADDRESS : BPATYP=1 (Tiers, menu 943), BPAADD=AD, BPAADDFLG=2 (adresse par défaut), libellé et première ligne `134 LOT IMINWADAY H RDC`, pays MA/Maroc. Ville et code postal vides. Les champs téléphone/mobile/web sont vides. Aucun CONTACT ni CONTACTCRM associé n'a été trouvé ; CNTNAM est vide. Cela décrit cette fiche, sans prouver que toute adresse ou tout contact est universellement facultatif. TEST.F10022 est absent : zéro adresse/contact sous ce code n'est pas une anomalie.

CHQ00 existe indépendamment dans OB et TEST : « Chèque Comptant », méthode CHQ, échéance 100 %, zéro mois et zéro jour. La législation stockée est **FRA**, malgré le pays MA/devise MAD : son applicabilité à la société cible reste à valider. L'existence d'un code et son usage historique ne suffisent pas à certifier sa conformité.

## Comparaison OB / TEST

| Contrôle | OB | TEST | Conséquence |
|---|---|---|---|
| Fournisseur F10022 | Présent | Absent | Pas de copie automatique |
| Même identité fiscale | F10022 et tiers/client C06952 | Fournisseur DROGUERIEPALME nommé erreur, tiers/client C06952 | Bloquer une nouvelle création et demander examen |
| Catégorie FR | Fournisseurs | Fournisseurs | Tous les champs métier de catégorie comparés sont identiques ; audit technique exclu |
| Valeurs catégorie | MA, MAD, CHQ00, MAR, STD ; REFCOU vide ; CREMOD 2 | Mêmes valeurs | Relecture du dossier cible obligatoire |
| Échantillon récent FR | 8 fournisseurs | 8 fournisseurs | 8/8 utilisent MAD, CHQ00, MAR, STD dans chaque dossier ; ce n'est pas une règle universelle |
| Références | Consultées | MAD, MA, CHQ00, MAR actif et STD type 3 vérifiés | Cohérence référentielle, pas validation complète société/législation |
| Plus grand suffixe F numérique observé | 10022 | 10012 | Maximum observé, pas allocation officielle |
| Compteur AVALNUM XBPS | 1033 avant et après | 1033 avant et après | Aucun compteur consommé |
| Publication fournisseur | Non inspectée pour écriture | Description locale WS_FOURNIS inspectée | Mapping OB non certifié ; aucune écriture autorisée |

La catégorie fournit des paramètres proposés et peut porter un compteur selon le paramétrage : [catégories V12](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESBSG.htm). Le moteur garde ces valeurs dans les suggestions avec `confirmed=false`, sans remplacer les champs déclarés.

## Numérotation : conclusions et limites

Les codes ont été triés par suffixe numérique, non par ordre lexical, dans BPSUPPLIER et BPARTNER. F10022 n'est pas supposé être le dernier créé. Dans TEST, F1115 est plus récent que F10012 ; le fournisseur le plus récent observé utilise aussi un code non F.

ACODNUM décrit BPS sous forme BPS- suivi de six chiffres, et XBPS sous forme F suivi de quatre chiffres. AVALNUM XBPS vaut 1033 dans les deux dossiers. REFCOU de FR est vide. Aucune affectation BPS/XBPS n'a été trouvée dans les onze lignes TABCOUAFF lues par dossier ; cela n'exclut ni une logique spécifique ni un autre contexte. Les affectations peuvent dépendre du contexte société/législation : [GESTCA V12](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESTCA.htm). **Le prochain numéro officiel n'est donc pas établi.**

Le moteur peut seulement présenter dans TEST, pour un fournisseur sans doublon et sans erreur, une proposition manuelle basée sur le maximum F numérique du dossier cible et dont l'absence est relue dans les deux tables. Elle est marquée non réservée, non officielle et convention stricte non confirmée. Le candidat observé F10013 n'est **pas proposé pour DROGUERIE PALMERAIE**, car des doublons existent. OB ne produit aucun candidat. Une future création nécessitera de vérifier le mode manuel autorisé ou d'utiliser l'allocation officielle Sage ; un MAX+1 n'est pas sûr face à la concurrence.

## Obligatoire, facultatif, automatique

- Le bot exige un nom pour préparer une fiche. Les identifiants fiscaux fournis sont conservés, contrôlés et utilisés pour les doublons ; leur obligation légale globale n'est pas déduite de cet exemple.
- Dictionnaire ATABZON, OBLIG=2 : BPSUPPLIER BPSNUM, CUR, PTE, VACBPR ; BPARTNER CUR ; BPSCATEG BSGCOD et CUR. Les autres champs sélectionnés ne présentent pas tous ce marqueur. Transactions, écrans et règles conditionnelles peuvent ajouter des obligations : cette liste ne certifie pas une charge utile de création complète.
- Contacts absents et ville/code postal vides sur l'exemple : valeurs non renseignées observées, pas permission universelle de les omettre.
- Numéro, auteur, date, UUID et identifiants techniques restent sous contrôle Sage selon le paramétrage. Ne jamais recopier ADMIN, la date historique ou F10022. BPSRSK=F10022 est un lien à soi observé, sans preuve d'une règle automatique universelle.
- Défauts de catégorie : suggestions à vérifier dans le dossier cible et à confirmer ; aucune copie automatique de FR/MAD/CHQ00/MAR/STD depuis OB.

Description SOAP locale TEST `runtime/crud-WS_FOURNIS-description.xml` : BPS0_1.BSGCOD, ENAFLG et BPSNUM sont des entrées ; BPSNAM est Display, donc pas un champ de saisie de nom à réutiliser aveuglément. BPRS_1 contient CUR, XICE (15), XIF (10), XRC (10) ; BPS2_1.ACCCOD, BPS2_2.PTE et BPS2_3.VACBPR sont des entrées. L'absence d'attribut OBL dans cette description ne certifie pas les obligations. La prévisualisation SQL du bot n'est pas une charge utile d'écriture SOAP validée. `creation_ready=false` reste explicite.

## Code corrigé et parcours

| Fichier et fonction | Rôle |
|---|---|
| backend/app/services/chat_supplier_preparation.py : literal_extract, ligne 6 | Extraction littérale NOM/ICE/IF/RC, dossier explicite, refus de PROD, aucun appel IA nécessaire pour le cas reproduit |
| Même fichier : prepare, ligne 36 | Doublons fiscaux, distinction fournisseur/tiers, contrôle de format, suggestions cible, proposition conditionnelle non réservée, blocages |
| backend/app/services/chat_partners.py : literal_extract (ligne 24), merge (ligne 107), tool_plan (ligne 173), validate (ligne 189), compose (ligne 220) | Intégration, répétition idempotente du même fournisseur, demandes de vérification, présentation et confirmation conditionnelle |
| backend/app/schemas/conversation_entities.py : schémas fournisseur | Champs structurés dossier OB/TEST, catégorie et régime ; identifiants fiscaux en chaînes |
| backend/app/services/chat_tools.py : registre et exécution des outils | Deux outils SQL frais, allowlist, dossier limité à OB/TEST |
| scripts/chat_sql_queries.ps1 : Get-ChatSelectQuery, lignes 17–18 | SELECT paramétrés de rapprochement fiscal et profil cible ; tables explicites, aucune mutation |
| scripts/chat_sql_worker.ps1 : paramètres et provenance | Folder/Ice/Fiscal/Rc contrôlés ; source SQL_OB ou SQL_TEST identifiable |
| backend/app/services/chat_multi_operations.py : résolution fournisseur | Réutilise le rapprochement fiscal au lieu de conclure absent sur le seul nom différent |
| backend/app/services/conversation_chat.py : traces d'outils | Reconnaît les lectures OB comme consultations réelles |
| frontend/src/SupplierPreparation.jsx : SupplierPreparation | Dossier, doublons, limites fiscales, suggestions non appliquées, état OB lecture seule |
| frontend/src/ChatApp.jsx : carte partenaire et état d'analyse | Affichage du même état ; ancien échec ne demande plus une reprise après une analyse terminée |
| scripts/inspect_supplier_ob_readonly.ps1 : Read-Only, ligne 11 | Audit borné en SELECT, schémas OB/TEST fixes, valeurs paramétrées |

Flux : message original persisté → extraction validée → brouillon conservé → recherches fiscales et profil frais du dossier cible → contrôle des résultats → carte cohérente → rapprochement ou confirmation demandée. Un défaut SQL ne doit pas effacer les informations déclarées. La validation de préparation ne déclenche jamais une écriture. Un changement de dossier relance les recherches sans réutiliser les paramètres de l'autre dossier.

## Vérifications exécutées

- `supplier-ob-full-cycle-03.xml` : **1 440 réussites, 3 ignorés, 4 exclus**, dont les 1 000 scénarios distincts et les nouveaux cas fournisseur. Deux cycles complets précédents sont conservés ; le dernier comprend le garde-fou supplémentaire sur les candidats de code.
- `conversations/20261028T160448Z/run_manifest.json` : **100/100 conversations simulées**, 790 tours ; source backend comparée aux empreintes du manifeste. Référentiels synthétiques fixes, zéro appel réel Qwen pour ces formulations ; ce ne sont pas 100 utilisateurs humains.
- `reports/supplier-ob-frontend.xml` : tests unitaires frontend ; le statut détaillé figure dans le XML.
- `reports/supplier-ob-live-ui.json`, captures desktop/mobile : vrai navigateur, vrai backend, lectures SQL réelles. Demande exacte → identifiants conservés → doublons TEST ; passage OB → F10022 et lecture seule ; retour TEST → références TEST. Aucune route de création ou d'approbation appelée.
- Tests dédiés `backend/tests/test_supplier_ob_preparation.py` : variantes exactes, IF distinct du code comptable, zéros initiaux, doublon avec nom erroné, tiers client, dossier OB explicite, refus PROD, profils manquants/incohérents, répétition sans second brouillon, candidat invalide et intégration PostgreSQL/API.
- `reports/supplier-ob-counter-safety.json` : compteurs XBPS inchangés avant/après, empreintes des lectures brutes.

Une requête initiale trop large de métadonnées de numérotation a dépassé le délai SQL de 15 secondes. L'échec est conservé dans `runtime/supplier-ob-audit/numbering.json` ; des requêtes plus ciblées ont ensuite abouti, sans augmenter le délai. Aucune erreur n'a été masquée en succès.

## Ce qui reste à décider avant une création future

Examiner le fournisseur TEST DROGUERIEPALME et le rôle du tiers C06952 ; confirmer le dossier, les données exactes, l'adresse, l'activation, la catégorie et l'applicabilité comptable/fiscale ; établir le compteur réellement affecté et la politique de code manuel ; valider le mapping d'écriture officiel du dossier cible et les obligations de sa transaction. L'utilisateur devra approuver la fiche exacte après ces contrôles. Rien dans ce rapport n'autorise une écriture OB ni ne valide le lot des vingt articles précédemment en attente.


## Correctif compl?mentaire : r?ponse ? cr?er le ?

Anomalie reproduite le 28 octobre 2026 : apr?s un brouillon fournisseur valide, `chat_turns.analyse` renvoie `creation_request` en lecture seule. `chat_fast_extract.extract` passait cet acte interne dans `Delta.speech_act`, dont l'?num?ration ne l'autorise pas. Pydantic levait donc une ValidationError avant tout appel Ollama. Ce nouvel incident ne provient ni de SQL ni d'un timeout.

Correction : `backend/app/services/chat_fast_extract.py`, fonction `extract`, traite l'acte avant les autres extractions, avec un Delta `approve` sans speech_act invalide. Cet intent signifie ici demande de pr?paration, sans autorisation d'?criture. Le merger conserve les brouillons et recontr?le les blocages. `backend/app/services/chat_partners.py`, fonction `compose`, explique explicitement que la demande est comprise, sans cr?ation, et que les blocages doivent ?tre r?solus.

Nouveaux tests : cinq formulations (? cr?er le ?, ? cr?e le ?, ? crrer le ?, ? cr?er le fournisseur ?, ? cr?er les fournisseurs ?), identit? du brouillon et identifiants conserv?s, z?ro appel IA et aucune approbation accord?e. Le test int?gr? PostgreSQL/API encha?ne aussi ? cr?er le ?, ? cr?er le fournisseur ?, puis ? ok ?, et v?rifie que le doublon continue de bloquer. Le navigateur r?el a ?t? rejou? sur ordinateur et mobile avec SELECT OB/TEST : analyse termin?e, m?me identifiant de fournisseur, aucune disponibilit? de cr?ation ni route d'?criture appel?e. Preuve actualis?e : `reports/supplier-ob-live-ui.json`. Le pr?c?dent cycle des 100 conversations appartient ? la version fournisseur pr?c?dente ; ne pas le pr?senter comme une nouvelle campagne de 100 sur ce correctif.

Le fournisseur n'a pas ?t? cr??. Les doublons pr?existants ne sont pas supprim?s ni fusionn?s. Aucune permission ni restriction n'a ?t? modifi?e.


Final verification: supplier-short-confirmation-full-final.xml = 1446 passed, 3 skipped, 3 subprocess tests deselected. Those 3 passed separately in supplier-short-confirmation-subprocess-local.xml. Frontend: 17 passed. Real desktop/mobile browser: PASS, including no-RC request on mobile. Initial boundary failures retained in supplier-short-confirmation-full.xml. No Sage writes.
