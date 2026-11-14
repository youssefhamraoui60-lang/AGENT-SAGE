# Architecture preparee — Ubuntu dedie, services Windows conserves

Etat: PREPARE, NON DEPLOYE. Aucun acces VM Ubuntu fourni. Ne pas confondre validation Compose et tests reels des services.

## Diagnostic du 16 octobre 2026

Windows Server 2025 Standard 24H2, 10.0.26100.33650, x64, installation Server.
VM confirmee: fabricant sangfor, modele acloud, HypervisorPresent=true.
8 vCPU; 16 Go RAM; environ 10.3 Go disponibles lors du nouveau diagnostic; environ 75 Go libres sur C:.
VirtualizationFirmwareEnabled=false, SLAT=false, VMMonitorModeExtensions=false dans l'invite.
Ces extensions ne sont pas visibles via ces indicateurs CIM; le materiel physique ne peut pas etre audite depuis cette session.
Le statut exact de la virtualisation imbriquee doit etre confirme dans Sangfor; CIM seul ne suffit pas a certifier son reglage.
WSL absent. La lecture DISM des fonctionnalites necessite une elevation: leur etat exact reste NON VERIFIE.
vmcompute et hns sont actifs, ce qui ne prouve pas la disponibilite de WSL2.
Session non administrateur. Docker Desktop preexistant reste intact, moteur inaccessible.
Reseau Windows public, pare-feu active pour les trois profils. Aucune modification de regle.
HTTPS download.docker.com et archive.ubuntu.com teste: HTTP 200. Aucun proxy HTTP(S)/ALL defini dans l'environnement.
Acces SSH, transfert TCP et sudo sur la future VM: non testables sans VM cible.

## Choix possibles et intervention ciblee

Windows Server 2025 prend en charge WSL2. Ce serveur ne satisfait pas actuellement les prerequis observes.
Pour WSL2: l'administrateur Sangfor doit confirmer la prise en charge puis exposer les extensions VT-x/SLAT
a cette VM. Ne pas appliquer les commandes Hyper-V de Microsoft a Sangfor: c'est un autre hyperviseur.
Cette operation peut necessiter un arret de la VM: a planifier et autoriser explicitement.
Ensuite seulement, faire autoriser l'installation/activation de WSL et VirtualMachinePlatform en session elevee,
et tout redemarrage eventuellement requis. Aucun de ces changements n'a ete lance.

Alternative preparee: creer sur l'hyperviseur une VM Ubuntu Server 24.04 LTS x64, distincte de la VM Windows.
Dimensionnement propose pour PostgreSQL+n8n: 4 vCPU, 8 Go RAM, disque 80 Go, ajustable selon les charges futures.
Ce dimensionnement est une proposition, pas une mesure d'une VM existante. Aucun GPU requis sur Ubuntu.
Pas besoin de virtualisation imbriquee pour Docker Linux dans cette VM distincte.
Acces necessaire: adresse/alias SSH, utilisateur, cle autorisee, empreinte SSH verifiee, sudo pour installation/Docker.
Le reseau de gestion doit autoriser Windows -> Ubuntu TCP 22 et les sorties HTTPS des depots/registres.
Les redirections SSH locales et distantes doivent etre permises par sshd; aucun changement automatique de sshd.
Ne pas fournir de mot de passe dans le chat ou dans un depot Git.

## Flux proposes

Windows FastAPI 127.0.0.1:8000 -> Windows Ollama 127.0.0.1:11434 (deja teste).
Windows FastAPI -> tunnel SSH local 127.0.0.1:55432 -> PostgreSQL Ubuntu 127.0.0.1:55432.
Navigateur Windows -> tunnel SSH local 127.0.0.1:5678 -> n8n Ubuntu 127.0.0.1:5678.
n8n -> Ubuntu 127.0.0.1:18000 -> tunnel SSH inverse -> Windows FastAPI 127.0.0.1:8000.
Ollama ne quitte pas Windows et aucun de ses ports n'est publie sur le LAN.
Seul SSH est joignable sur le reseau de gestion de la VM Ubuntu.

