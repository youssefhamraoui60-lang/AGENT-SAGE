# Étape 2 — propositions métier locales

Le moteur ne possède aucun connecteur Sage X3, aucune chaîne de connexion SQL Server, aucun exécuteur
ni fonction de création distante. Toutes les réponses portent `execution_sage_autorisee=false`.
Même `approved_locally` signifie validation d'une proposition locale uniquement.

## Flux et isolation

1. FastAPI valide une demande de 3 à 8000 caractères et enregistre sa réception.
2. Le contexte RAG et jusqu'à deux petits exemples approuvés sont lus, puis la transaction est fermée.
3. Ollama Qwen 2.5 7B produit un objet JSON sous schéma, à température 0, avec au plus deux tentatives par défaut.
4. Pydantic vérifie la structure; les codes/sites doivent être cités, les désignations/noms préservés.
   Les réponses invalides ou incomplètes sont rejetées, jamais réparées silencieusement.
5. Un moteur indépendant consulte uniquement les référentiels locaux validés, détermine les champs manquants,
   compare les doublons et distingue `extrait` de `confirme` par source.
6. La proposition, les contrôles, le modèle/digest/version Ollama et le prompt versionné sont stockés.
7. Les corrections et décisions humaines sont des opérations distinctes, protégées par jeton local et révision attendue.

Le schéma `sage_ai` est distinct des tables de l'étape 1 dans `public` et de la base `n8n`.
Les tests PostgreSQL utilisent `sage_ai_test_*`, uniquement avec données et règles synthétiques;
ces schémas sont conservés et ignorés par l'API de service. Aucun test ne supprime des données existantes.

Tables: `schema_migrations`, `requests`, `request_events`, `reference_entries`, `knowledge_documents`, `knowledge_passages`.
Migration additive `database/003-business.sql`, copie empaquetée `backend/migrations/003-business.sql`.
Application transactionnelle, verrou de migration, vérification SHA256 et réexécution idempotente.
L'historique est append-only (trigger interdisant UPDATE/DELETE). Les corrections gardent l'extraction initiale.

## Référentiels et règles

Aucun référentiel Sage X3 validé n'est livré ou supposé. FG, MARCH, UN ou M3 ne sont pas déclarés universels.
Les références ont un type, code, libellé, aliases configurables, provenance et indicateur de validation.
Les références synthétiques sont exclues du service normal (`ALLOW_SYNTHETIC_REFERENCES=false`).
Une correspondance de référentiel confirme l'existence locale d'un code, pas son adéquation à la demande ni une existence Sage X3.
La décision humaine reste séparée et ne déclenche aucune exécution.

`backend/app/core/business-rules.json` définit les champs requis de préparation; `deployment_validated=false`
interdit toute approbation locale positive avant revue réelle des règles du déploiement.
Les champs fournisseurs supplémentaires sont configurables avec `informations.email`, `informations.adresse`, etc.
Ne pas passer ce drapeau à true à partir d'un résultat LLM ou d'un document non vérifié.

Import d'un fichier réellement fourni, depuis `backend`:

```powershell
.\.venv\Scripts\python.exe ..\scripts\step2_admin.py import-references C:\chemin\references-validees.json --validated
```

L'import est transactionnel, n'écrase pas les références existantes et nécessite une provenance.
`config/references.example.json` est un gabarit avec valeurs à remplacer, pas une base à importer telle quelle.

## API

- POST `/api/v1/ai/analyze`: analyse et persistance, sans approbation.
- POST `/api/v1/ai/validate`: contrôles de proposition, sans changement d'état.
- POST `/api/v1/ai/check-duplicates`: candidats exacts/normalisés/approximatifs, scores indicatifs, `local_only`.
- GET `/api/v1/ai/requests/{id}`: extraction initiale, proposition courante et historique.
- GET `/api/v1/ai/health`: DB, migration, modèle et statut du corpus.
- POST `/api/v1/ai/requests/{id}/corrections`: patchs humains par index, raison, acteur et révision.
- POST `/api/v1/ai/requests/{id}/decision`: approve/reject local avec raison et révision.

Les deux routes humaines exigent `X-Approval-Token`, issu du secret `APPROVAL_TOKEN` dans `.env`.
Le nom d'acteur est une déclaration de l'opérateur partageant ce jeton, pas une identité multiutilisateur certifiée.
Ce mécanisme local n'est pas une solution IAM de production. Il n'est jamais transmis au modèle.
Les révisions périmées et statuts incompatibles retournent 409; les erreurs de modèle 502, indisponibilités 503, timeouts 504.
Les échecs d'analyse persistés sont retrouvables avec le header `X-Request-ID`.
Toutes les routes de l'étape 1 sont conservées; services liés à localhost.

## RAG et améliorations

Voir `knowledge/README.md`. BM25 Python/PostgreSQL, sources et SHA256 traçables, maximum 2000 passages candidats.
Pas de corpus officiel fourni: l'absence est affichée comme `empty_corpus`; aucune règle officielle inventée.
Le contenu est non fiable et ne peut pas modifier la configuration ni les référentiels.
Les signaux d'injection connus sont filtrés, sans prétendre une détection parfaite. L'absence d'exécuteur et
la validation indépendante restent les protections structurelles.
Les décisions approuvées peuvent devenir des exemples de contexte avec leurs IDs; aucun entraînement ni export automatique.
Tout futur fine-tuning/export nécessitera étude de faisabilité, autorisation et anonymisation.

## Exécution Windows et tests

```powershell
cd C:\AGENT-SAGE-X3\backend
.\.venv\Scripts\python.exe ..\scripts\step2_admin.py migrate
$env:RUN_STEP2_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests -q
cd ..
.\scripts\start.ps1
.\backend\.venv\Scripts\python.exe scripts\test_step2_live.py
.\backend\.venv\Scripts\python.exe scripts\test_step2_n8n.py
```

Les tests réels sont distincts des mocks: ils consomment plusieurs minutes CPU et conservent des demandes synthétiques.
La migration est une commande explicite; l'import du backend n'applique pas de DDL automatiquement.
Pour une conteneurisation ultérieure, le Dockerfile inclut migrations, prompts et règles par défaut;
URLs et secrets demeurent des variables d'environnement. Aucun Docker n'est requis actuellement.

## Sauvegarde

La procédure native existante sauvegarde toute la base `agent_sage`, y compris le schéma `sage_ai`,
la base n8n, ses fichiers, les sources, les verrous et le `.env` original.
`native_backup.py --validate-restore` reste utilisable; les archives sont privées et exclues de Git.
Le jeton d'approbation fait partie des secrets à protéger lors d'un transfert, comme la clé n8n.
Le rapport étape 1 est préservé; le nouveau rapport factuel est `logs/ETAPE-2-RAPPORT-FINAL.md`.
