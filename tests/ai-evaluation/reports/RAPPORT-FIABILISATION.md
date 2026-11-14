# Fiabilisation Agent Sage X3 — rapport de progression vérifié

Mission incomplète. Les résultats ci-dessous proviennent de fichiers effectivement produits par les exécutions.

## Architecture actuelle

React → API FastAPI (travail asynchrone et statut) → demande originale PostgreSQL → extraction locale ou Qwen → checkpoint des brouillons → outils SELECT prédéfinis → validation et dépendances → réponse. Les fiches fournisseurs/clients sont des brouillons distincts ; aucun nouveau service d’écriture n’est activé.

Les expériences sont enregistrées uniquement lors de la relecture explicite d’un brouillon. La récupération combine mots et similarité de caractères, reste isolée par propriétaire et ne constitue aucun entraînement.

## Résultats exécutés

| Rapport | Tests | Échecs | Erreurs | Ignorés |
|---|---:|---:|---:|---:|
| all-isolated-cycle-01.xml | 1363 | 0 | 0 | 3 |
| all-isolated-cycle-02.xml | 1369 | 0 | 0 | 3 |
| all-isolated-cycle-03.xml | 1371 | 0 | 0 | 3 |
| all-offline-cycle-01.xml | 1359 | 0 | 0 | 119 |
| all-offline-cycle-02.xml | 1361 | 0 | 0 | 119 |
| baseline.xml | 12 | 10 | 0 | 0 |
| campaign-cycle-01.xml | 1000 | 26 | 0 | 0 |
| campaign-cycle-02.xml | 1181 | 0 | 0 | 6 |
| campaign-cycle-03.xml | 1061 | 0 | 0 | 0 |
| campaign-cycle-04.xml | 1025 | 0 | 0 | 0 |
| campaign-cycle-05.xml | 1025 | 0 | 0 | 0 |
| campaign-cycle-06.xml | 1025 | 0 | 0 | 0 |
| campaign-cycle-07.xml | 1028 | 0 | 0 | 0 |
| campaign-cycle-08.xml | 1037 | 0 | 0 | 0 |
| campaign-cycle-09.xml | 1032 | 0 | 0 | 0 |
| campaign-cycle-10.xml | 1028 | 0 | 0 | 0 |
| campaign-cycle-11.xml | 1045 | 0 | 0 | 0 |
| campaign-cycle-12.xml | 1033 | 0 | 0 | 0 |
| cycle-01.xml | 40 | 3 | 0 | 0 |
| cycle-02.xml | 50 | 2 | 1 | 0 |
| cycle-03.xml | 49 | 1 | 0 | 0 |
| cycle-04.xml | 49 | 0 | 0 | 0 |
| cycle-05.xml | 61 | 0 | 0 | 0 |
| cycle-06.xml | 181 | 0 | 0 | 6 |
| integration-cycle-01.xml | 164 | 8 | 0 | 0 |
| integration-cycle-02.xml | 164 | 0 | 0 | 0 |
| integration-cycle-03.xml | 164 | 0 | 0 | 0 |
| memory-budget-cycle-01.xml | 27 | 0 | 0 | 0 |
| modern-foam-final-regression.xml | 1102 | 0 | 0 | 0 |
| modern-foam-full-cycle-02.xml | 1385 | 0 | 0 | 3 |
| modern-foam-full-regression.xml | 1381 | 1 | 0 | 3 |
| nettoyant-full-cycle-01.xml | 1426 | 0 | 0 | 3 |
| partner-review-integration-cycle-01.xml | 1 | 0 | 0 | 0 |
| partner-review-integration-cycle-02.xml | 5 | 0 | 0 | 0 |
| partners-baseline.xml | 12 | 4 | 0 | 0 |
| recipe-integration-cycle-01.xml | 2 | 0 | 0 | 0 |
| recipe-offline-cycle-01.xml | 1042 | 0 | 0 | 0 |
| timeout-multi-full-cycle-01.xml | 1411 | 0 | 0 | 3 |
| timeout-multi-full-cycle-02.xml | 1417 | 0 | 0 | 3 |
| timeout-multi-full-cycle-03.xml | 1418 | 0 | 0 | 3 |
| timeout-multi-full-cycle-04.xml | 1420 | 0 | 0 | 3 |
| windows-local-security-cycle-01.xml | 2 | 0 | 2 | 0 |
| windows-local-security-cycle-02.xml | 14 | 0 | 0 | 0 |

