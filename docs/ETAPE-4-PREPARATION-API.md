# Étape 4 — Lecture de la création manuelle et préparation locale

Évolution : le parcours multi-objets avec approbations et endpoints d'exécution **verrouillés par défaut** est maintenant décrit dans `ETAPE-4-API-CRUD.md`.
Cette page décrit le formulaire article initial, conservé pour compatibilité; ses propres routes ne déclenchent pas d'écriture.

L'article TSTAI2610174D94B4 a été créé manuellement par l'opérateur, puis relu par le projet.
Le projet n'a envoyé aucun save et ne doit pas recréer cet article.
Dans http://127.0.0.1:8000/sage/, saisir le jeton local puis cliquer sur **Lire l’article testé**.
La fiche affiche les données réelles, notamment catégorie NEG, unités SAC, gestion des lots et code comptable.

## Formulaire

« Préparer une création · TEST » produit un XML et conserve un brouillon PostgreSQL local.
Les paramètres ne sont pas préremplis à partir de l'article manuel; celui-ci n'est pas une configuration universelle.
Référence, désignation, catégorie, unités et coefficients sont explicites. Statut, gestion stock/lots et code comptable
peuvent être ajoutés; leur caractère obligatoire reste une règle métier du dossier, pas une déduction du formulaire.
Les coefficients sont des décimaux positifs, au plus six décimales; les menus sont contrôlés contre la publication réelle.
Les huit champs de base et quatre complémentaires suivent l'ordre du XML manuel communiqué.
Aucun groupe statistique FG ou autre défaut de l'ancien brouillon DIVE n'est imposé.

## API

Les routes exigent le jeton `X-Approval-Token`, jamais les identifiants Sage dans le navigateur.

- POST `/api/v1/sage/article-preparations` : entrée Pydantic stricte, lecture de getDescription, vérification du code par read,
  sérialisation XML puis insertion locale. Aucun POST SOAP save.
- GET `/api/v1/sage/article-preparations/{uuid}` : relecture du brouillon local sans nouvel appel Sage.

Exemple fictif de corps de préparation; ce code n'est pas créé :

```json
{
  "reference": "TST_BROUILLON",
  "designation": "Brouillon à examiner humainement",
  "categorie": "NEG",
  "unite_stock": "SAC",
  "unite_achat": "SAC",
  "unite_vente": "SAC",
  "coefficient_achat": "1",
  "coefficient_vente": "1",
  "statut": "1",
  "gestion_stock": "2",
  "gestion_lots": "3",
  "code_comptable": "CPJ35"
}
```

Ces valeurs reproduisent les paramètres du cas manuel, sans affirmer qu'elles conviennent à un autre article.
Dans le XML, CPJ35 est la valeur de **ACCCOD (code comptable)**, pas le code de l'article à dupliquer.

La réponse comprend un UUID, le XML, son empreinte SHA256 et les contrôles :

- `blocked_existing` : le code existe réellement, création bloquée;
- `blocked_unknown` : l'absence n'est pas établie, création bloquée;
- `awaiting_human_review` : absence constatée, brouillon à examiner, pas une permission de créer.

`requires_human_approval=true`, `human_approved=false` et `sage_write_enabled=false` sont calculés côté serveur.
Les champs tels que approved, folder, operation sont refusés à l'entrée. L'utilisateur ne choisit pas un dossier de production.
Seul le message SOAP explicite « Fiche inexistante » avec statut 0 est interprété comme une absence.
Une erreur de droits, un timeout ou une réponse incohérente ne permettent pas de conclure que le code est libre.
La vérification ne réserve pas la référence : elle devra être refaite juste avant toute écriture ultérieure autorisée.

## Approbation humaine

Les routes de ce formulaire initial ne fournissent pas d'exécution ou d'approbation autorisant implicitement save.
Le formulaire ne présente aucun bouton « Créer » ni aucune approbation automatique.
L'application Sage reste limitée à getDescription/query/read au niveau du transport.
Un futur envoi devra passer par une revue des règles, une approbation humaine explicite du contenu final et
une autorisation distincte d'une seule tentative. Un brouillon conservé, même après revue, ne vaut pas cette autorisation.

## PostgreSQL local et migration

Schéma projet configuré, par défaut sage_ai :

- `soap_article_preparations` : paramètres, XML, empreinte, contrôles, statut et date;
- `soap_article_observations` : observations relues dans Sage et provenance déclarée des informations manuelles.

Migration additive 004, sans changement des données ou tables Sage :

```powershell
cd C:\AGENT-SAGE-X3\backend
.\.venv\Scripts\python.exe ..\scripts\step4_admin.py
```

Le checksum est vérifié lors d'une nouvelle exécution. La migration n'est pas appliquée automatiquement à l'import de FastAPI.
Les anciennes migrations, routes et barrières d'écriture sont conservées.

## Tests

```powershell
cd C:\AGENT-SAGE-X3\backend
$env:RUN_STEP2_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests -q
cd ..
node frontend\tests\step4-browser.mjs
```

Le test navigateur utilise le code déjà créé et vérifie le blocage du doublon dans le formulaire;
il crée seulement un brouillon local et n'envoie aucune écriture Sage.
Les essais positifs sur code absent utilisent des mocks et une base locale isolée, jamais une création réelle.

## XML manuel et limites de l'analyse

Le corps fourni par l'opérateur est conservé dans examples/step4/manual-success-object.xml.
Les douze champs transmis correspondent aux valeurs relues dans Sage, constat indépendant de son annonce de statut 1.
Les deux avertissements sur coefficients ont été signalés par l'opérateur, mais leur libellé et la réponse save complète
n'ont pas été fournis. Les coefficients enregistrés valent 1 : cela ne permet pas de reconstituer les avertissements ni leur cause.
Les liens Request/Response du testeur Syracuse ne sont pas une copie de la réponse SOAP.
Le résultat manuel ne valide pas les anciens paramètres DIVE ni toutes les règles possibles de NEG.

La sauvegarde native couvre les nouvelles tables et sources. Le XML manuel et les observations sont des données internes;
les rapports dans logs doivent être copiés séparément lors d'un transfert si nécessaire.
