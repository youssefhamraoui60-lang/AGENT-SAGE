$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$ai=Get-Content logs\ollama-tests.json -Raw -Encoding UTF8 | ConvertFrom-Json
$envTests=Get-Content logs\environment-tests.json -Raw -Encoding UTF8 | ConvertFrom-Json
$passed=@($ai | Where-Object schema_valid).Count
$semantic=Get-Content logs\ai-semantic-checks.json -Raw -Encoding UTF8 | ConvertFrom-Json
$semanticPassed=@($semantic | Where-Object status -eq 'PASS').Count
$table=@('| Demande | Essai | Resultat Pydantic | Secondes |','|---|---:|---|---:|')
foreach($r in $ai){$table+="| $($r.test) | $($r.essai) | $($r.status) | $($r.seconds) |"}
$matrix=@('| Controle | Statut |','|---|---|')
foreach($r in $envTests){$matrix+="| $($r.test) | $($r.status) |"}
$report=@'
# ETAPE 1 — RAPPORT FINAL

Date: 16 octobre 2026, Europe/Paris.

## A. Informations systeme
Windows Server 2025 Standard 64 bits; Intel Xeon Cascadelake, 8 coeurs/8 threads.
RAM: 16 Go, environ 11 Go disponibles lors de l'audit initial. Disque C: environ 83 Go libres initialement.
Aucun GPU de calcul detecte (adaptateurs Remote Display et Sangfor QXL).
VirtualizationFirmwareEnabled=false. WSL absent. Voir system-audit.md pour les mesures completes et ports.

## B. Logiciels et versions
- Git MinGit 2.56.0.windows.2 portable dans le profil utilisateur; depot local initialise, aucun distant.
- Python 3.15.0 installe manuellement par l'utilisateur, pip 26.2.1; venv backend/.venv cree et utilise.
- Tentative Python 3.12 par winget refusee: strategie organisation, code 1625. Aucun contournement de cette strategie.
- Installation Git classique interrompue a la demande d'elevation; installation portable sans elevation ensuite.
- Node 24.20.0 LTS, npm 11.19.0 portables; archives officielles et SHA256 verifies.
- Ollama 0.40.5 installe par winget pour l'utilisateur, hash installateur verifie.
- Docker CLI 29.8.2 et Compose 5.6.0 preexistants. Moteur non disponible.
- FastAPI 0.143.2, Pydantic 2.14.1, Uvicorn 0.54.0, psycopg 3.3.6; toutes versions resolues dans backend/requirements.lock.txt.

## C. Structure du projet
Racine C:\AGENT-SAGE-X3. Backend/app avec api, core, agents, services, schemas, models; backend/tests;
frontend; docker; workflows; database; logs; scripts; tests; models.
Fichiers .env, .env.example, .gitignore, compose.yaml, README.md et backend/Dockerfile crees.
Frontend et repertoires futurs sont des emplacements reserves: aucune fonctionnalite Sage X3 developpee.
.env contient des secrets aleatoires distincts, ACL limitee a l'utilisateur et SYSTEM, fichier exclu de Git.

## D. Etat des conteneurs
Aucun conteneur du projet demarre: pipe dockerDesktopLinuxEngine introuvable.
Docker Desktop n'est pas supporte sous Windows Server:
https://docs.docker.com/desktop/setup/install/windows-install/
Activation WSL/virtualisation et modification de l'hote non tentees.
Compose valide par docker compose config --quiet (code 0).
Manifestes postgres:17.6-bookworm, n8nio/n8n:2.43.7 et python:3.15.0-slim consultes avec succes.
Le registre docker.n8n.io a expire; source n8nio/n8n sur Docker Hub verifiee et retenue.
Manifestes consultes ne signifient pas images telechargees ni conteneurs testes.
Volumes persistants dedies, reseau interne, ports localhost, healthchecks, restart=no.

## E. PostgreSQL
Configuration et SQL prepares: users, article_requests, supplier_requests, approval_requests, agent_execution_logs.
Base n8n et role n8n separes de la base backend. Secrets differents.
Service indisponible. /health/db retourne HTTP 503, conformement a la gestion d'erreur.
Creation effective des tables, insertion/lecture, rollback et persistance: SKIPPED, moteur absent.
scripts/test_database.py et test-environment.ps1 -TestPersistence prepares pour ces controles.

## F. FastAPI
Backend natif demarre sur http://127.0.0.1:8000 (aucun lancement automatique Windows).
GET /health: HTTP 200. GET /health/ollama: HTTP 200. GET /health/db: HTTP 503 attendu en absence de DB.
POST /api/ai/extract: appel reel POLYSTER 3 CM, HTTP 200 en environ 10.1 secondes, JSON valide.
Preuve: backend-extraction.json. Essai additionnel de la demande 1: backend-extraction-test1.json.
Validation Pydantic, erreurs 502/503/504, timeouts, journalisation sans secrets.
Pytest: 5 passes. Un avertissement de deprecation TestClient/httpx est conserve dans pytest.log.
Construction Docker non executee. Scripts start/stop -BackendOnly executes pour verifier le cycle natif.