Les cycles se recouvrent : ne pas additionner leurs nombres pour prétendre à autant de scénarios distincts. La campagne dédiée contient 1 000 cas paramétrés dans 11 domaines ; elle ne mesure pas à elle seule la compréhension libre de Qwen.

## Conversations simulées

| Cycle | État | Terminées | Réussies | Tours | Échecs de tours | Appels réels Qwen |
|---|---|---:|---:|---:|---:|---:|
| conversations\20261028T085109Z | completed | 10 | 8 | 79 | 5 | 24 |
| conversations\20261028T090543Z | cancelled_superseded | 65 | 65 | 509 | 0 | 12 |
| conversations\20261028T092109Z | completed | 100 | 99 | 790 | 1 | 9 |
| conversations\20261028T093819Z | completed | 1 | 1 | 7 | 0 | 1 |
| conversations\20261028T095648Z | completed | 1 | 1 | 14 | 0 | 0 |
| conversations\20261028T103706Z | completed | 1 | 0 | 1 | 1 | 1 |
| conversations\20261028T104324Z | completed | 1 | 0 | 1 | 1 | 0 |
| conversations\20261028T104620Z | completed | 1 | 1 | 1 | 0 | 0 |
| conversations\20261028T110008Z | completed | 100 | 100 | 790 | 0 | 0 |
| conversations\20261028T111236Z | completed | 100 | 100 | 790 | 0 | 0 |
| conversations\20261028T151457Z | completed | 100 | 100 | 790 | 0 | 0 |

Les utilisateurs sont simulés. SQL et SOAP sont simulés dans ces conversations ; PostgreSQL et les appels Qwen identifiés par leur provenance sont réels. Une revue humaine de la pertinence des réponses reste nécessaire.

Consolidation des mêmes entrées et attentes : 100 conversations distinctes, 100 réussies au premier cycle complet, 100 réussies après les rejeux identifiés. Le premier échec de délai reste conservé.

## Corrections et vérifications

- Corrections explicites conservées en présence de questions ; catégories et unités de destination correctement distinguées des anciennes valeurs.
- Absence et facultativité du fournisseur distinguées ; cibles d’articles et de tiers séparées.
- Conventions de codes locales à la conversation ou à une sélection ; contrôles de longueur et de disponibilité conservés.
- Historique des valeurs et exemples relus, sans apprentissage automatique de règles métier.
- Désignations contenant CONTROLE traitées comme données plutôt que commandes.
- Catalogue de catégories lu dans TEST avec codes et intitulés, sans l’ancienne limite de 21 lignes ; les indisponibilités restent explicites.
- Demande AHMNDE multi-opérations reproduite ; champs juridiques, brouillons dépendants et reprise après interruption vérifiés. Voir RAPPORT-TIMEOUT-MULTI-OPERATIONS.md.
- Tests de doublons, approbations, réémissions et résultats article-site ambigus exercés en simulation.

## Sécurité et recette réelle

Aucun SAVE réel dans ces travaux. Les lectures TEST ont confirmé l’absence des 20 codes proposés et leurs couples article-site. Les données restent non approuvées : l’utilisateur demande des corrections.

Le lecteur SQL possède INSERT/UPDATE sur TEST.ITMMASTER, TEST.ITMFACILIT, TEST.BPSUPPLIER et TEST.BPCUSTOMER. Aucun de ces droits n’a été utilisé ni modifié. Leur correction exige une décision séparée.

