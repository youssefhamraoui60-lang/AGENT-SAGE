# Intégration SOAP Python / FastAPI — 27 octobre 2026

Le succès PowerShell de TESTSOAP003 est une preuve fournie par l'utilisateur.
Le XML exact envoyé n'est pas présent dans les fichiers locaux recherchés : aucune
équivalence exacte ni création Python réussie n'est revendiquée.

## Code et fonctionnement

Le client existant `sage_soap.py` utilise Zeep et Requests avec validation du nom,
de la chaîne et des CRL, sans redirection ni retry des requêtes. `sage_gateway.py`
utilise le contexte FRA / POOL_AI_TEST, WS_ARTICLE et un XML métier PARAM/GRP/FLD/LST.
La description doit confirmer V12/TEST et ITM. La méthode générique `call` ne peut
plus appeler save/modify : seule `write_once`, après consommation de l'approbation,
dispose du transport d'écriture.

Le parcours FastAPI existant reste :

1. POST `/api/v1/sage/articles/prepare` avec `Preparation` (champs publiés).
2. Revue du XML, du digest et des contrôles retournés.
3. POST `/api/v1/sage/operations/{id}/approve`, confirmation humaine explicite,
   acteur, raison et digest ; jeton valable 15 minutes et utilisable une fois.
4. POST `/api/v1/sage/articles` avec l'identifiant et le jeton.

Les étapes 3 et 4 restent HTTP 423 tant que les droits et la politique ne sont
pas validés. Aucun paramètre actif ni secret n'a été modifié par cette intégration.
Le contrôle opérateur existant doit rester en place ; l'identité de l'approbateur
reste déclarative et doit être raccordée à une identité authentifiée avant ouverture.

Le doublon est vérifié par SOAP READ lors de la préparation et juste avant
l'exécution. Une réponse inconnue bloque la création. L'approbation est consommée
en transaction PostgreSQL avant le SAVE. Aucun nouvel essai après un résultat
incertain ; seule une relecture est permise. La réponse SOAP est archivée et les
champs sont comparés à la relecture. Ce parcours ne fournit pas encore de preuve
SQL automatique après SAVE ; la recette Python autorisée devra aussi faire le SELECT.

## Contrôles métier ajoutés

`sage_article_rules.py` exige un référentiel TEST revu, daté, non expiré, lié à
l'empreinte getDescription et protégé par SHA-256 dans la politique existante :
`permissions.articles.create.business_rules_evidence` (path et sha256).
L'absence du référentiel bloque la préparation. Le même contenu est exigé avant SAVE.

Format JSON attendu du fichier de règles :

```json
{
  "solution": "V12",
  "folder": "TEST",
  "reviewed": false,
  "expires_at": "2000-01-01T00:00:00+00:00",
  "description_sha256": "EMPREINTE_REELLE",
  "required_fields": [],
  "active_units": [],
  "categories": {}
}
```

Chaque catégorie doit déclarer `active`, `manual_keys`, `statuses`, `units`
(STU/PUU/SAU), `unit_combinations` (dictionnaires de chemins de champs et valeurs,
avec les coefficients nécessaires), `tax_fields`, `tax_combinations`,
`tax_default_verified`, `allowed_fields`, `requires_article_site`,
`supplier_required`, `supplier_fields`. Les valeurs proviennent d'un export TEST
revu ; aucune catégorie, unité ou taxe de production n'est inventée.

Les champs obligatoires de base et OBL=1 de la publication sont contrôlés ; les
combinaisons unités/conversions et fiscales doivent correspondre exactement au
référentiel. Les champs non revus sont refusés. Les fournisseurs renseignés sont
relus avec WS_FOURNIS. Une catégorie exigeant un article-site est bloquée dans ce
parcours de création unitaire : une opération WS_AR_SITE distincte doit être conçue
et autorisée, sans création implicite ni transaction multi-objets simulée.
Les règles conditionnelles supplémentaires doivent figurer dans required_fields
et les combinaisons revues. Ce référentiel ne remplace pas les validations serveur.

## Lecture Python et passage à AIAGT

Exécuter depuis la racine :
`backend\.venv\Scripts\python.exe scripts\verify_python_article_read.py`.
Le script n'expose aucune méthode d'écriture ni aucun mot de passe et écrit
`logs/python-TESTSOAP003-read.json`. Le test effectué s'arrête avant authentification
avec `sage_crl_bundle_missing`. Il faut aligner les fichiers publics de confiance
et de révocation du connecteur avec la configuration réellement validée en
PowerShell ; aucun diagnostic TLS serveur ni installation n'a été relancé.

Pour AIAGT : vérifier l'identité Syracuse, l'accès V12/TEST, le rattachement effectif
du pool, GESITM consultation/création et la publication WS_ARTICLE. Restreindre sites
et fonctions ; aucun droit facture/stock/comptabilité. Évaluer WS_FOURNIS en lecture
et GESITF/WS_AR_SITE uniquement si nécessaires au périmètre approuvé. Utiliser le
stockage DPAPI existant (`sage_soap_credential_file`), sans secret dans les rapports.
La politique doit prouver les identités HTTP et X3, droits et règles, publication
courante et expiration. Le compte admin reste refusé pour les écritures publiques.

Aucun SAVE Python n'est autorisé par cette mission. La recette finale nécessitera
une autorisation spécifique pour un code unique, puis SAVE unique, READ et SELECT.

## Résultats obtenus

Suite ciblée avec PostgreSQL local isolé et passerelle SOAP simulée : **71 tests
réussis, 3 ignorés** (fixtures PKI de laboratoire), une alerte de dépréciation du
TestClient existant. Rapport : `logs/python-soap-integration-tests.xml`.
La suite vérifie notamment les routes HTTP 423, le parcours préparation/approbation,
le jeton consommé, les doublons, la relecture après résultat incertain, les champs
et règles métier et le refus des écritures par le dispatcher générique.
Ces succès sont des tests automatisés ; aucun d'eux ne prouve un SAVE réel Sage.
