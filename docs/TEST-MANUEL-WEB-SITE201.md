# Test manuel depuis /sage/ — site 201 obligatoire

Le chat local est raccordé au module PowerShell SOAP validé. FastAPI orchestre la
session web et les validations humaines ; aucun connecteur SOAP Python n'est utilisé
pour ce parcours. Le flag dédié SAGE_POWERSHELL_CHAT_ENABLED active uniquement ce
parcours. SAGE_WRITES_ENABLED reste false : les routes CRUD générales restent 423.

Règle demandée : site **201 explicitement déclaré**, sinon aucune création.
Le site n'est pas choisi automatiquement. Il s'agit d'une condition pour créer
l'article ; aucune fiche article-site n'est créée automatiquement.

Périmètre de ce test : dossier TEST, codes commençant par TEST (maximum 20 caractères),
catégorie NEG, statut actif, unités UN. Les fournisseurs, champs fiscaux explicites,
comptables et réglages de stock supplémentaires sont refusés dans ce parcours réduit.
Les valeurs par défaut de catégorie sont celles du SAVE PowerShell validé.
La politique HTTPS Windows TEST précédemment approuvée reste celle du module.

## Actions dans le navigateur, sur VM208

1. Ouvrir http://127.0.0.1:8000/sage/ et démarrer une nouvelle conversation.
2. Saisir : « Crée un article, code article TESTAGENT005, désignation ARTICLE TEST
   INTERFACE SITE 201, catégorie NEG, unité UN pour le stock, l'achat et la vente,
   site 201. » Le code n'est pas réservé ; sa disponibilité sera revérifiée.
3. Vérifier le code et tous les champs. Confirmer le brouillon.
4. Cliquer Préparer la création : SELECT SQL et SOAP READ PowerShell, sans SAVE.
   Examiner le XML et les valeurs affichées.
5. Cocher l'autorisation, puis Approuver cette création précise.
6. Cliquer Exécuter la création approuvée seulement pour autoriser réellement SAVE.
7. Lire les statuts SOAP, la relecture et la comparaison SQL affichés.

L'approbation est liée à la session, au contenu, à l'opération et expire après
15 minutes. Le serveur consomme l'approbation et persiste executing avant de
contacter PowerShell. Le module impose aussi un marqueur permanent par code avant
SAVE. Une erreur/expiration/concurrence/absence de site 201 n'autorise aucun envoi.
Après résultat incertain, ne pas retenter : relecture uniquement. Un brouillon
ayant donné lieu à une tentative ne peut plus être modifié.

## Vérifications effectuées sans création

Tests isolés de PostgreSQL avec SOAP simulé : 41 réussis, incluant le blocage
du site absent/différent, les approbations, l'expiration et l'interdiction de retry.
Préparation réelle PowerShell de TESTAGENT005 : doublon absent, XML construit,
SaveSent=false. Aucun SAVE réel envoyé durant l'intégration web.
Preuves : logs/powershell-web-tests.xml et logs/web-powershell-real-prepare.json.

Test réel du navigateur (Edge), modèle local, SQL TEST et SOAP PowerShell : PASS,
code TESTAGENT005, site explicitement déclaré 201, opération prepared. Les clics
d'approbation/exécution étaient bloqués dans le test navigateur pour garantir zéro
SAVE. Preuve : logs/powershell-site201-browser.json ; capture :
logs/powershell-site201-browser.png. Les routes CRUD publiques ont également été
vérifiées en HTTP 423 (logs/web-powershell-runtime.json).
