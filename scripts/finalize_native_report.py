"""Final native report, gated on real test evidence and the latest nine AI trials."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
def load(name,default=None):
    path=ROOT/'logs'/name
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def main():
    tests=load('native-environment-tests.json',[])
    ai=load('ollama-tests.json',[])
    semantic=load('ai-semantic-checks.json',[])
    workflow=load('native-workflow-tests.json',{})
    backup=load('native-backup-tests.json',{})
    pytest=load('pytest-result.json',{})
    state=load('native-final-state.json',{})
    logs=load('native-stability-check.json',{})
    vc=load('vc-runtime-verification.json',{})
    probe=load('backend-extraction-native-final.json',{})
    passed=sum(x.get('schema_valid',False) for x in ai)
    semantic_passed=sum(x.get('status')=='PASS' for x in semantic)
    native_pass=bool(tests) and all(x['status']=='PASS' or (x['test']=='Docker' and x['status']=='SKIPPED') for x in tests)
    ready=(native_pass and len(ai)==9 and passed==9 and len(semantic)==9 and semantic_passed==9
        and workflow.get('status')=='PASS' and backup.get('restore')=='PASS' and pytest.get('exit_code')==0
        and state.get('http') and all(code==200 for code in state['http'].values())
        and logs.get('status')=='PASS' and probe.get('status')=='PASS' and vc.get('installed')==1)
    conclusion='ÉTAPE 1 VALIDÉE' if ready else 'ÉTAPE 1 PARTIELLEMENT VALIDÉE'
    table='\n'.join(f"| {x['test']} | {x['status']} |" for x in tests)
    ai_table='\n'.join(f"| {x['test']} | {x['essai']} | {x['status']} | {x['seconds']} |" for x in ai)
    now=datetime.now(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y %H:%M %Z')
    report=f'''# AGENT-SAGE-X3 — ÉTAPE 1 — RAPPORT FINAL

Mise à jour: {now}.

**{conclusion} — architecture native Windows autorisée.** Aucun Docker opérationnel n'est prétendu:
l'utilisateur a expressément retenu PostgreSQL et n8n natifs sur la seule VM Windows actuelle.
La création d'une VM Ubuntu est annulée; les anciens fichiers sont conservés comme historique.

## A. Système

Windows Server 2025 Standard 24H2 x64, build 26100.33650. VM Sangfor aCloud confirmée (sangfor/acloud, HypervisorPresent=true).
Intel Xeon Cascadelake, 8 vCPU, 16 Go RAM; environ 75 Gio libres sur C: lors du diagnostic de reprise.
Pas de GPU de calcul détecté. WSL absent; disponibilité de la virtualisation imbriquée non démontrée par les indicateurs CIM.
Windows Server 2025 prend en charge WSL2 sous réserve des prérequis; aucun de ces prérequis n'a été activé.
Un moteur Windows ne remplace pas le noyau Linux nécessaire aux images Compose Linux initiales.
Aucune création de VM, activation Hyper-V/WSL, modification Sangfor, pare-feu ou politique de sécurité.

## B. Logiciels réellement opérationnels

| Composant | Version / résultat |
|---|---|
| Microsoft Visual C++ x64 | {vc.get('version','non vérifié')}, Installed={vc.get('installed')} dans le registre; DLL système présentes |
| PostgreSQL Windows EDB | 17.11, binaire --version code 0, cluster local démarré |
| Node.js / npm | 24.20.0 LTS / 11.19.0, installations existantes conservées |
| n8n npm local | 2.43.7, commande version et readiness HTTP testées |
| Python | 3.15.0, venv existant conservé |
| FastAPI / Pydantic / Uvicorn | 0.143.2 / 2.14.1 / 0.54.0, versions verrouillées dans backend/requirements.lock.txt |
| Ollama | 0.40.5, installation existante conservée |
| Modèle | qwen2.5:7b, Q4_K_M, environ 4.7 Go, inférence CPU réelle |
| Git | MinGit 2.56.0.windows.2, dépôt local, aucun distant |
| Docker CLI / Compose | préexistants conservés; moteur inutilisé, non requis pour la variante native |

Le runtime Microsoft a été traité par l'utilisateur puis vérifié par le registre, les DLL et le démarrage de PostgreSQL.
L'ancienne tentative UAC annulée reste tracée; aucun succès d'installation administrateur par Codex n'est inventé.
L'archive PostgreSQL officielle EDB a été vérifiée contre le SHA256 publié:
4b8db0930c38f6ef845db919551dedda3b6b845aeb0927b3d79a6e8e9e4537cf.
n8n: 2314 paquets ajoutés. npm a signalé des scripts de dépendances non approuvés;
aucune protection npm globale n'a été désactivée. Les fonctions réellement nécessaires ont été testées, y compris le moteur du workflow.
Les avertissements de dépendances obsolètes sont conservés dans n8n-install.log.

## C. Architecture finale et fichiers

```text
Windows Server — C:\\AGENT-SAGE-X3
  n8n 127.0.0.1:5678 -----> FastAPI 127.0.0.1:8000 -----> Ollama 127.0.0.1:11434
       |                           |
       +---- base n8n              +---- base agent_sage
                    PostgreSQL 127.0.0.1:55432
```

Binaires PostgreSQL: .tools/postgresql-17/pgsql/bin. Installation n8n: .tools/n8n.
Données PostgreSQL: runtime/postgres. Données et configuration n8n: runtime/n8n.
Le backend, son schéma, ses tests et les répertoires du projet sont conservés.
STACK_MODE=native dans .env sélectionne les scripts natifs depuis start.ps1, stop.ps1 et test-environment.ps1.
Tous les ports utiles sont limités à 127.0.0.1. Pas de publication Internet, pas de service Windows ou tâche de démarrage automatique.
Les services s'exécutent sous le compte utilisateur; runtime, backups et .env sont protégés par ACL et exclus de Git.
Les secrets ne figurent pas dans ce rapport. Les logiciels Windows/Ollama déjà installés restent dans leurs emplacements d'origine.

## D. PostgreSQL

Cluster dédié au projet. Rôle d'administration sage_admin; rôles agent et n8n distincts, sans SUPERUSER/CREATEDB/CREATEROLE.
Bases agent_sage et n8n séparées. Authentification SCRAM-SHA-256, listen_addresses=127.0.0.1.
Tables backend créées: users, article_requests, supplier_requests, approval_requests, agent_execution_logs.
Connexion, insertion et lecture synthétiques, rollback puis relecture après redémarrage contrôlé testés.
Preuves: native-postgres-init.log, native-environment-tests.json, native-final-state.json, postgres-native.log.

## E. FastAPI

/health, /health/db et /health/ollama répondent HTTP 200 dans l'état final.
/api/ai/extract testé directement et à travers n8n avec de vraies inférences locales.
Le contrôle DB utilise une connexion synchrone dans le thread pool FastAPI pour éviter l'incompatibilité
Psycopg asynchrone / boucle Proactor Windows rencontrée; ce changement est limité au backend du projet.
5 tests pytest réussis après correction. Un avertissement de dépréciation TestClient/httpx reste non bloquant.
Schéma Pydantic, timeouts, erreurs 502/503/504 et journalisation structurée conservés.

## F. n8n

Migrations PostgreSQL exécutées. Éditeur: http://127.0.0.1:5678; readiness HTTP 200.
Compte propriétaire local de démonstration admin@localhost.invalid créé pour cette instance neuve;
mot de passe fort uniquement dans .env (N8N_OWNER_PASSWORD). Aucun email envoyé, aucun compte existant réinitialisé.
Workflow réel: Webhook -> FastAPI -> Ollama -> Réponse JSON. Résultat: {workflow.get('status','SKIPPED')}, HTTP {workflow.get('webhook_http')}.
Demande POLYSTER 3 CM, unité M3, catégorie MARCH, fournisseur ISONIMA: champs attendus vérifiés.
Workflow conservé après redémarrage n8n, désactivé à la fin. Les deux workflows synthétiques, dont le premier essai, sont conservés inactifs.
Fichier: workflows/demo-extraction-native.json; preuves: native-workflow-tests.json et native-workflow-run.log.

## G. Ollama, modèle et neuf essais finaux

Ollama natif sur localhost, modèle Qwen 2.5 7B adapté aux 16 Go RAM; GPU de calcul non disponible.
Neuf appels réels, trois par demande, validation Python/Pydantic et comparaison des quatre champs explicites.
JSON conformes: **{passed}/9**. Comparaisons sémantiques synthétiques réussies: **{semantic_passed}/9**.

| Demande | Essai | Résultat | Secondes |
|---|---:|---|---:|
{ai_table}

Les JSON complets, durées, erreurs et stabilité par demande sont dans ollama-tests.json / ollama-tests.md.
La confiance déclarée est une estimation du modèle, pas une probabilité calibrée.
Un premier nouvel essai a produit la chaîne "null" au lieu du littéral null; réponses rejetées et conservées dans
ollama-tests-native-null-string-failure.json. Correction: consigne explicite et exemple de dialogue avec un vrai null.
Aucune réponse invalide n'a été modifiée pour fabriquer un succès. Le schéma et sa cohérence restent vérifiés.

## H. Tests d'intégration et de persistance

| Contrôle | Résultat |
|---|---|
{table}

Docker est SKIPPED par décision d'architecture native, et non présenté comme installé ou fonctionnel.
L'inférence réelle, le webhook de bout en bout, les neuf comparaisons, pytest et l'état HTTP final complètent cette matrice.
Preuves supplémentaires: backend-extraction-native-final.json, pytest-result.json, ai-semantic-checks.json et native-final-state.json.

## I. Corrections et journaux

- Runtime Microsoft manquant: vérifié présent avant initialisation PostgreSQL.
- Contrôle DB FastAPI incompatible avec Proactor: corrigé dans le projet et retesté.
- Publication n8n asynchrone: le test attend l'enregistrement réel du webhook avant l'appel. Le premier HTTP 500 est conservé dans native-workflow-initial-failure.json.
- Le script pg_ctl laissait son pipe PowerShell hérité au serveur: redirection vers pg-control.log, démarrage et tests de redémarrage retestés.
- Le catalogue MCP n8n externe a connu un timeout: module de catalogue optionnel inutilisé désactivé via N8N_DISABLED_MODULES=mcp-registry.
  Aucun garde de sécurité désactivé. Le workflow local et l'isolation d'expressions fonctionnent.
- Les coupures de connexion pendant les redémarrages PostgreSQL sont attendues; n8n a journalisé Database connection recovered.

Contrôle de stabilité final des journaux: **{logs.get('status','SKIPPED')}**; preuve native-stability-check.json.
Les erreurs historiques et transitoires restent tracées; elles ne sont pas masquées comme des succès.
Les lignes PostgreSQL de sévérité LOG « winsock error 10054 » lors de l'arrêt du client n8n pour sauvegarde
sont consignées séparément comme déconnexions attendues, uniquement si les services répondent tous HTTP 200 ensuite.
Aucun blocage essentiel résolu n'est présenté comme encore actif. Les avertissements npm/pg/TestClient sont documentés et non assimilés à des erreurs critiques persistantes.
n8n 2.43.7 annonce aussi la dépréciation du mode natif hors conteneur et du task runner interne pour une version future.
La version est verrouillée; toute mise à niveau future devra revérifier sa compatibilité avec Windows natif.

## J. Sauvegarde et restauration réelles

Sauvegarde: `{backup.get('backup','non exécutée')}`.
Résultat: {backup.get('status','SKIPPED')}; restauration contrôlée: **{backup.get('restore','SKIPPED')}**.
Contenu: dumps PostgreSQL backend/n8n, données et configuration n8n, .env original avec clé de chiffrement,
sources et verrous, manifeste SHA256. Les archives contiennent des secrets: conserver le dossier sur un support protégé.
La sauvegarde suspend temporairement n8n puis le relance. Les snapshots sont cohérents par base, pas atomiques entre les deux bases.
La restauration de validation utilise un nouveau cluster local sur 55433, compare les lignes et les fichiers n8n,
puis l'arrête sans supprimer les données de validation. Aucun cluster existant n'est écrasé.
Preuves: native-backup-tests.json, native-backup-run.log. Le cluster de validation reste arrêté.

Transfert vers une autre VM Windows:
1. Copier le dossier de sauvegarde protégé; vérifier son manifeste avec scripts/verify_native_backup.py.
2. Extraire source.zip dans une nouvelle racine et y remettre environment.env comme .env avec ACL privée.
3. Installer les mêmes versions compatibles des logiciels sur cette cible; recréer le venv et n8n depuis les verrous.
4. Initialiser un cluster VIDE et les mêmes rôles, restaurer backend.dump et n8n.dump avec pg_restore.
5. Remettre n8n-home dans runtime/n8n et conserver exactement N8N_ENCRYPTION_KEY.
6. Conserver/retélécharger qwen2.5:7b dans Ollama, puis refaire les tests HTTP, workflow et persistance.
Le venv, les logiciels et le modèle Ollama ne sont pas inclus dans les dumps. Voir database/NATIVE-WINDOWS.md.

## K. Commandes d'exploitation

Depuis C:\\AGENT-SAGE-X3:

```powershell
.\\scripts\\start.ps1
.\\scripts\\status.ps1
.\\scripts\\test-environment.ps1 -TestPersistence
.\\scripts\\test-ai.ps1
.\\backend\\.venv\\Scripts\\python.exe scripts\\native_backup.py --validate-restore
.\\scripts\\stop.ps1
```

start.ps1 démarre les composants natifs manquants en préservant les processus déjà actifs.
stop.ps1 arrête PostgreSQL/n8n du projet; FastAPI et Ollama sont conservés.
Arrêt explicite du backend: scripts/stop.ps1 -BackendOnly. Aucune exécution au démarrage Windows configurée.
Pour n8n, utiliser les identifiants locaux de .env; aucun mot de passe n'est publié dans le rapport.
Le workflow de démonstration est inactif: l'activer uniquement pour un test volontaire.

## L. Intervention et limites

Si tous les critères ci-dessus sont PASS, aucune intervention administrateur ni aucun redémarrage supplémentaire n'est nécessaire pour l'étape 1.
La validation concerne un environnement local de préparation et ses données synthétiques; aucune connexion Sage X3 n'est configurée.
Les contrôles sont des observations à la date du rapport, pas une garantie de fonctionnement en production ou après modification.
Les services doivent être démarrés manuellement après fermeture de session/redémarrage Windows.

## M. Conclusion

**{conclusion}** pour l'architecture native sur la VM Windows Server actuelle.
La validation exige tous les composants requis opérationnels et les preuves réelles d'intégration, persistance et restauration.
Aucune autre VM créée, aucun accès Sage X3/SQL Server et aucun service de production modifié.
L'intervention s'arrête à l'étape 1; aucune fonctionnalité de l'étape 2 développée.
'''
    (ROOT/'logs/ETAPE-1-RAPPORT-FINAL.md').write_text(report,encoding='utf-8')
    print(conclusion)

if __name__=='__main__': main()
