# Connexion Sage X3 V12 en lecture seule

Interface locale : http://127.0.0.1:8000/sage/ (depuis la VM AGENT-SAGE-X3).
Utiliser le jeton `APPROVAL_TOKEN` du fichier privé `.env` dans le champ prévu.
Les identifiants SOAP restent côté serveur. Le navigateur ne reçoit ni compte ni mot de passe Sage.
Le jeton reste en mémoire dans l'onglet; recharger la page le supprime.

## Configuration et connexion vérifiée

Le fichier de configuration est `C:\AGENT-SAGE-X3\.env`, à l'intérieur du dossier du projet.
`SAGE_SOAP_USERNAME` et `SAGE_SOAP_PASSWORD` ont été renseignés par l'opérateur, sans publication des valeurs.
Autres variables optionnelles, valeurs par défaut :

```dotenv
SAGE_SOAP_BASE_URL=http://192.168.9.200:8124
SAGE_SOAP_POOL=POOL_AI_TEST
SAGE_SOAP_PUBLICATION=WS_ARTICLE
SAGE_SOAP_LANGUAGE=FRA
SAGE_SOAP_TIMEOUT=20
```

Solution V12 / dossier TEST : association au pool déclarée côté Sage par l'opérateur.
Le connecteur n'administre pas le pool et ne modifie pas son compte ni son association au dossier.
Ne pas remplacer le chemin réseau par localhost:8124, qui désignerait cette VM.
Le port 8080 est joignable mais retourne 404 sur le WSDL; le port 8124 expose le WSDL réel en HTTP 200.
WSDL : `/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl`.
Endpoint : `/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC`.
Le binding est créé explicitement sur l'adresse réseau vérifiée; une éventuelle adresse interne publiée par le WSDL n'est pas suivie.

L'authentification actuelle est HTTP Basic sur l'adresse HTTP fournie : le transport n'est pas chiffré.
Pour un déploiement durable, faire fournir une URL HTTPS valide et un compte technique disposant uniquement
des droits nécessaires à la lecture, puis remplacer les secrets locaux. Aucun certificat ni contrôle TLS n'est désactivé.
La liste blanche du connecteur ne remplace pas les restrictions du compte côté Sage.

## API et limites

Toutes les routes exigent `X-Approval-Token` :

- GET `/api/v1/sage/status` : état de configuration, sans preuve de connexion ni identifiant.
- GET `/api/v1/sage/description` : métadonnées réelles de la publication.
- GET `/api/v1/sage/articles?limit=20` : liste réelle, 1 à 50 lignes maximum.
- GET `/api/v1/sage/articles/CPJ35` : lecture réelle par clé ITMREF, vérifiée dans la description publiée.

La liste correspond à la liste gauche de l'objet publiée par Sage, pas à une extraction exhaustive de la table SQL.
La requête commence à la clé ITMREF vide; une liste pleine est signalée comme potentiellement partielle.
Aucun offset ou total de catalogue n'est inventé. Aucun cache d'articles ni import dans les référentiels de l'étape 2.
La fiche expose des champs article sélectionnés, sans traces techniques ni identifiants d'auteurs de modification.
Toutes les données affichées viennent des réponses SOAP; aucune valeur de démonstration n'est substituée en cas d'échec.

Le module Python `backend/app/services/sage_soap.py` utilise Zeep pour le WSDL et la sérialisation RPC/encoded.
Le Syracuse réel omet le membre messages déclaré obligatoire dans le WSDL : désérialisation explicite
et contrôlée du SOAP de retour (opération attendue, statut 1, resultXml), sans correction de données métier.
Les schémas standards SOAP encoding et XML sont fournis localement dans `backend/app/schemas/soap`.
Tous les autres imports WSDL, destinations SOAP inattendues et redirections sont bloqués.
Les DTD/entités XML sont interdites, réponses limitées à 4 Mo, deux appels simultanés maximum.
Les erreurs SOAP brutes et les en-têtes d'authentification ne sont jamais retournés au navigateur ou journalisés.
Seules getDescription, read et query passent la barrière du transport. Aucune route d'écriture ou invocation générique.

## Démarrage et tests

```powershell
cd C:\AGENT-SAGE-X3
.\scripts\start.ps1
# Après changement de configuration serveur ou reconstruction frontend :
.\scripts\stop.ps1 -BackendOnly
.\scripts\start.ps1 -BackendOnly
```

Compilation React, avec le Node.js déjà installé :

```powershell
$env:PATH="$env:LOCALAPPDATA\AGENT-SAGE-X3-tools\node-v24.20.0-win-x64;$env:PATH"
npm ci --prefix frontend
npm run build --prefix frontend
node frontend\tests\live-browser.mjs
```

Le test navigateur utilise Edge existant en mode headless, lit CPJ35 et affiche 20 articles réels;
captures ordinateur/mobile dans logs, jeton masqué. Le test ne lance aucune écriture Sage.

```powershell
cd backend
$env:RUN_STEP2_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe ..\scripts\test_step3_live.py
```

Les tests unitaires bloquent les opérations d'écriture sans les envoyer à Sage.
Les preuves réelles sont séparées des mocks. Les traces SOAP de diagnostic sont privées dans runtime;
elles peuvent contenir des données métier et ne doivent pas être publiées.
La sauvegarde native existante inclut les sources, les verrous Python/npm et le .env privé;
les logiciels et node_modules sont reconstruits depuis leurs verrous. Conserver les archives sous ACL privée.

Sources techniques :
- https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_soap-generic.html
- https://online-help.sagex3.com/geode/12/en-us/Content/V7DEV/api-guide_soap-web-services.html
- https://schemas.xmlsoap.org/soap/encoding/
- https://www.w3.org/2001/xml.xsd