compose.ubuntu-vm.yaml reutilise compose.yaml. Le backend conteneur est place dans un profil inactif:
le backend Windows existant reste le service utilise. PostgreSQL conserve son reseau interne et son volume.
n8n utilise le reseau de l'hote Linux pour atteindre le tunnel inverse sur loopback, avec N8N_LISTEN_ADDRESS=127.0.0.1.
Ce choix donne a n8n acces au reseau de la VM dediee; il ne faut pas employer cette variante sur un hote partage.
Les capacites Linux restent retirees et aucun socket Docker ou montage Windows sensible n'est donne a n8n.
Les sources de reference restent dans C:\AGENT-SAGE-X3; la VM recoit une copie de deploiement.
Les volumes Docker sont sur le disque Linux et leurs sauvegardes sont rapatriees dans C:\AGENT-SAGE-X3\backups.

## Deploiement apres fourniture de la VM

Le choix VM dediee a ete confirme par l'utilisateur pendant cette reprise.
Fichiers remis a l'administrateur Sangfor:
- vm-authorized-key.pub: cle publique du projet, a placer dans authorized_keys du compte Ubuntu.
- vm-cloud-init.yaml et vm-meta-data: option cloud-init si le mode d'import de l'hyperviseur la prend en charge.
  Le compte par defaut d'une image cloud Ubuntu est normalement ubuntu; verifier le compte cree sur la cible.
  Ces fichiers ne sont pas un ISO amorcable et ne creent aucune VM a eux seuls.
- Installer Ubuntu Server 24.04 LTS x64 sur une nouvelle VM 4 vCPU / 8 Go RAM / 80 Go disque.
  La prise en charge du format d'image et de cloud-init dans cette version Sangfor reste a confirmer par l'administrateur.
  Pour une installation par ISO, ajouter la cle publique via la console et configurer le compte sudo autorise.

La cle privee dediee reste dans le profil Windows, ~/.ssh/agent_sage_vm_ed25519, avec ACL privee.
Elle n'est ni copiee dans le projet ni incluse dans les sauvegardes. Aucun fichier SSH existant n'est ecrase.
Apres obtention de l'IP et de l'empreinte d'hote verifiee, ajouter explicitement a la configuration OpenSSH utilisateur:

```text
Host sage-docker-vm
    HostName ADRESSE_IP_FOURNIE_PAR_ADMIN
    User ubuntu
    IdentityFile ~/.ssh/agent_sage_vm_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking yes
```

Ce bloc n'est pas installe tant que l'IP, l'utilisateur reel et l'empreinte SSH ne sont pas connus.

Copier docker/vm.example.json vers docker/vm.local.json et remplacer ssh_target par un alias SSH verifie.
Configurer la cle dans le profil OpenSSH Windows. Ne jamais desactiver StrictHostKeyChecking.
L'outil utilise sudo -n: en cas de refus, l'administrateur doit choisir le mode d'execution autorise,
sans modification automatique de sudoers. Il refuse de supprimer des paquets existants ou d'ecraser un repertoire distant.

Depuis C:\AGENT-SAGE-X3, utiliser backend/.venv/Scripts/python.exe pour:

```powershell
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py deploy
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py provision
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py check
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py start
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py status
# Conserver le processus SSH en execution; Ctrl+C ferme uniquement les tunnels.
.\backend\.venv\Scripts\python.exe scripts\vm_ops.py tunnel
```

Installer seulement Docker Engine, CLI, containerd et les plugins Compose/Buildx manquants depuis le depot officiel Docker.
Le script provision cible Ubuntu 24.04 dedie. Les services d'une nouvelle installation ne sont pas actives au boot.
Si Docker est preexistant, il est conserve et son etat est controle.
Le projet utilise restart=no; apres reboot Ubuntu, demarrer Docker explicitement avec sudo systemctl start docker.
Arret des seuls conteneurs du projet: `vm_ops.py stop`. Aucun volume n'est supprime.
Ne pas lancer scripts/start.ps1 sans -BackendOnly sur Windows: cette commande cible encore le contexte Docker Windows.

