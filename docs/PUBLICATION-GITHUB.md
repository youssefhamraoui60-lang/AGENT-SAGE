# Publication du code et des sauvegardes dans GitHub

Dépôt demandé : https://github.com/youssefhamraoui60-lang/AGENT-SAGE

Le dépôt est public. Publier le code après export filtré. Les sauvegardes
applicatives complètes sont publiées comme fichiers de release chiffrés
AES-256-GCM ; ne jamais publier le ZIP complet en clair.
L'export public est un dépôt Git indépendant ; le dépôt de travail original est
préservé. Son rapport `PUBLIC-EXPORT-REPORT.json` indique les fichiers filtrés.

Depuis le poste actuel, authentifier Git sans écrire de jeton dans un fichier :

```powershell
cd C:\AGENT-SAGE-X3
. ./scripts/tools.ps1
git credential-manager github login --device --username youssefhamraoui60-lang --no-ui
```

Ouvrir l'URL affichée par Git Credential Manager et saisir le code temporaire
dans le navigateur. Le code et le jeton d'accès ne font pas partie de la sauvegarde.
Puis, dans le dossier public indiqué au rapport de livraison :

```powershell
git status --short
git remote -v
git push -u origin main
```

Le commit et le remote sont déjà préparés. Ne pas utiliser `--force`. Si le
dépôt contient entre-temps un autre commit, récupérer et examiner celui-ci avant
de pousser. Vérifier ensuite les fichiers et le commit dans GitHub. Une réussite
locale de `git commit` n'est pas une preuve de publication distante.

Pour de nouvelles versions : refaire l'export public, contrôler le filtrage et
les dépendances avant publication. L'export n'est pas un audit de sécurité complet.

## Sauvegarde complète versionnée

La première archive est [Backup V1 — 2026-11-14](https://github.com/youssefhamraoui60-lang/AGENT-SAGE/releases/tag/backup-V1-2026-11-14).
Les dix fichiers `.aes` contiennent le ZIP chiffré, totalisant 13 661 076 694
octets. La clé de déchiffrement est conservée séparément, jamais dans GitHub.

Après des modifications du code ou des données, créer une nouvelle sauvegarde
complète de la version validée et publier un nouveau nom et tag immuables
(`Backup V2 — AAAA-MM-JJ`) avec une nouvelle clé. Le code avance séparément sur
`main`; chaque release conserve l'état complet associé à sa date. Ne pas
remplacer V1, ses fichiers ni sa clé. Vérifier les empreintes et la restauration
avant de supprimer les copies temporaires.

Pour restaurer V1, télécharger les dix assets dans un dossier et utiliser
`scripts/restore_encrypted_release_v1.py`, le guide A à Z et la clé séparée.
