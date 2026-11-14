# Articles TEST : module PowerShell autonome

Exécution Windows PowerShell 5.1 sur VM208, sous VM7\youssef. Aucun besoin de
Python, FastAPI, Zeep, bundle CRL Python, installation ou SQL INSERT.
Le module charge le PSCredential admin protégé DPAPI déjà provisionné.
Destination figée : https://sage:8443, POOL_AI_TEST, WS_ARTICLE, V12/TEST.
La description SOAP doit confirmer ce dossier avant chaque lecture publique.

## Lecture seule

```powershell
powershell.exe -NoProfile -File C:\AGENT-SAGE-X3\scripts\read_powershell_soap.ps1 -Code TESTSOAP003
```

Rapport réel : logs/powershell-module-real-read.json. Un échec HTTPS est un échec
réel ; aucun repli HTTP, callback permissif ou retry.
Après approbation explicite de l'utilisateur le 27 octobre 2026, le module conserve
le comportement Windows HttpClient par défaut, sans imposer la révocation. La valeur
effective est rapportée (False dans cet environnement). Certificat, chaîne, dates
et nom du serveur restent validés par Windows. La réussite ne prouve pas l'absence
de révocation. Cette exception TEST ne modifie pas les autres connecteurs.

## Préparation puis création future autorisée

Ne pas exécuter la dernière commande avant l'autorisation spécifique de création.

```powershell
Import-Module C:\AGENT-SAGE-X3\scripts\SageTestSoap.psm1
Connect-SageTestSoap
$plan = New-SageTestArticlePlan -Code TESTAGENT004 -Designation 'ARTICLE TEST CREATION AGENT IA' -Category NEG -Unit UN
$plan | Select-Object Code,Designation,Category,Unit,Digest,ObjectXml,ReviewRequired
# Seulement après autorisation :
Invoke-SageTestArticleCreation -Plan $plan
Disconnect-SageTestSoap
```

Le plan construit PARAM/GRP/FLD, statut actif 1, unités identiques et coefficients 1.
Les champs, tailles et menus sont vérifiés dans la publication réelle. Les règles
conditionnelles, la catégorie et sa fiscalité par défaut doivent être revues par
l'opérateur : la structure publiée seule ne les certifie pas. Aucun fournisseur,
article-site, prix ou mouvement de stock n'est créé implicitement.

L'opérateur voit le XML puis doit saisir exactement la phrase CREER TEST suivie du
code et du digest. Même -Confirm:$false ne supprime pas cette confirmation explicite.
Le module revérifie description et absence après la réponse humaine. Un marqueur
CreateNew atomique par code est conservé dans runtime/powershell-soap-attempts avant
l'unique appel save. Le résultat et les champs relus sont archivés à côté.
Un résultat incertain ne déclenche jamais un nouveau SAVE ; effectuer seulement
Get-SageTestArticle. Ne jamais supprimer le marqueur pour relancer.

L'agent peut importer le module et préparer un plan ; la création attend une vraie
saisie humaine dans une session PowerShell interactive. Aucun endpoint de création
FastAPI n'est activé ou utilisé. L'intégration au chat web n'est pas remplacée
automatiquement par ce module autonome.

Tests hors ligne, sans identifiants ni connexion ERP :
`powershell.exe -NoProfile -File scripts/test_powershell_soap_module.ps1`.

## Création autorisée réellement exécutée

Le 27 octobre 2026, création de TESTAGENT004 : SAVE status=1, READ status=1,
champs demandés comparés avec succès. Une seule tentative de SAVE. Preuve :
logs/TESTAGENT004-authorized-powershell-result.json. Le marqueur permanent se trouve
dans runtime/powershell-soap-attempts/TESTAGENT004.attempt.json.
Le paramètre AuthorizedTestAgent004 matérialise uniquement l'autorisation explicite
reçue pour ce code et ces valeurs exactes ; il ne permet ni un autre article ni un
second SAVE. Aucun nouvel article n'est autorisé par ce précédent.
