# Campagnes de fiabilisation

Les résultats de simulation ne prouvent pas qu'une création réelle fonctionne.
Les fichiers XML/JSON de chaque cycle restent conservés, y compris les échecs.

## Frontières des exécutions

- `scripts/run_offline_regression.py` interdit réseau, sous-processus et PostgreSQL. Seul le socketpair local requis par asyncio Windows est autorisé.
- `scripts/run_isolated_regression.py` ajoute uniquement PostgreSQL local `agent_sage` sur 55432, sous un nom de schéma de test explicitement contrôlé. Les appels SQL Server et SOAP sont simulés dans ces tests.
- `scripts/evaluate_human_conversations.py` ajoute uniquement Ollama à `127.0.0.1:11434`. L'extracteur réel et la mémoire PostgreSQL sont utilisés ; les résultats SQL sont des fixtures synthétiques. Aucune fonction d'écriture Sage n'est appelée.
- `scripts/prepare_twenty_readonly.ps1` consulte réellement SQL Server et les services SOAP existants, par SELECT/getDescription/READ seulement. Il ne contient aucune invocation SAVE.
- `scripts/prepare_twenty_agent_offline.py` confronte les 20 données proposées à l'extracteur et à la fusion réels de l'agent, sans modèle distant, SQL ni SOAP.

## Commandes reproductibles

Depuis `C:\AGENT-SAGE-X3` :

```powershell
& .\backend\.venv\Scripts\python.exe scripts/run_offline_regression.py tests -q -k 'not stream_retains and not powershell_dpapi_roundtrip and not powershell_standalone_securestring and not project_environment_is_independent' --junitxml=../tests/ai-evaluation/NOUVEAU-CYCLE.xml

& .\backend\.venv\Scripts\python.exe scripts/run_isolated_regression.py tests/test_conversation_chat.py tests/test_chat_performance.py tests/test_chat_save_bridge.py tests/test_sage_crud.py tests/test_article_agent.py tests/test_sage_powershell_chat.py tests/test_sage_article_sites.py tests/test_business_integration.py tests/test_sage_preparations.py tests/test_partner_review_integration.py tests/test_recipe_partial_workflow.py -q --junitxml=../tests/ai-evaluation/NOUVELLE-INTEGRATION.xml

& .\backend\.venv\Scripts\python.exe scripts/evaluate_human_conversations.py
& .\backend\.venv\Scripts\python.exe scripts/report_reliability.py
```

Chaque nouveau cycle doit recevoir un nom de sortie distinct pour conserver l'historique.
Ne pas relancer une conversation déjà active sous prétexte qu'une observation a expiré : vérifier d'abord son processus ou sa session d'exécution.

## Lecture des résultats

`test_evaluation_campaign.py` contient 1 000 cas paramétrés dans 11 domaines. Les variantes portent sur les opérations, les champs, les cibles, les cardinalités et les modes de panne. Cette campagne ne contient pas 1 000 appels réels Qwen.

Les conversations comportent de 7 à 15 tours, avec 10 parcours et des cardinalités/cibles de 1 à 10. Leurs entrées, attentes, états obtenus, réponses et provenances sont dans `conversations/<cycle>/`. Les personnes sont simulées ; aucune revue humaine du langage n'est automatiquement revendiquée.

La propriété `real_model_called` distingue un véritable appel Ollama d'une extraction déterministe. La validité JSON n'est pas le seul critère : les assertions vérifient les valeurs, leur conservation, la portée des corrections et l'absence d'approbation ou d'opération d'écriture.

Les tests ignorés ne sont pas comptés comme réussis. Les cycles se recouvrent : leurs nombres ne s'additionnent pas pour établir un nombre de scénarios distincts.

## Recette des 20 créations

Voir `RAPPORT-20-CREATIONS-REELLES.md`. Le lot proposé n'est pas approuvé : l'utilisateur a demandé de corriger certaines fiches. Aucun SAVE réel n'est autorisé sur la base de ce lot.

Le contrôle réel a également révélé des droits INSERT/UPDATE pour le lecteur SQL sur quatre tables TEST. Les droits, les certificats et les périmètres d'écriture restent inchangés ; toute adaptation sensible nécessite une approbation distincte.
