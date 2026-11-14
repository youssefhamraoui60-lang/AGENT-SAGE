# Architecture native Windows — voie retenue

La création d'une VM Ubuntu est annulée. Les fichiers Ubuntu/Sangfor précédents sont conservés
uniquement comme historique; ils ne sont pas utilisés par cette architecture.

Tous les services résident dans C:\AGENT-SAGE-X3, sauf les logiciels Windows et Ollama déjà installés.
Aucun service Windows n'est enregistré par les scripts natifs. Aucun démarrage automatique au boot.

| Service | Exécution | Adresse |
|---|---|---|
| PostgreSQL | Binaires EDB 17.11, compte Windows courant | 127.0.0.1:55432 |
| n8n | Installation npm locale, Node.js existant | 127.0.0.1:5678 |
| FastAPI | Venv Python existant, conservé | 127.0.0.1:8000 |
| Ollama | Installation existante, conservée | 127.0.0.1:11434 |

PostgreSQL:
- binaires: .tools/postgresql-17/pgsql/bin;
- cluster: runtime/postgres;
- rôle d'administration dédié sage_admin, secret NATIVE_PG_ADMIN_PASSWORD dans .env;
- rôle applicatif agent sans superuser, propriétaire agent_sage;
- rôle n8n sans superuser, propriétaire de la base n8n;
- authentification SCRAM, écoute IPv4 localhost, aucun accès réseau d'entreprise.

n8n:
- dépendances: .tools/n8n, installation npm versionnée, verrou à conserver;
- données de configuration et fichiers: runtime/n8n;
- base PostgreSQL n8n distincte du backend;
- même clé N8N_ENCRYPTION_KEY conservée dans .env;
- diagnostics et notifications externes désactivés, cookies HTTP pour localhost uniquement.

Les scripts/start-native.ps1 et stop-native.ps1 démarrent/arrêtent uniquement les processus du projet.
stop-native conserve FastAPI et Ollama. Pour arrêter explicitement FastAPI, utiliser stop.ps1 -BackendOnly.
start-native préserve un port déjà occupé; il faut ensuite vérifier que le service répond correctement.

```powershell
.\scripts\start-native.ps1
.\scripts\test-native-environment.ps1 -TestPersistence
.\backend\.venv\Scripts\python.exe scripts\native_backup.py --validate-restore
.\scripts\stop-native.ps1
```

Les tests de persistance redémarrent le PostgreSQL du projet; les connexions applicatives peuvent
être momentanément interrompues. Aucun service de production ou SQL Server n'est touché.

La sauvegarde native inclut deux dumps PostgreSQL, runtime/n8n, le .env original, les sources,
les manifestes/verrous npm et un manifeste SHA256. Elle suspend temporairement n8n pour stabiliser ses fichiers.
Le répertoire backups contient des secrets et est privé, exclu de Git.
L'option --validate-restore restaure les dumps dans un NOUVEAU cluster runtime/restore-validation-* sur le port 55433,
compare les nombres de lignes et les fichiers n8n, puis arrête ce cluster de validation. Aucun cluster n'est supprimé.
Le script ne remplace pas un cluster existant. Les deux dumps sont cohérents par base, pas atomiques entre bases.

Pour un transfert: conserver le dossier de sauvegarde avec ses secrets sur un support protégé,
vérifier son manifeste, récupérer source.zip et le .env original dans une nouvelle racine,
installer les mêmes versions des binaires PostgreSQL/Node/Python et les dépendances verrouillées,
initialiser un cluster vide avec les mêmes rôles puis restaurer backend.dump et n8n.dump par pg_restore.
Copier n8n-home vers runtime/n8n et conserver exactement N8N_ENCRYPTION_KEY.
Recréer le venv depuis backend/requirements.lock.txt, installer n8n avec son package-lock,
et conserver/retélécharger qwen2.5:7b dans Ollama. Le modèle et les logiciels ne sont pas inclus dans les dumps.
Exécuter les tests d'intégration et de persistance avant de considérer la nouvelle machine comme restaurée.

Le succès des commandes de préparation ne garantit pas que les services ont démarré.
Se référer au rapport logs/ETAPE-1-RAPPORT-FINAL.md et aux preuves de tests réellement exécutés.

Sources:
- https://www.postgresql.org/download/windows/
- https://www.enterprisedb.com/download-postgresql-binaries
- https://github.com/EnterpriseDB/edb-installers/issues/682
- https://docs.n8n.io/hosting/installation/npm/
