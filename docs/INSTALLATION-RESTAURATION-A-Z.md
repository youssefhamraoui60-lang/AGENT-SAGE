# Installation et restauration AGENT SAGE, de A à Z

État documenté : 14 novembre 2026. La configuration réellement exploitée est
Windows natif x64, PowerShell 5.1, Python 3.15, PostgreSQL 17, Node 24 et Ollama.
Les fichiers Docker/Ubuntu historiques ne remplacent pas cette procédure : OCR
Windows, PowerShell et les identifiants DPAPI nécessitent une adaptation Linux.

## 1. Identifier les deux livrables

**ZIP COMPLET PRIVÉ** : application entière avec `.env`, documents, historiques,
certificats, sessions, dépendances installées, outils, Python, Ollama et modèles,
dumps de toutes les bases PostgreSQL locales et rôles, instantanés SQLite.
`backup/REPORT.json` décrit précisément les exclusions et fichiers évolutifs.
Le cluster PostgreSQL actif n'est pas copié à chaud : les dumps sont la sauvegarde
restaurable. Les logiciels et poids copiés ne sont pas une image Windows.

**ZIP PUBLIC / dépôt GitHub** : code et documentation filtrés, `.env.example`
sans secrets ; aucune base, session Telegram, clé privée, document métier ou log.
Il ne permet pas de récupérer les secrets de la sauvegarde privée.

Conserver le ZIP privé dans un emplacement protégé. Il n'est pas chiffré et ne
doit jamais être ajouté au dépôt public. Les mots de passe et clés n8n présents
dans les dumps et `.env` donnent accès à des données réelles.

## 2. Vérifier avant extraction

Comparer `Get-FileHash -Algorithm SHA256 <archive.zip>` avec le fichier
`.zip.sha256`. Le backup a aussi une vérification CRC ZIP et un manifeste SHA256
par fichier (`backup/MANIFEST-SHA256.json`). Après extraction :

Si Python n'est pas encore installé, utiliser `software/python315/python.exe`
à la place de `python` dans la commande suivante.

```powershell
python application/scripts/verify_complete_backup.py C:\Restauration\AGENT-SAGE
```

Prendre un Windows x64 neuf, avec assez d'espace pour le ZIP ET son extraction
(prévoir au moins 35 Go libres, davantage selon les documents). Extraire dans
un dossier privé. Le répertoire `application` est la racine du projet ; `software`
contient les composants externes ; `backup/database` contient les dumps.

## 3. Installer les prérequis Windows

Installer le runtime Microsoft Visual C++ x64 (installateur inclus dans
`application/.tools/downloads/vc_redist.x64.exe`) et les composants OCR français de
Windows. Ces composants système ne sont pas transportables par copie de dossier.
Utiliser Windows PowerShell 5.1 pour les scripts .NET/WinRT et les credentials.
Les versions capturées de Python, Node, Git, PostgreSQL, n8n et Ollama sont incluses,
avec leurs licences dans leurs dossiers. Les roues Python hors ligne sont sous
`application/.tools/offline-python` ; leur résultat de préparation figure dans
`application/logs/backup-wheel-build.log`.

Pour minimiser les chemins absolus historiques, installer l'application sous
`C:\AGENT-SAGE-X3` sur la NOUVELLE machine. Ne jamais écraser une installation active.
Copier `software/windows-tools` dans `$env:LOCALAPPDATA\AGENT-SAGE-X3-tools`,
`software/python315` dans `$env:LOCALAPPDATA\Python\pythoncore-3.15-64`,
`software/ollama` dans `$env:LOCALAPPDATA\Programs\Ollama`, et
`software/ollama-models` dans `$env:USERPROFILE\.ollama\models`.
Les poids ne se retéléchargent pas si ces dossiers sont correctement replacés.
Sur une autre architecture, installer les versions compatibles depuis leurs
éditeurs ; les binaires Windows sauvegardés ne fonctionnent pas sur Linux.

## 4. Recréer les environnements Python

