# API FastAPI et trois parcours SOAP — TEST uniquement

Les routes existent pour ITM/WS_ARTICLE, BPS/WS_FOURNIS et ITF/WS_AR_SITE.
Les écritures sont désactivées par défaut. Les preuves réelles et simulées sont séparées dans logs/ETAPE-4-TESTS-API-CRUD.md.
Les succès d'une simulation ne constituent pas un succès de création ou de modification dans Sage.

## Routes

| Objet | Liste | Lecture | Préparation | Création | Modification |
|---|---|---|---|---|---|
| Articles | GET /api/v1/sage/articles | GET /api/v1/sage/articles/{code} | POST /api/v1/sage/articles/prepare | POST /api/v1/sage/articles | PATCH /api/v1/sage/articles/{code} |
| Fournisseurs | GET /api/v1/sage/suppliers | GET /api/v1/sage/suppliers/{code} | POST /api/v1/sage/suppliers/prepare | POST /api/v1/sage/suppliers | PATCH /api/v1/sage/suppliers/{code} |
| Articles-sites | GET /api/v1/sage/article-sites | GET /api/v1/sage/article-sites/{article}/{site} | POST /api/v1/sage/article-sites/prepare | POST /api/v1/sage/article-sites | PATCH /api/v1/sage/article-sites/{article}/{site} |

Les codes article contenant `/` sont acceptés par les routes de chemin; encoder les segments côté client.
Clés publiées : ITMREF; BPSNUM; ITMREF+STOFCY. Les longueurs, champs, dimensions et menus proviennent des descriptions réelles.
Le champ BPSNAM est Display dans la publication consultée : saisir la raison sociale fournisseur via BPRS_1.BPRNAM, tableau de deux valeurs.

Routes complémentaires, toutes avec X-Approval-Token :

- GET /api/v1/sage/security : verrous locaux;
- GET /api/v1/sage/{resource}/schema : métadonnées et champs modifiables;
- GET /api/v1/sage/{resource}/history : 100 opérations récentes;
- GET /api/v1/sage/operations/{uuid} : préparation et historique;
- POST /api/v1/sage/operations/{uuid}/approve : approbation spécifique;
- POST /api/v1/sage/operations/{uuid}/reconcile : **relecture seule**, jamais un retry.

## Préparer sans écrire

```json
{
  "action": "create",
  "keys": {"BPSNUM": "CODE_FICTIF"},
  "fields": [
    {"group":"BPRS_1","name":"BPRNAM","value":["FOURNISSEUR FICTIF TEST API",""]},
    {"group":"BPRS_1","name":"BPRSHO","value":"TESTAPI"}
  ]
}
```

Ce corps est un exemple de structure, pas un jeu complet de données métier validées.
Pour modifier, action=update et ne transmettre que les changements autorisés; FastAPI lit et conserve l'état avant.
Les clés sont injectées côté serveur dans le XML et ne peuvent pas être modifiées dans fields.
Les groupes Table utilisent une ligne explicite row à partir de 1; les champs dimensionnés utilisent un tableau de taille exacte.
Les DTD/entités, champs inconnus/Display, dimensions incorrectes, données hors format et changements de clé sont refusés.

Modifications volontairement limitées dans cette version :

- ITM : ITM0_1.DES1AXX et ITM1_1.DES2AXX/DES3AXX;
- BPS : BPRS_1.BPRNAM et BPRSHO;
- ITF : ITF1_2.ABCCLS.

Élargir cette liste exige une revue métier et de nouveaux tests, pas un paramètre envoyé par React.
Les réglages stock/coûts ou adresses bancaires ne sont pas librement modifiables par ce parcours.

FastAPI vérifie l'existence dans Sage. Pour ITF, il vérifie aussi l'existence de l'article parent.
Une création déjà existante et une modification d'une fiche absente sont bloquées.
La préparation ne prouve pas toutes les obligations métier et ne réserve pas le code.
Pour une modification, la fiche complète relue est empreintée; son changement avant exécution invalide le contrôle préalable.
Ce contrôle ne constitue pas une transaction atomique avec Sage : une fenêtre de concurrence reste possible entre la dernière lecture et modify.

## Verrou technique, non activé

La configuration réelle demeure inchangée : HTTP et identifiants existants, **SAGE_WRITES_ENABLED=false par défaut**.
Le booléen seul ne permet pas d'écrire. Les conditions cumulatives sont :

1. HTTPS avec vérification TLS normale; nom et chaîne valides. SAGE_SOAP_CA_BUNDLE permet un bundle CA explicitement approuvé, sinon le défaut reste True.
2. Compte HTTP technique dédié, non admin, et identité X3 du pool non admin; empreintes de ces identités liées au dossier d'attestation.
3. Rotation des anciens identifiants exposés et compte technique vérifiés par l'administrateur, sans publier les secrets.
4. Dossier d'attestation local expirant, lié à l'URL exacte, solution V12, dossier TEST, pool et publication.
5. Pour chaque objet ET action : droits et règles revus, exports locaux présents et SHA256 identiques, empreinte actuelle de publication identique.
6. En création, attestation que les clés manuelles demandées sont conservées, sans remplacement par un compteur imprévu.

