# Correction prioritaire Modern Foam — 28 octobre 2026

## Périmètre et résultat

La conversation jointe `1d687515-957f-482e-b7d4-c32abdbc5b52/Pasted text.txt` a été analysée. Les corrections portent sur la compréhension, la mémoire et l'affichage. Aucune création réelle Sage, aucun SQL DML Sage, aucune modification des droits, certificats ou connecteurs d'écriture.

Le rejeu de 14 messages passe : deux articles conservés, site 201, M2, sans fournisseur, catalogue avec intitulés, réponse AGEN, répétition AGEN puis corrections successives. Les valeurs métier restent distinctes des limites de création. Ce résultat ne certifie pas la création réelle ni toutes les formulations possibles.

## Causes et corrections

| Constat | Cause vérifiée et correction | Code |
| --- | --- | --- |
| Demandes de noms ignorées | La détection exigeait notamment le pluriel exact `categories` et ne reconnaissait pas `DONNER`, `lisert`, `catigorier`, `cztigorier`. Ces variantes déclenchent maintenant une consultation en lecture, sans mutation métier. | `backend/app/services/chat_turns.py`, `analyse`, lignes 18–21 ; `chat_fast_extract.py`, `extract` |
| AGEN sans effet | L'extracteur court ne liait pas ce code à la question catégorie en attente. Il le lie maintenant à `pending.categorie`, puis applique les contrôles SQL habituels. Répéter le code déjà retenu est sans effet métier. Un code fournisseur F1025 reste un fournisseur. | `chat_turns.py`, `analyse`, lignes 35–40 ; `chat_fast_extract.py`, `extract`, lignes 13–14 |
| Catalogue incomplet | `TOP (21)` tronquait la lecture à 21 lignes. Suppression de cette limite pour la requête fixe et paramétrée de catégories TEST. La demande explicite du catalogue contourne le cache de références. | `scripts/chat_sql_queries.ps1`, branche `get_article_categories`, ligne 7 ; `backend/app/services/chat_tools.py`, `pooled`, lignes 52–59 |
| Carte contradictoire | Un texte frontend codé en dur affichait site 202, NEG et M2 pour les codes MFB, alors que les champs réels pouvaient afficher AR et aucun site. Texte supprimé ; les valeurs métier sont celles du brouillon. | `frontend/src/ChatApp.jsx`, composant `Article`, ligne 16 et rendu des champs ligne 18 |
| Site redemandé | Le code actuel conserve déjà le site de la phrase combinée « site 201 … pas de fournisseur ». La capture ne permet pas d'établir quelle version était chargée lors de l'incident. Test ajouté sur la phrase exacte, la persistance et les réponses suivantes. Le site figure désormais aussi dans le tableau textuel. | `conversation_chat.py`, `_merge`, ligne 161 ; `questions`, ligne 465 ; `compose`, ligne 497 |
| Article confondu avec article-site | Le parcours enfant existait seulement pour EXT_POUDRE. Ajout d'un état explicite de préparation article-site aux contrôles et d'une explication séparée sur chaque carte. Une fiche retrouvée reste « champs non comparés », jamais validée sur la seule présence de l'article. | `conversation_chat.py`, `validate_article_draft`, lignes 368 et 410 ; `ChatApp.jsx`, `Article`, lignes 16 et 27 |

Les schémas `Patch` et `Delta` possédaient déjà catégorie, unité et site : aucune migration ni élargissement de schéma n'était nécessaire. Les sources des champs, invalidations et corrections restent gérées par `merge` et `chat_semantics.record_changes`. La relecture API après persistance est vérifiée dans le nouveau test d'intégration.

## Référentiel réellement consulté

Le worker SQL existant a exécuté uniquement `get_article_categories` sur TEST.ITMCATEG : **39 lignes** retournées, succès de lecture. Preuve : [modern-foam-real-categories.json](modern-foam-real-categories.json).

AGEN porte l'intitulé **AGENCEMENTS ET AMENAGEMENTS**. Les unités par défaut de cette catégorie sont UN. Cela ne remplace pas la demande M2 et ne prouve pas que toutes les règles métier autorisent AGEN/M2. L'application conserve M2, affiche ce qui est vérifié et maintient les restrictions d'écriture.

## Exécutions et preuves