## G. n8n
Configuration PostgreSQL, volume persistant, healthcheck readiness et workflow JSON de demonstration prepares.
Workflow inactif: Webhook de test -> Backend FastAPI -> Reponse JSON.
Conteneur, HTTP, connexion PostgreSQL, import workflow et persistance: non verifies, service absent.
Apres disponibilite Docker: creer le compte proprietaire local dans l'interface n8n et importer le workflow.
Aucune activation ni creation de compte pretendue.

## H. Ollama
Service local repond sur 127.0.0.1:11434. Telechargement et inference effectivement executes.
Le raccourci Startup ajoute par l'installation a ete deplace dans logs/Ollama-startup-disabled.lnk.
Ollama ne sera donc pas lance par ce raccourci au prochain demarrage Windows.
Acces depuis les conteneurs via host.docker.internal prepare, mais non teste faute de moteur.
Aucun bind 0.0.0.0 et aucune regle pare-feu ajoutes.

## I. Modele choisi
qwen2.5:7b, 7.6B, Q4_K_M, environ 4.7 Go sur disque.
Choix conforme a la preference avec 16 Go RAM; execution CPU faute de GPU de calcul.
Les mesures sont locales et incluent le chargement et, pour certains appels, l'attente d'un autre appel local.
La confiance retournee est une estimation du modele, non calibree.

## J. Neuf essais finaux d'extraction
Les neuf appels ont ete faits reellement, trois par demande, et valides avec Python/Pydantic.
Les JSON et erreurs complets sont dans ollama-tests.json et ollama-tests.md.
Les premieres series sont conservees dans ollama-tests-native.json, ollama-tests-initial.md,
ollama-tests-python-premier.json et ollama-tests-python-premier.md.
Des incoherences initiales sur unite/champs_manquants ont motive une correction de consigne.
Aucune reponse invalide n'a ete reconstruite pour fabriquer un succes.
'@
$report+="`n`n"+($table -join "`n")
$report+="`n`nJSON conformes au schema dans la serie finale: $passed/9. Le schema ne prouve pas l'exactitude semantique.`n"
$report+="`nComparaison des quatre champs explicites aux demandes synthetiques: $semanticPassed/9 PASS. Preuve: ai-semantic-checks.json.`n"
for($i=1;$i -le 3;$i++){
    $subset=@($ai | Where-Object {$_.test -eq $i -and $_.schema_valid})
    $distinct=@($subset | ForEach-Object {$_.json | ConvertTo-Json -Depth 8 -Compress} | Select-Object -Unique).Count
    $report+="`nDemande ${i}: $($subset.Count)/3 JSON conformes, $distinct sorties distinctes."
}
$report+=@'


## K. Tests reussis et controles globaux
'@
$report+="`n`n"+($matrix -join "`n")
$report+=@'


## L. Echecs et limites
Moteur Docker inaccessible. PostgreSQL et n8n absents; persistance et connectivite conteneurs non demontrees.
Les eventuels FAIL des essais IA restent des echecs; consulter leur JSON brut et erreur Pydantic.
Les tests SKIPPED ne constituent jamais une validation. Logs conteneurs inaccessibles faute de moteur.
Backend natif teste; pile Compose non demarree. Aucune conclusion de bon fonctionnement n8n/PostgreSQL.

## M. Intervention necessaire
Choisir un hote Docker Linux ou Windows client compatible. L'hote actuel est Windows Server avec virtualisation indisponible.
Toute activation Windows/WSL, virtualisation imbriquee ou migration necessite une decision de l'utilisateur/administrateur.
La virtualisation imbriquee peut necessiter une intervention sur l'hyperviseur Sangfor; aucune modification appliquee.
Python est desormais resolu par l'installation manuelle; aucune autre installation Python requise pour le backend natif.
Apres disponibilite Docker: arreter le backend natif, lancer la pile, verifier DB/n8n, persistance et acces Ollama conteneur.
Le backend natif et Ollama restent accessibles localement a la fin de cette intervention.

## N. Demarrage et arret
Depuis C:\AGENT-SAGE-X3:

```powershell
.\scripts\start.ps1 -BackendOnly
.\scripts\stop.ps1 -BackendOnly
.\scripts\status.ps1
# Lorsque Docker Linux sera disponible:
.\scripts\stop.ps1 -BackendOnly
.\scripts\start.ps1
.\scripts\test-environment.ps1 -TestPersistence
.\scripts\test-ai.ps1
.\scripts\stop.ps1
```

Les scripts ne suppriment aucun volume. Les secrets restent dans .env et ne figurent pas dans ce rapport.
Le script test-environment relance les neuf inferences; prevoir plusieurs minutes sur CPU.

## O. Conclusion
ÉTAPE 1 PARTIELLEMENT VALIDÉE : Python, Git, Node, Ollama, modele local et backend natif fonctionnent.
Docker, PostgreSQL, n8n et les tests obligatoires de persistance restent bloques/non verifies.
Aucun acces a Sage X3, SQL Server entreprise ou API Sage X3. Aucune etape 2 commencee.
'@
$report | Set-Content logs\ETAPE-1-RAPPORT-FINAL.md -Encoding UTF8
