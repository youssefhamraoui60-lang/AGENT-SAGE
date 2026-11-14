# Création PEINTURE par PowerShell — bloquée avant SAVE

1er novembre 2026. Demande utilisateur de création reçue. **Aucun SAVE envoyé, aucune fiche Sage modifiée.**

## Contrôles réellement exécutés

- PowerShell 5.1 et `HttpClientHandler`, requête HEAD vers le point SOAP réel, sans identifiant ni mot de passe, redirection interdite, `CheckCertificateRevocationList=true` et validation native Windows conservée.
- Résultat : `STRICT_TLS_VALIDATION_FAILED`, exception d'authentification TLS. Le script retourne le code 2, jamais un succès de validation. Preuve : `reports/powershell-urgent-strict-check.json` ; commande reproductible : `powershell.exe -NoProfile -NonInteractive -File scripts/check_powershell_strict_transport.ps1`.
- Diagnostic natif complémentaire `SslStream`, TLS 1.2, révocation demandée. Le callback de collecte ne peut accepter que `SslPolicyErrors.None` avec chaîne sans erreur ; il ne contourne aucune validation. Résultat : `RemoteCertificateChainErrors`, **`RevocationStatusUnknown`**, `Verified=false`.
- Certificat effectivement présenté : CN=sage, émetteur SAGE-CA-2, SHA256 `275D8597924516ED25B5305FA6FAEB0115140FA9413D8F9C1F540DF95269BB6B`. Preuve : `reports/powershell-urgent-chain-check.json`.
- Relecture SQL SELECT exacte : zéro ligne pour `PEINTURE-ACRYLIQUE-B` dans ITMMASTER et pour ses couples 201/209 dans ITMFACILIT. Les trois SELECT ont réussi. Preuve horodatée : `reports/powershell-urgent-existence.json`.

Ces diagnostics sont un **échec de sécurité constaté**, pas une tentative de création et pas des tests de création réussis.

## Pourquoi ne pas lancer l'ancien script directement

`scripts/SageTestSoap.psm1`, `Connect-SageTestSoap`, charge un identifiant admin et conserve le défaut `CheckCertificateRevocationList=false`. Le commentaire décrit une exception historique TEST. Ce chemin diffère du transport strict demandé ultérieurement par l'utilisateur. Puisque le dossier TEST est utilisé en exploitation, cette exception n'est pas étendue à PEINTURE.

En outre, `scripts/sage_chat_worker.ps1` refuse ce code métier et cette combinaison stock/TVA hors de ses anciens cas ; `scripts/sage_site_worker.ps1` et `SageTestArticleSites.New-SageTestArticleSitePlan` limitent l'enfant à EXT_POUDRE. Renommer l'article ou passer directement sous admin pour éviter ces contrôles ne constitue pas une correction conforme.

L'instruction « créer avec PowerShell » autorise la création demandée ; elle ne révoque pas les consignes explicites de vérification du certificat/révocation et de non-contournement des droits. Aucun manque d'accord général de l'utilisateur n'est présenté comme la cause de l'échec : le blocage est technique et confirmé avant l'authentification.

## Données conservées pour la suite

Code proposé non réservé : PEINTURE-ACRYLIQUE-B ; désignation PEINTURE ACRYLIQUE BLANCHE 20 KG ; NEG ; UN ; TVA demandée 20 % ; non géré en stock ; sites 201 et 209 ; fournisseur non renseigné. Les règles fiscales/comptables et les paramètres définitifs article-site restent soumis aux contrôles déjà documentés. Aucune valeur non validée n'est ajoutée pour accélérer le SAVE.

## Action indispensable et suite

Obtenir la CRL signée et à jour de SAGE-CA-2 et faire vérifier sa signature, sa période et son contenu réel. Configurer ensuite sa prise en charge par le client PowerShell sans désactiver la révocation, avec les validations nécessaires. Demande administrative précise déjà prête : `docs/DEMANDE-ADMIN-PKI-AIAGT-20261030.md`. Aucune clé privée ni aucun mot de passe requis dans les échanges.

Après transport strict validé, utiliser une identité/droits approuvés pour l'exploitation et un parcours PowerShell général article + article-site avec les données exactes validées, empreintes d'approbation, SAVE unique et relecture SOAP/SQL. Une évolution du payload devra être présentée avant écriture ; aucun accord ne couvre des valeurs encore inconnues. Le parent doit exister et être vérifié avant chaque création enfant ; rechercher les enfants avant SAVE pour éviter les doublons.

Le diagnostic n'a modifié ni `.env`, ni les certificats, droits, politiques ou services Sage. Aucun ancien contrôle n'a été retiré. Aucun test massif n'a été relancé : seule la connexion PowerShell stricte et les lectures de présence nécessaires ont été exécutées. L'objectif de création réelle reste ouvert ; aucun travail autonome en arrière-plan n'est annoncé.
