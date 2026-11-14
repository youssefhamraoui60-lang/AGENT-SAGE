# VM à créer dans Sangfor aCloud

Choix utilisateur confirmé: VM Ubuntu dédiée, sans modification de la VM Windows existante.
Cette fiche prépare l'intervention; aucune VM n'a été créée par Codex.

| Paramètre | Valeur proposée |
|---|---|
| Nom | agent-sage-docker |
| Système | Ubuntu Server 24.04 LTS x64 |
| CPU | 4 vCPU |
| RAM | 8 Go |
| Disque | 80 Go, extensible |
| Réseau | Réseau de gestion privé joignable depuis Windows |
| Entrée réseau nécessaire | SSH TCP 22 depuis la VM Windows |
| Sorties nécessaires | DNS, HTTPS dépôts Ubuntu/Docker et registres d'images |
| PostgreSQL / n8n | Écoute localhost uniquement, accès Windows par tunnels SSH |
| Virtualisation imbriquée | Non nécessaire pour cette VM Linux distincte |

Installer OpenSSH Server pendant l'installation Ubuntu. Autoriser uniquement la clé publique
fournie dans vm-authorized-key.pub pour le compte destiné au projet. Configurer le mode sudo autorisé
pour installer Docker depuis son dépôt officiel et administrer les conteneurs dédiés.

Les fichiers vm-cloud-init.yaml et vm-meta-data constituent une option pour une image cloud compatible.
Ils ne sont pas un ISO, n'installent pas Docker et ne doivent pas être employés comme un autoinstall Ubuntu.
L'administrateur doit vérifier si sa version de Sangfor accepte ce mode de personnalisation.
Sinon, installer depuis l'ISO officielle Ubuntu et ajouter la clé publique via la console.

Source ISO vérifiée dans le catalogue officiel:
https://releases.ubuntu.com/24.04/ubuntu-24.04.5-live-server-amd64.iso
SHA256 attendu depuis SHA256SUMS obtenu par HTTPS officiel:
`97f3d7ffb032c3eb3b23d2c8be9cc76e60c2c1f2c0146ba5ba9fe01cafae0fd8`.
Vérifier à nouveau le catalogue et le SHA256 au moment de l'installation.
La copie locale .tools/ubuntu/*.partial est incomplète et inutilisable comme ISO.
Le téléchargement optionnel a été interrompu; aucun média Ubuntu prêt à démarrer n'est livré.

Informations à retourner après création:

1. Adresse IP ou nom DNS de gestion.
2. Nom du compte SSH effectivement créé.
3. Empreinte SHA256 de la clé d'hôte SSH, obtenue par un canal fiable, par exemple la console Ubuntu:
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
4. Confirmation que la clé publique du projet est autorisée et indication du mode sudo autorisé.

Ne transmettre aucun mot de passe ni clé privée dans le chat. La clé privée du projet reste
dans le profil Windows `.ssh/agent_sage_vm_ed25519`.

La création de cette VM et ses éventuelles règles réseau relèvent de l'administrateur Sangfor.
Aucun accès à Sage X3 ou SQL Server, aucun redémarrage de Windows et aucune modification de son pare-feu ne sont nécessaires pour cette préparation.
