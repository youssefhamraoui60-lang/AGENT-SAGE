# Publication du code dans GitHub

Dépôt demandé : https://github.com/youssefhamraoui60-lang/AGENT-SAGE

Le dépôt est public. Publier uniquement le dossier d'export public préparé par
`scripts/export_public_source.py`, jamais le ZIP COMPLET, les dumps ou `.env`.
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
