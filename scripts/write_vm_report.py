"""Report the observed VM diagnostic and preparation; never claim a deployed VM."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
checks=json.loads((root/'logs/vm-integration-tests.json').read_text(encoding='utf-8-sig'))
docker=json.loads((root/'logs/docker-retry-results.json').read_text(encoding='utf-8-sig'))
rows='\n'.join(f"| {x['test']} | {x['status']} |" for x in checks)
commands='\n'.join(f"| {x['command']} | {x['exit_code']} |" for x in docker)
text=f'''# ÉTAPE 1 — RAPPORT FINAL

Reprise du 16 octobre 2026, Europe/Paris. Le rapport précédent est conservé dans ETAPE-1-RAPPORT-AVANT-REPRISE.md.

**ÉTAPE 1 PARTIELLEMENT VALIDÉE.** Le choix d'une VM Ubuntu dédiée a été confirmé par l'utilisateur.
Cette VM est préparée dans les fichiers du projet, mais n'est pas créée ni accessible depuis cette session.
Docker Engine, PostgreSQL et n8n restent non opérationnels/non vérifiés. Aucun résultat distant n'est inventé.

## A. Diagnostic système précis

- Windows Server 2025 Standard, 24H2, x64, version 10.0.26100, UBR 33650: build complet **26100.33650**.
- InstallationType: Server. Fabricant **sangfor**, modèle **acloud**, HypervisorPresent=true: VM confirmée.
- Intel Xeon Cascadelake, 8 vCPU; 16 Go RAM, environ 10.3 Go disponibles lors de ce diagnostic.
- Disque C: 80 769 028 096 octets libres lors du diagnostic, environ 75.2 Gio.
- VirtualizationFirmwareEnabled, SecondLevelAddressTranslationExtensions et VMMonitorModeExtensions: false via CIM.
  Ces indicateurs ne prouvent pas à eux seuls le réglage de virtualisation imbriquée de Sangfor;
  l'administrateur de l'hyperviseur doit le confirmer. Aucune extension utilisable n'a été démontrée pour WSL2.
- WSL absent selon wsl --status et wsl --list --verbose. Lecture des fonctionnalités DISM refusée faute d'élévation:
  leur état exact n'est pas certifié. hns et vmcompute actifs ne prouvent pas que WSL2 fonctionne.
- Session non administrateur. Aucun essai d'élévation, activation Hyper-V/WSL ou redémarrage pendant cette reprise.

Windows Server 2025 prend en charge WSL2 sous réserve des prérequis; il ne faut pas confondre
cette prise en charge avec celle de Docker Desktop sur Windows Server.
Source: https://learn.microsoft.com/windows/wsl/install-on-server

## B. Réseau et droits

Profil Ethernet 2: Public, connectivité Internet signalée. Pare-feu actif pour Domain/Private/Public.
HTTPS vers download.docker.com/linux/ubuntu/gpg et archive.ubuntu.com/ubuntu/dists/noble/Release: HTTP 200.
Aucun HTTP_PROXY, HTTPS_PROXY ou ALL_PROXY dans les variables d'environnement de la session.
Les autres contraintes réseau, le port SSH vers la future VM, les redirections SSH et sudo sur cette VM restent non vérifiés.
Aucune règle de pare-feu, politique de sécurité, configuration sshd ou configuration hyperviseur modifiée.

## C. Composants réellement présents

Logiciels de l'étape précédente conservés: Python 3.15.0, pip 26.2.1, Git MinGit 2.56.0.windows.2,
Node 24.20.0 LTS / npm 11.19.0, Ollama 0.40.5, modèle qwen2.5:7b Q4_K_M, FastAPI dans backend/.venv.
Docker CLI 29.8.2 et Compose 5.6.0 préexistants conservés. **Aucun moteur Docker ou système Ubuntu installé pendant cette reprise.**
Docker Desktop n'a pas été installé, réinstallé, démarré ni reconfiguré.
Une clé SSH Ed25519 dédiée a été créée dans le profil Windows, sans écraser de clé existante.
Seule sa clé publique est dans docker/vm-authorized-key.pub. La clé privée reste hors projet, avec ACL utilisateur/SYSTEM/administrateurs.

## D. Architecture actuelle et architecture cible

Actuelle: Windows FastAPI 127.0.0.1:8000 -> Windows Ollama 127.0.0.1:11434. Aucun service Docker actif du projet.

Cible préparée, non déployée:

```text
Windows: FastAPI :8000 -----> Ollama :11434
             |
             +-- SSH local :55432 --> Ubuntu PostgreSQL :55432
Navigateur ----- SSH local :5678  --> Ubuntu n8n :5678
Windows FastAPI <-- SSH inverse <-- Ubuntu :18000 <-- n8n
```

VM Ubuntu Server 24.04 LTS x64 proposée: 4 vCPU, 8 Go RAM, 80 Go disque sur Sangfor.
Ces ressources sont à créer sur l'hyperviseur; elles ne sont pas réservées par cette session.
Pas d'hyperviseur supplémentaire dans Windows, pas de virtualisation imbriquée nécessaire pour cette VM distincte.
Les services Windows existants restent inchangés. Seul SSH est requis sur le réseau de gestion Ubuntu;
PostgreSQL, n8n et le tunnel inverse écoutent sur loopback.
La variante n8n utilise network_mode=host pour joindre le tunnel inverse et N8N_LISTEN_ADDRESS=127.0.0.1;
elle est destinée exclusivement à la VM dédiée, pas à un hôte partagé.

## E. Configuration et fichiers préparés

- compose.ubuntu-vm.yaml surcharge compose.yaml sans le reconstruire. Le backend conteneur est dans un profil inactif.
  Les services sélectionnés par défaut sont PostgreSQL et n8n; leurs secrets et volumes existants sont réutilisés.
- scripts/ubuntu-install-docker.sh: dépôt officiel Ubuntu/Docker; refuse les suppressions de paquets et préserve Docker s'il existe.
- scripts/vm_ops.py: déploiement dans un nouveau répertoire seulement, commandes Docker ciblées via SSH, tunnels, sauvegarde.
  Aucun contexte Docker global n'est modifié. SSH exige une clé et une empreinte d'hôte déjà vérifiée.
- scripts/ubuntu-backup.sh et ubuntu-restore.sh: dumps PostgreSQL, données n8n, clé de chiffrement, sources, empreintes SHA256.
- scripts/test-vm-integration.ps1: contrôles locaux/distants et test de persistance PostgreSQL optionnel.
- workflows/demo-extraction-vm.json: copie de démonstration pointant vers le tunnel inverse, inactive.
- docker/vm-cloud-init.yaml, vm-meta-data et vm-authorized-key.pub: éléments de préparation pour l'administrateur Sangfor.
  Les fichiers cloud-init ne créent pas une VM et leur prise en charge dans cet hyperviseur n'a pas été démontrée.
- docker/UBUNTU-VM.md: procédure complète, ressources, flux, conditions et sauvegarde/restauration.
- docker/FICHE-CREATION-VM.md: demande de création concrète, source ISO officielle et SHA256 attendu.
  Le téléchargement local optionnel de l'ISO a été interrompu; le fichier .partial est incomplet,
  non vérifié et inutilisable comme média. Aucun ISO installable n'est prétendu livré. Voir ubuntu-media.json.

Les sources de référence restent dans C:\\AGENT-SAGE-X3; la VM recevra une copie de déploiement.
Les données persistantes résideront sur son disque Linux et leurs sauvegardes seront copiées dans le répertoire privé backups/ Windows.
.env, backups/ et docker/vm.local.json sont exclus de Git; aucun dépôt distant utilisé.

## F. Commandes Docker réellement exécutées lors de la reprise

| Commande | Code de sortie |
|---|---:|
{commands}

Les commandes Compose ci-dessus utilisent -f compose.yaml -f compose.ubuntu-vm.yaml.
La commande up utilise -d postgres n8n; ps utilise --all.
Échec du moteur: pipe dockerDesktopLinuxEngine absent. Le contexte default échoue également.
Les commandes up/ps n'ont donc pas démarré de conteneur. config --quiet réussit sans avoir besoin du moteur.
Preuves brutes: docker-retry-results.json et docker-diagnostic-2026-10-16.txt.

## G. Tests exécutés lors de la reprise

| Contrôle | Résultat |
|---|---|
{rows}

Autres vérifications réellement effectuées: validation Compose de la surcharge (code 0),
liste des services sélectionnés postgres/n8n, compilation Python des scripts ajoutés,
analyse syntaxique PowerShell sans erreur, génération et lecture de l'empreinte de la clé SSH.
vm_ops.py check refuse proprement de continuer sans docker/vm.local.json (code 1).
Les scripts shell Ubuntu sont préparés et relus mais **non exécutés sous Linux** faute de cible disponible.

## H. PostgreSQL

Connexion FastAPI -> PostgreSQL: HTTP 503. Aucune base opérationnelle démontrée.
Tables, insertion/lecture, rollback et persistance après restart: SKIPPED, pas de moteur Linux accessible.
Les scripts et le schéma existants sont conservés. Aucun accès à SQL Server ni aux données Sage X3.

## I. n8n

Accès HTTP: échec de connexion. Conteneur, connexion DB, persistance, workflow et journaux non vérifiables.
La création du compte propriétaire local et le test du webhook restent à réaliser après déploiement effectif.
Le montage d'un volume et la présence d'un fichier workflow ne constituent pas une preuve de persistance ou d'exécution.

## J. FastAPI et Ollama

GET /health: HTTP 200. GET /health/ollama: HTTP 200. Ports 8000 et 11434 toujours liés à 127.0.0.1.
Les processus existants n'ont pas été redémarrés ni leur configuration modifiée lors de cette reprise.
Résultats historiques conservés, non relancés inutilement: 5 tests pytest réussis et 9/9 extractions
validées par Pydantic et comparées aux demandes synthétiques. Voir pytest.log, ollama-tests.json,
ollama-tests.md et ai-semantic-checks.json. Ces succès ne valident pas les services Docker absents.

## K. Sauvegarde et restauration préparées

Depuis Windows, après déploiement réel: vm_ops.py backup.
Le script distant suspend temporairement n8n, réalise les deux pg_dump, copie .n8n et .env,
inclut les sources et un manifeste SHA256, puis reprend n8n s'il était actif.
L'archive contenant des secrets est rapatriée par SSH dans C:\\AGENT-SAGE-X3\\backups, exclu de Git et à ACL privée.
Les dumps sont cohérents par base, pas un instantané atomique entre les deux bases.

Restauration uniquement sur un nouvel hôte/projet avec volumes absents: vérifier la provenance de l'archive,
extraire les sources, remettre le .env original en mode 600, installer Docker, lancer ubuntu-restore.sh
avec le répertoire de sauvegarde extrait. Le script refuse tout volume de projet préexistant.
La clé de chiffrement n8n doit rester la même. Refaire tous les tests, y compris persistance après restart.
La sauvegarde Docker n'inclut pas le modèle Ollama Windows ni le venv Windows: conserver les sources et le verrou
de dépendances, puis recréer le venv sur une cible compatible et conserver/retélécharger le modèle.
**Aucune sauvegarde de volumes Docker ni restauration n'a encore été testée.**
Procédure détaillée: docker/UBUNTU-VM.md.

## L. Démarrage et arrêt

Les services Windows fonctionnent déjà. Leurs commandes existantes restent disponibles:
scripts/start.ps1 -BackendOnly et scripts/stop.ps1 -BackendOnly.

Après fourniture de la VM, configuration de docker/vm.local.json et vérification SSH:

```powershell
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py deploy
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py provision
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py start
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py status
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py tunnel
# Le tunnel reste actif; lancer les tests dans une autre session:
.\\scripts\\test-vm-integration.ps1 -TestPersistence
# Arrêt des conteneurs du projet uniquement:
.\\backend\\.venv\\Scripts\\python.exe scripts\\vm_ops.py stop
```

La copie deploy refuse d'écraser un répertoire distant existant. La configuration SSH n'est pas installée avec une adresse fictive.
Pas de démarrage automatique des conteneurs au boot. Après reboot de la nouvelle VM, Docker devra être démarré explicitement.

## M. Intervention restante, ciblée

Créer ou fournir la VM Ubuntu dédiée sur Sangfor. Cette session n'a ni accès à la console Sangfor,
ni adresse d'une VM Ubuntu existante, ni identité SSH cible vérifiée.
Fournir l'adresse de gestion, le nom du compte SSH, l'empreinte de sa clé d'hôte et autoriser la clé publique préparée.
Le compte doit disposer du mode sudo nécessaire au provisionnement et aux commandes Docker du projet.
La compatibilité du format d'import/cloud-init Sangfor doit être vérifiée côté administrateur.
Aucun mot de passe ou clé privée à envoyer dans le chat.

## N. Erreurs et limites restantes

Docker Engine inaccessible; PostgreSQL et n8n absents; intégration distante, persistance et restauration non démontrées.
WSL2 n'a pas été activé et n'est plus la voie retenue après le choix utilisateur de la VM dédiée.
Aucun arrêt/redémarrage Windows, modification de protection ou de service existant, suppression de données ou accès Sage X3.

## O. Conclusion

**ÉTAPE 1 PARTIELLEMENT VALIDÉE.** La préparation de la VM dédiée et des outils de reprise est terminée.
La validation complète reste bloquée par l'absence d'une VM Linux accessible; les critères Docker/PostgreSQL/n8n,
connexions interservices et persistance devront tous être vérifiés réellement avant validation.
Arrêt à l'étape 1; aucune fonctionnalité de l'étape 2 commencée.
'''
(root/'logs/ETAPE-1-RAPPORT-FINAL.md').write_text(text,encoding='utf-8')
print('Updated logs/ETAPE-1-RAPPORT-FINAL.md; status: PARTIELLEMENT VALIDEE')