config/sage-write-policy.example.json est volontairement expiré/inactif. Il ne contient pas de droits valides.
Une attestation n'est pas une découverte automatique des permissions X3 : ses documents doivent être examinés et approuvés par l'administrateur métier.
Le serveur vérifie leur présence, leur intégrité et leur rattachement à l'identité/publication; il ne transforme pas une déclaration non vérifiée en droit Sage.
Les profils X3 réels restent appliqués par Sage au moment de l'appel.
SAGE_SECURITY_POLICY_FILE devra désigner un fichier privé validé; aucune route React ne peut créer ou modifier ce dossier d'attestation.
Les autorisations create et update sont distinctes dans permissions, pour chacun des trois resource.
L'URL HTTPS/CA et la création du compte technique doivent d'abord être approuvées selon ETAPE-4-PROPOSITION-HTTPS.md.
N'activer aucune écoute, confiance globale, règle réseau ou nouveau droit sans présenter et autoriser le changement.

## Approbation individuelle, puis exécution unique

L'approbation est elle-même bloquée si les conditions de sécurité ne sont pas remplies.
Une fois ces conditions validées, l'opérateur doit soumettre :

```json
{"digest":"SHA256_EXACT_DE_L_OPERATION","confirm":true,"actor":"operateur","reason":"Motif spécifique de cette opération"}
```

FastAPI enregistre acteur déclaré, raison, date, ID, digest, expiration à 15 minutes et hash du jeton à usage unique.
Le digest couvre objet/action, clés, valeurs, XML, état avant et description de publication. Les horodatages de génération de getDescription sont exclus du hash.
Le jeton brut n'est retourné qu'à l'approbateur et n'est jamais enregistré dans l'historique. React le garde en mémoire, puis l'efface avant l'essai.
L'identité de l'opérateur reste déclarée derrière le jeton partagé X-Approval-Token; ce dispositif n'est pas un IAM multiutilisateur certifié.
Le corps POST/PATCH d'exécution ne transmet pas de nouvelles valeurs :

```json
{"operation_id":"UUID_APPROUVE","approval_token":"JETON_SPECIFIQUE_A_USAGE_UNIQUE"}
```

Avant réseau, FastAPI recontrôle HTTPS, identité technique, preuves, cible TEST, publication et état du record.
Une transaction PostgreSQL verrouille l'opération et l'approbation, consomme le jeton et marque executing AVANT l'appel SOAP.
Un transport distinct n'autorise que le save ou modify attendu, une seule fois, à destination/pool/publication/XML/clés exacts.
Le transport de lecture originel conserve sa liste blanche getDescription/query/read.
Il n'existe aucune route delete ou d'exécution SOAP arbitraire. Les redirections et imports WSDL non approuvés restent bloqués.

Après la tentative, read est effectué, même en cas d'erreur/timeout de write. Les champs proposés sont comparés aux valeurs relues.
succeeded exige statut SOAP 1, existence et correspondance de tous les champs; un timeout reste ambiguous même si le record est observé ensuite.
Aucun retry automatique. Le jeton consommé ne peut pas être réutilisé, et une opération terminale ne peut pas être approuvée à nouveau.
Un arrêt du processus après consommation peut laisser executing sans preuve de résultat : utiliser uniquement reconcile et une investigation humaine.
La relecture ne prouve pas à elle seule l'auteur d'une modification concurrente et ne convertit pas une réponse ambiguë en succès SOAP.

## Interface

http://127.0.0.1:8000/sage/ : trois onglets, consultation/listes/recherche par clés, champs issus de la publication,
préparation création/modification, avant/après proposé, XML, résultat, historique et relecture sans retry.
Les boutons approbation et exécution restent désactivés aujourd'hui.
Liens directs de consultation : ?resource=articles&code=...; ?resource=suppliers&code=...; ?resource=article-sites&code=...&site=...
Le jeton local doit être renseigné; les secrets Sage ne sont jamais envoyés au navigateur.
L'ancien formulaire article et ses routes de préparation restent disponibles pour compatibilité; ils n'exécutent pas d'écriture.

## PostgreSQL, démarrage et tests

Migration additive 005 : soap_operations, soap_operation_approvals, soap_operation_events (événements protégés contre UPDATE/DELETE).
Les administrateurs de la base conservent leurs pouvoirs; ce journal n'est pas immuable face à un superutilisateur.

```powershell
cd C:\AGENT-SAGE-X3\backend
.\.venv\Scripts\python.exe ..\scripts\crud_admin.py
$env:RUN_STEP2_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests -q
cd ..
npm run build --prefix frontend
.\scripts\stop.ps1 -BackendOnly
.\scripts\start.ps1 -BackendOnly
.\backend\.venv\Scripts\python.exe scripts\test_crud_live.py
node frontend\tests\crud-browser.mjs
```

Les tests réels fournis ne consomment aucune approbation et exigent que les écritures restent bloquées; ils créent seulement des préparations locales.
Le test de cycle complet utilise un gateway SOAP simulé et PostgreSQL isolé : il n'est jamais exécuté contre Sage.
Les exemples examples/crud-api/*-NOT-SENT.xml sont des sérialisations WSDL hors ligne, pas des requêtes envoyées.
Les listes sont limitées à 50 lignes; elles ne prouvent pas l'absence globale d'un code, laquelle est contrôlée par read exact.
La sauvegarde native inclut les tables et sources; les preuves logs se transfèrent séparément.
