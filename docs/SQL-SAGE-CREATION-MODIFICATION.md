# SQL Sage : lecture, création et modification

Ce document décrit le code livré ; il ne lance aucune écriture. SQL Server Sage
et PostgreSQL de l'agent sont deux moteurs différents. Les fichiers
`backend/migrations/*.sql` sont PostgreSQL ; `TEST` et `OB` sont les dossiers
(schémas) de la base SQL Server `x3v12`.

## Carte du code opérationnel

| Usage | Source utilisée |
|---|---|
| Lecture Sage bornée | `scripts/chat_sql_queries.ps1`, `scripts/chat_sql_worker.ps1`, `scripts/chat_sql_tools.ps1` |
| Commandes SOB | `telegram-test/prepare.py`, `creation.py`, `sob-execute.ps1`, `sob-create.sql` |
| Droits commandes TEST | `telegram-test/sage-sob-enable-creation.sql`, `sage-sob-permissions.sql` |
| Droits commandes OB (fichier distinct) | `telegram-test/sage-sob-enable-creation-ob.sql` : ne pas exécuter pour restaurer le routage TEST |
| Création article | `backend/app/services/article_sql.py`, `TEST/article_sql_worker.ps1`, `TEST/article_transaction.sql`, `TEST/article_catalog.sql` |
| Création fournisseur | `backend/app/services/supplier_sql.py`, `TEST/sql_worker.ps1`, `TEST/Read-SupplierDefaults.ps1` |
| Modifications | `backend/app/services/erp_modification.py`, `modification_policy.py`, `modification_resolvers.py`, `TEST/modification_worker.ps1` |
| Anciennes propositions SQL | `sql/direct-test-review/` : prototypes commentés, pas une procédure de déploiement complète |
| Historique SOAP | `scripts/SageTestSoap.psm1`, `SageTestArticleSites.psm1` : distinct du chemin SQL |

Ne pas supprimer `TEST` sous prétexte que ce nom ressemble à des tests : ce
répertoire contient des workers réellement utilisés par le backend.

## Connexion et lecture avant action

Les workers .NET lisent généralement `runtime/sql-reader-credential.clixml`.
Sur un nouveau compte Windows, le recréer avec `Get-Credential | Export-Clixml`.
Les chaînes effectives figurent dans les workers ; plusieurs sont fixes à
`tcp:sage,1433` / `x3v12`. Vérifier chaque canal et chaque dossier.

Exemples à exécuter dans SSMS, après choix explicite de la bonne base :

```sql
USE [x3v12];
SELECT TOP (20) ITMREF_0, ITMDES1_0, STU_0, SAU_0
FROM [TEST].[ITMMASTER] ORDER BY ITMREF_0;
SELECT TOP (20) BPCNUM_0, BPCNAM_0
FROM [TEST].[BPCUSTOMER] ORDER BY BPCNUM_0;
SELECT TOP (20) BPSNUM_0 FROM [TEST].[BPSUPPLIER] ORDER BY BPSNUM_0;
```

Utiliser paramètres .NET et requêtes fixes pour toute saisie utilisateur. Un
document, un mail ou une sortie de modèle ne doit jamais être interprété comme SQL.

## Créer une commande avec les contrôles existants

`creation.build_payload(details)` valide le brouillon. `creation.review(owner,
details)` appelle `sob-execute.ps1` en mode `preview`, conserve le `PLAN_JSON`,
une référence idempotente SOB et une expiration. Le script SQL contrôle client,
sites, dates, lignes, articles, unités, TVA, total et numérotation.

Pour une simulation technique, envoyer UNIQUEMENT un payload produit par
`build_payload`, avec `mode="preview"`, à `creation.run_script('sob-execute.ps1',
payload)`. Les exemples privés vérifiés sont dans les rapports de contrôle et
`runtime/sob-improvements-20261113/sql-previews-final.json` du ZIP complet.
Ne pas copier leurs clients/quantités pour une autre demande.

L'exécution passe par `creation.confirm(...)` avec validation du canal autorisé,
relecture des droits, vérification d'expiration et plan attendu identique.
`sob-create.sql` utilise des transactions, verrouillage et références de reçu.
Le script n'est PAS un fichier à lancer sans paramètres dans SSMS. Il peut
écrire `SORDER`, `SORDERP`, `SORDERQ`, `SVCRVAT` et la numérotation `AVALNUM`.
Il ne faut jamais assembler ces INSERT indépendamment ou modifier un compteur
pour obtenir un numéro voulu.

La réussite SQL n'assure pas à elle seule tous les états métier Sage (signature,
livraison, facturation) : contrôler dans l'interface après création autorisée.
En cas de résultat incertain, consulter le reçu et la référence existante avant
toute nouvelle demande. Ne pas supprimer les SQLite pour forcer une reprise.

## Fournisseurs et articles

Passer par les services et workers livrés : ils calculent les dépendances,
référentiels, unités et taxes, préparent le plan, puis exécutent dans le dossier
explicitement autorisé. Un fournisseur peut impliquer BPARTNER, BPSUPPLIER,
adresses, contacts et données fiscales ; un article peut impliquer ITMMASTER,
sites, unités, taxes et références fournisseur. Un INSERT dans une seule table
n'est pas équivalent à la création d'un objet Sage complet.

La configuration e-mail fournisseurs et celle des commandes Telegram sont
indépendantes. Ne pas convertir le routage des commandes en OB pour remettre en
service l'e-mail fournisseurs. Vérifier les doublons ICE/IF/RC et le code de reçu.

## Modifier un objet existant

Le chemin supporté est : identifier l'objet et le dossier, prendre un snapshot,
résoudre unités/catégories/dépendances, produire le plan de changement, le
valider puis exécuter `TEST/modification_worker.ps1` via `erp_modification`.
Le worker doit recevoir un plan du service, jamais un nom de colonne choisi par
le modèle. Les états terminaux/ambigus ne sont pas relancés automatiquement.

Pour une intervention DBA exceptionnelle : sauvegarde Sage préalable, clé exacte,
valeur attendue, transaction et contrôle `@@ROWCOUNT`, puis contrôles métier et
dépendances avant COMMIT. Ce motif seul ne remplace pas les règles métier :

```sql
SET XACT_ABORT ON;
BEGIN TRANSACTION;
-- SELECT ... WITH (UPDLOCK, HOLDLOCK) WHERE clé = @clé ;
-- Vérifier l'ancienne valeur et toutes les dépendances.
-- UPDATE ... SET colonne_autorisée = @nouvelle WHERE clé = @clé AND ... ;
-- IF @@ROWCOUNT <> 1 THROW 51000, 'Conflit ou clé non unique', 1;
ROLLBACK TRANSACTION; -- simulation ; aucun UPDATE exécutable fourni ici
```

Ne pas publier des valeurs fiscales, comptes SQL, clés, plans clients ou exports
Sage dans GitHub. Le ZIP public contient la méthode et le code, pas les données.
Une restauration complète de l'ERP nécessite le `.bak` SQL Server du DBA ; les
dumps PostgreSQL ne sauvegardent pas la base Sage distante.