Les venv copiés sont une archive de l'état précédent, pas une garantie de
portabilité. Sur la nouvelle machine, renommer les deux `.venv` sauvegardés en
`.venv-original`, puis créer les nouveaux environnements :

```powershell
cd C:\AGENT-SAGE-X3
$python = "$env:LOCALAPPDATA\Python\pythoncore-3.15-64\python.exe"
& $python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install --no-index --find-links .tools/offline-python -r .tools/offline-python/backend-requirements.txt
& $python -m venv telegram-test/.venv
& telegram-test/.venv/Scripts/python.exe -m pip install --no-index --find-links .tools/offline-python -r .tools/offline-python/telegram-requirements.txt
```

En mode connecté, remplacer `--no-index --find-links ...` par un index Python
autorisé, en gardant les versions des fichiers verrouillés du backup.
Le dossier n8n installé est inclus sous `.tools/n8n`. Le frontend compilé et ses
dépendances sont inclus dans le ZIP privé ; pour reconstruire : charger
`scripts/tools.ps1`, puis `cd frontend`, `npm ci`, `npm run build`.

## 5. Configuration et secrets

Restaurer le `.env` privé sans l'afficher et adapter les adresses, ports, modèles,
chemins et dossiers autorisés. `backup/inventory` conserve les versions Python et
la liste exacte des modèles Ollama. Garder **N8N_ENCRYPTION_KEY** identique pour
déchiffrer les credentials n8n restaurés. Les variables de production ne doivent
pas être utilisées pour des essais sur un serveur Sage de démonstration.

Les `.clixml` utilisent DPAPI : ils sont liés au compte Windows et à la machine.
Les copier ne suffit pas. Recréer chaque credential requis sur le nouveau compte,
par exemple (la saisie du mot de passe reste dans la fenêtre sécurisée) :

```powershell
Get-Credential | Export-Clixml -LiteralPath runtime/sql-reader-credential.clixml
```

Inventorier les autres `.clixml` du ZIP et recréer les comptes correspondants.
Ne pas substituer un compte administrateur au compte applicatif.
Les certificats et clés inclus restent privés ; remettre les certificats de
confiance selon la procédure de votre environnement, sans désactiver TLS.

## 6. Restaurer PostgreSQL dans un cluster NEUF

Ne pas lancer `native_stack.py init` puis superposer les dumps : cet init crée
des schémas qui entreraient en conflit avec la restauration. Utiliser le script
ci-dessous, qui refuse un répertoire existant et un port déjà occupé :

```powershell
& backend/.venv/Scripts/python.exe scripts/restore_complete_databases.py `
  --backup C:\Restauration\AGENT-SAGE\backup\database `
  --data C:\AGENT-SAGE-X3\runtime\postgres --port 55432
```

Ce script initialise un cluster vide avec un rôle technique de restauration,
restaure les rôles puis toutes les bases, s'arrête sur toute erreur et arrête le
cluster après contrôle. Le port doit correspondre à `DB_PORT` dans `.env`.
Ensuite `native_stack.py start-pg` démarre le cluster restauré. Les migrations
historiques sont déjà contenues dans les dumps : ne pas rejouer les INSERT de seed.

Les SQLite cohérents sont déjà à leur emplacement dans `application/runtime` :
journaux anti-doublons, reçus de commandes, authentification Telegram. Ne pas
réinitialiser ces journaux : cela risquerait de recréer des commandes existantes.
Les anciens PID ne représentent aucun processus de la nouvelle machine ; les
scripts de démarrage vérifient l'identité des processus.

## 7. Reconnecter Sage X3

Le serveur SQL distant `sage`, base `x3v12`, n'est PAS une base PostgreSQL locale.
Ce backup d'application ne transporte pas l'installation Sage, sa licence ou son
SQL Server. Pour déplacer aussi l'ERP, le DBA doit fournir une sauvegarde SQL
Server `.bak`, ses logins, certificats, procédures et la procédure de restauration
Sage. Ne pas copier des MDF/LDF actifs.