La politique d’écriture, les certificats, la révocation et les privilèges restent inchangés. Le connecteur article-site est toujours borné à EXT_POUDRE. Le rapport RAPPORT-20-CREATIONS-REELLES.md contient les propositions et les blocages.

**Défaut sensible reproduit et non corrigé :** le retour ALREADY_EXISTS du connecteur article-site peut confirmer la relecture sans comparer les champs attendus. La simulation UN attendu / M2 existant retourne ReadConfirmed=true. Preuve : failures/existing-site-mismatch-simulation.json. Le patch proposé dans reports/PROPOSITION-ARTICLE-SITE-READBACK.patch reste non appliqué, en attente d’une approbation distincte.

## Fichiers applicatifs et tests modifiés ou ajoutés

- `backend/app/api/chat.py` — modified
- `backend/app/schemas/conversation_entities.py` — new
- `backend/app/services/chat_article_requests.py` — new
- `backend/app/services/chat_experiences.py` — new
- `backend/app/services/chat_fast_extract.py` — modified
- `backend/app/services/chat_jobs.py` — new
- `backend/app/services/chat_model.py` — modified
- `backend/app/services/chat_multi_operations.py` — new
- `backend/app/services/chat_partners.py` — new
- `backend/app/services/chat_performance.py` — modified
- `backend/app/services/chat_semantics.py` — new
- `backend/app/services/chat_tools.py` — modified
- `backend/app/services/chat_turns.py` — modified
- `backend/app/services/conversation_chat.py` — modified
- `backend/tests/test_article_agent.py` — modified
- `backend/tests/test_evaluation_campaign.py` — new
- `backend/tests/test_modern_foam_priority.py` — new
- `backend/tests/test_multi_operations.py` — new
- `backend/tests/test_nettoyant_multisite.py` — new
- `backend/tests/test_partner_conversation.py` — new
- `backend/tests/test_partner_review_integration.py` — new
- `backend/tests/test_recipe_partial_workflow.py` — new
- `backend/tests/test_recipe_robustness.py` — new
- `backend/tests/test_reliability_regressions.py` — new
- `backend/tests/test_supplier_confirmation.py` — modified
- `backend/tests/ai-evaluation/reports/modern-foam-before.xml` — new
- `frontend/src/analysisJobs.js` — new
- `frontend/src/ChatApp.jsx` — modified
- `frontend/tests/analysisJobs.test.mjs` — new
- `frontend/tests/modern-foam-mocked-browser.mjs` — new
- `frontend/tests/multi-operations-live-readonly-browser.mjs` — new
- `frontend/tests/multi-operations-mocked-browser.mjs` — new
- `frontend/tests/nettoyant-live-readonly-browser.mjs` — new
- `frontend/tests/reliability-mocked-browser.mjs` — new
- `scripts/chat_sql_queries.ps1` — modified
- `scripts/diagnose_multi_operations.py` — new
- `scripts/evaluate_human_conversations.py` — new
- `scripts/evaluate_modern_foam_readonly.py` — new
- `scripts/evaluate_multi_operations_readonly.py` — new
- `scripts/exercise_multi_operations_http.py` — new
- `scripts/export_evaluation_evidence.py` — new
- `scripts/prepare_twenty_agent_offline.py` — new
- `scripts/prepare_twenty_readonly.ps1` — new
- `scripts/probe_existing_site_simulation.ps1` — new
- `scripts/report_reliability.py` — new
- `scripts/report_twenty_preparation.py` — new
- `scripts/run_isolated_regression.py` — new
- `scripts/run_offline_regression.py` — new

## Travail restant

- human review of language quality pending
- SQL reader table INSERT/UPDATE privileges require separate approval
- customer publication not observed
- write connector changes require separate approval
- existing article-site readback mismatch reproduced; connector correction not approved/applied
- real20 exact data changes requested by user

Les parcours d’écriture fournisseurs/clients et la recette réelle ne sont pas déclarés opérationnels. Les limitations restantes ne sont pas compensées par des succès de simulation.