| Vérification exécutée | Résultat | Preuve |
| --- | --- | --- |
| Reproduction initiale | 5 échecs, 2 réussites ; deux cas accentués étaient altérés par l'encodage stdin Windows et ont été corrigés avant la validation. Les deux phrases fautives fournies et AGEN reproduisaient bien le défaut. | `modern-foam-before.xml` |
| Premier correctif et régressions mémoire | 26 réussites | `modern-foam-cycle-01.xml` |
| Rejeu API et PostgreSQL isolé | 14 réussites avant ajout du contrôle de fraîcheur du catalogue | `modern-foam-cycle-02.xml` |
| Régression ciblée, dont 1 000 scénarios | 1 102 réussites | `../modern-foam-final-regression.xml` |
| Première régression complète | 1 377 réussites, 1 échec de compatibilité du tableau, 3 ignorés, 7 exclus. L'ajout du site avait déplacé les colonnes existantes ; le site est maintenant ajouté en dernière colonne. | `../modern-foam-full-regression.xml` |
| Régression complète après correction | **1 382 réussites, 3 ignorés, 4 exclus** | `../modern-foam-full-cycle-02.xml` |
| Rejeu de 14 messages | **14/14**, état et réponses contrôlés ; aucun appel d'extraction Qwen nécessaire pour ces formulations déterministes | `../conversations/20261028T095648Z/modern-foam-priority.json` et son manifeste |
| Build Vite et navigateur Edge, ordinateur/mobile | Réussis ; API entièrement simulée, aucune mutation backend | `modern-foam-browser.json`, captures `modern-foam-desktop.png` et `modern-foam-mobile.png` |
| Parcours frontend fournisseurs/clients existants | Réussi | `reliability-browser.json` |

Le rejeu utilise les vrais extracteurs et la vraie mémoire PostgreSQL dans un schéma isolé. Il utilise l'instantané réel de catégories ci-dessus ; les autres résultats SQL Sage restent simulés. Il ne constitue pas une conversation avec une personne réelle. Le worker réel a été contrôlé séparément en lecture seule.

Commandes depuis la racine :

```powershell
.\backend\.venv\Scripts\python.exe scripts/run_isolated_regression.py tests -q -k 'not stream_retains and not powershell_dpapi_roundtrip and not powershell_standalone_securestring and not project_environment_is_independent' --junitxml=../tests/ai-evaluation/modern-foam-full-cycle-02.xml
.\backend\.venv\Scripts\python.exe scripts/evaluate_modern_foam_readonly.py
```

Le test streaming exclu du dernier cycle figure dans le cycle ciblé réussi. Les tests système Windows exclus ont leurs preuves antérieures séparées ; ils ne sont pas comptés comme réussites de ce cycle. Les résultats historiques sont conservés.

## Parcours article-site et limites maintenues

1. Conserver le site demandé dans le brouillon et vérifier son existence et l'applicabilité de la catégorie.
2. Vérifier l'existence de l'article maître et de la fiche article-site, séparément.
3. Préparer les champs et le XML de la fiche enfant dans le périmètre autorisé.
4. Obtenir une approbation spécifique des données article-site et invalider l'approbation en cas de correction.
5. Effectuer au plus l'écriture approuvée, puis relire et comparer les champs attendus. Une erreur de communication laisse le résultat incertain, sans relance aveugle.

Ce parcours est décrit et représenté dans les contrôles. **Son exécution existante reste limitée à EXT_POUDRE** dans `sage_article_sites.worker/action` ; aucune extension aux articles MFB ni aux vingt articles n'a été appliquée. Les règles TEST/NEG/UN du parcours générique restent des restrictions du connecteur, distinctes des valeurs AGEN/M2/site 201 demandées. La préparation métier n'accorde aucune autorisation de SAVE.

Le défaut sensible antérieurement reproduit sur une fiche article-site déjà existante reste ouvert : le connecteur peut annoncer une relecture confirmée sans comparer les champs. Voir `PROPOSITION-CORRECTIONS-CONNECTEURS.md` et la proposition de patch non appliquée. Aucun succès de création article-site n'est revendiqué dans cette phase.

Le lot de vingt articles reste non approuvé : l'utilisateur a demandé des corrections de fiches. Les droits SQL excessifs observés restent également à traiter séparément. Aucun de ces blocages n'est contourné par les corrections du chat.