## Tests a executer et preuves attendues

1. vm_ops.py check: docker info Linux et version Compose; enregistrer la sortie sans secrets.
2. vm_ops.py start: compose config, up -d --wait puis vm_ops.py status.
3. Avec le tunnel actif: scripts/test-vm-integration.ps1. Il teste DB via FastAPI, tables, insertion/lecture et rollback.
4. Ajouter -TestPersistence pour un restart controle des seuls conteneurs postgres/n8n, puis relire le marqueur DB.
5. Verification n8n: healthz/readiness, requete SQL base n8n et volume monte, puis import workflow de test.
6. Creer le compte proprietaire local n8n dans le navigateur, importer workflows/demo-extraction-vm.json.
7. Cliquer Listen for test event et envoyer une demande synthetique au webhook-test.
8. Exporter le workflow avant/apres restart pour prouver sa persistance, verifier l'acces HTTP et les logs.

Ces tests sont obligatoires avant validation finale. Le simple montage d'un volume ne prouve pas sa persistance.

## Sauvegarde et restauration pour transfert

`vm_ops.py backup` execute ubuntu-backup.sh puis rapatrie l'archive par SSH dans backups/.
La sauvegarde arrete temporairement n8n et le redemarre seulement s'il etait actif. Elle n'arrete pas PostgreSQL
ni les services Windows. Les dumps pg_dump sont coherents par base; les deux bases ne constituent pas un instantane atomique commun.
Contenu: dumps backend/n8n, repertoire .n8n, .env original avec cle de chiffrement n8n, sources et SHA256SUMS.
Les archives contiennent des secrets: repertoire prive Windows/Linux; transfert chiffre SSH; exclues de Git.
Les permissions protegeant un fichier ne sont pas un chiffrement au repos: conserver le support de sauvegarde dans le stockage protege de l'entreprise.
Un manifeste SHA256 detecte une alteration accidentelle, pas l'authenticite d'une archive provenant d'un tiers.

Pour restaurer: nouvelle VM Ubuntu et nouveaux volumes uniquement. Verifier la provenance et extraire l'archive,
verifier SHA256SUMS, extraire source.tar.gz dans un nouveau repertoire de projet, y copier environment.env en .env
avec mode 600, installer Docker avec le script fourni, puis:

```bash
sudo bash scripts/ubuntu-restore.sh /chemin/absolu/sauvegarde-extraite
```

Le script refuse si les volumes agent-sage-x3_pgdata ou agent-sage-x3_n8ndata existent.
Il restaure les dumps et le repertoire n8n, puis attend les healthchecks.
Un conteneur auxiliaire temporaire utilise root et la seule capacite CHOWN pour rendre le volume .n8n a l'UID 1000.
Les services permanents conservent leurs restrictions de capacites.
Refaire tous les tests d'integration et un cycle de sauvegarde/restauration sur volumes neufs avant de declarer la methode validee.
La methode est preparee; aucune sauvegarde de donnees Docker ni restauration n'a pu etre executee faute de moteur.

Pour transferer aussi la partie Windows, conserver la racine C:\AGENT-SAGE-X3 et son .env protege,
recreer le venv depuis requirements.lock.txt sur la cible compatible, et conserver/retelcharger qwen2.5:7b
dans Ollama. Les fichiers du modele Ollama sont hors du depot et hors de l'archive Docker;
la sauvegarde Docker seule ne suffit donc pas a une reprise Windows hors ligne.

Sources officielles consultees:
- https://learn.microsoft.com/windows/wsl/install-on-server
- https://learn.microsoft.com/windows/wsl/troubleshooting
- https://docs.docker.com/engine/install/ubuntu/
- https://docs.docker.com/reference/compose-file/merge/
- https://docs.n8n.io/hosting/configuration/environment-variables/deployment/