Recréer la résolution DNS de `sage`, la connectivité SQL 1433 et SOAP, les droits
et comptes nécessaires. Plusieurs scripts historiques utilisent `sage/x3v12`
explicitement ; rechercher ces références avant de changer de serveur :

```powershell
rg -n 'tcp:sage|x3v12|192\.168\.' scripts TEST telegram-test backend/app
powershell -NoProfile -File scripts/test_sage_sql_readonly.ps1
```

Voir `docs/SQL-SAGE-CREATION-MODIFICATION.md` pour les scripts exacts et la
validation. Les commandes Telegram ciblent TEST. Le canal fournisseurs e-mail
peut cibler OB selon sa configuration restaurée : ne le démarrer qu'après
vérification du dossier, des destinataires et des droits.

## 8. Démarrer progressivement

```powershell
cd C:\AGENT-SAGE-X3
. ./scripts/tools.ps1
./scripts/start-native.ps1
./scripts/test-native-environment.ps1
```

Backend : `http://127.0.0.1:8000/docs`, interface `/sage/`, n8n sur 5678.
Pour le portail SOB, `telegram-test/start-web.ps1` démarre le serveur sur 8011
au premier plan ; en exploitation le lancer via `Start-Process -WindowStyle Hidden`
avec redirection des logs. Les ports 8001/8002 peuvent correspondre à des variantes
de backend ; ne pas démarrer arbitrairement toutes les variantes.
Ollama reste sur `127.0.0.1:11434`. Vérifier `ollama list` et le modèle `glm-ocr`.
Si le fournisseur IA actif est un service distant (par exemple DeepSeek),
son accès Internet et sa clé restent nécessaires : les paquets hors ligne
ne transforment pas ce service distant en modèle local.

Tester d'abord une préparation et une simulation SQL, sans création réelle.
Une fois la bascule décidée, arrêter l'ancien écouteur Telegram et l'ancien
worker e-mail AVANT de démarrer les nouveaux :

```powershell
./telegram-test/start-routed-assistant.ps1
./scripts/start-supplier-mail.ps1
```

La session Telegram privée peut nécessiter une nouvelle connexion avec le compte
autorisé ; ne jamais publier son fichier `.session`. Confirmer les deux groupes
et leurs IDs. Depuis le 14/11, chaque message est isolé, agrégation désactivée.
Les réponses vont dans COMMANDES SOB, les demandes viennent de sob commandes.
Ne pas rejouer tout l'historique à l'installation.

## 9. Recette avant mise en service

Contrôler santé DB/backend/n8n/Ollama, accès Sage en lecture seule, connexion
mail IMAP et SMTP, journal anti-doublons et présence des règles d'apprentissage.
Lancer les tests ciblés :

```powershell
& backend/.venv/Scripts/python.exe -m pytest telegram-test/test_telegram_batch.py telegram-test/test_telegram_routing.py telegram-test/test_cement_trip_grounding.py telegram-test/test_document_grounding.py -q
```

Effectuer une simulation d'un document connu et vérifier client, articles,
quantités, unités, prix, taxes et dossier. Les tests unitaires et le contrôle CRC
ne prouvent pas une recette Sage complète sur une autre machine.
Le ZIP privé inclut les rapports Excel de contrôle dans `TEST`.

## 10. Exploitation et dépannage

Les logs sont sous `logs/` et `runtime/telegram-test/`. Les règles et exemples
SOB sont dans PostgreSQL (`sob_learning_*`). Les reçus locaux sont dans les SQLite.
Conserver les preuves d'exécution ; résultat ambigu = vérifier Sage avant relance.
540/560 sacs par voyage ne sont jamais supposés sans preuve explicite.
Une référence ou une lecture manuscrite ambiguë reste à préciser.
Après toute évolution : tests ciblés, sauvegarde datée, puis nouveau manifeste.
La copie des fichiers reste une photographie progressive des logs/documents ;
`files_changed_during_capture` du rapport signale les fichiers ayant bougé.
