# SOAP SAVE — avancement réel du 30 octobre 2026

**Finalisation du connecteur strict incomplète : aucun SAVE réel exécuté dans cette campagne.** Travail effectué sur la VM agent 192.168.9.208. Aucun changement, redémarrage ou écriture métier sur le serveur Sage 192.168.9.200 pendant cette campagne ; aucune modification de fiche OB/TEST. Les analyses fournisseurs déjà terminées n'ont pas été recommencées.

Rectification après comparaison des parcours : TESTAGENT004 et EXT_POUDRE ont bien été créés le 27 octobre via le connecteur PowerShell distinct. Le verrou Python décrit ici ne gouverne pas ce parcours historique, qui n'exige pas la révocation CRL et utilise admin. Cette exception n'est pas étendue aux fournisseurs. Voir `RAPPORT-REGLE-CREATION-ARTICLES-FOURNISSEURS.md` pour les preuves et le nouveau branchement fournisseur strict. Il ne faut pas présenter « écritures génériques désactivées » comme une interdiction commune à tous les connecteurs.

## Résultats concrets

| Point | Observation initiale du jour | Correction / preuve | Statut actuel |
|---|---|---|---|
| Autorité TLS utilisée par l'agent | Ancienne CA sagex3 dans certs/ca.cacrt | Le serveur présente désormais SAGE-CA-2 ; racine identique déjà dans Root Windows machine et utilisateur ; copie publique locale versionnée et sélection du bon bundle | Corrigé côté agent ; aucun import de racine ni modification du certificat serveur |
| Identité sélectionnée par le backend | Secret DPAPI admin sélectionné malgré présence du secret AIAGT | Sélection locale du fichier AIAGT existant et de SAGE_SOAP_DPAPI_USERNAME=AIAGT ; rechargement du backend local uniquement ; endpoint runtime confirme AIAGT et secret chargé | Corrigé localement ; authentification distante pas encore vérifiable faute de révocation |
| Révocation | Fichier configuré certs/approved-production/crls.pem absent | CRL requise exactement identifiée ; TLS réseau strict sur IPv4 192.168.9.200 refuse erreur OpenSSL 3, profondeur 0 | Bloqué : obtenir CRL courante signée SAGE-CA-2 |
| Droits techniques | AIAGT existe mais profil inconnu | SELECT TEST.AUTILIS/AFCTFCT/AFCTFCY : actif, profil ADMIN, toutes fonctions et tous codes d'accès ; droits CMS sur plusieurs sites GESITF | Droits trop larges pour les preuves de privilèges minimaux attendues ; aucun droit changé |
| Diagnostic HTTP 423 | La barrière vérifiait le schéma HTTPS mais pas la présence des objets CA/CRL | Contrôle local explicite ajouté ; diagnostic distingue matériel local et validation du pair ; refus aussi d'un fichier ne contenant que des certificats à la place de CRL | Corrigé, HTTP 423 confirmé sur articles et fournisseurs |
| Politique d'exécution | Chemin de politique actif vide et écritures désactivées | Aucune fausse preuve ou politique d'autorisation créée ; état exact exposé dans le diagnostic protégé | Bloqué, revue administrative nécessaire avant activation |

Preuves du jour : `reports/soap-save-readiness-20261030/`. Les fichiers PEM/DER présents dans ce dossier sont publics et ne contiennent pas de clé privée.

## Certificats et CRL exacte manquante

Le certificat actuel n'est plus celui décrit dans le rapport du 24 octobre. Nouvelle feuille :

- sujet C=MA, O=SAGEX3-LAB, CN=sage ; SAN DNS:sage et DNS:SAGE ;
- émetteur C=MA, O=SAGEX3-LAB, CN=SAGE-CA-2 ;
- série `46D725F7BFC19FAE4A228E082B07C1F7` ;
- empreinte SHA-256 DER `275D8597924516ED25B5305FA6FAEB0115140FA9413D8F9C1F540DF95269BB6B` ;
- validité 26/10/2026 19:12:26 GMT → 26/10/2029 19:22:26 GMT ;
- AKI `4023125D1BCC07E496577B0F5C05E8C3E6E58289`, correspondant au SKI de SAGE-CA-2.

Racine SAGE-CA-2 : SHA-256 DER `1CA60F430ECAFF47EE7E4BFC63C952628D57F2811FCAC137F00D3E2A40366C90`, présente dans les deux magasins Root Windows de 208. La copie cliente provient de LocalMachine Root, pas d'une confiance accordée aveuglément à la chaîne reçue du serveur. Empreinte DER de la copie comparée à celle de la chaîne présentée. Ancienne CA sagex3 conservée intacte.

Chaîne actuelle directe : feuille sage → racine SAGE-CA-2. **Il manque la CRL signée par SAGE-CA-2 pour contrôler la révocation de cette feuille.** Il ne faut ni une CRL de sagex3 ni une CRL issue de la PKI de laboratoire de l'agent. Aucun CDP ou AIA/OCSP n'a été trouvé dans les extensions de la feuille ou de la nouvelle CA. Le cache CRL Windows consulté ne fournit pas de publication SAGE-CA-2.

Les deux causes ont été isolées : avec l'ancien bundle, autorité inconnue ; avec la racine déjà approuvée par Windows, chaîne/nom/usages stricts conformes hors ligne, puis refus erreur 3 « unable to get certificate CRL » dès que la révocation est exigée. Le contrôle de chaîne seule est un diagnostic hors ligne, **pas une connexion autorisée sans révocation**. La connexion réelle utilise toujours strict + CRL_CHECK_CHAIN et est refusée.

L'absence de CDP n'empêche pas un bundle CRL local explicitement administré. Une CRL signée, courante et renouvelable peut être fournie au client sans changer le certificat ni redémarrer Syracuse. Il faut son émission par la CA existante ; une copie de certificat ne permet pas de fabriquer cette preuve. La documentation décrit séparément chaîne, nom et contrôle CRL : [OpenSSL 3.5](https://docs.openssl.org/3.5/man1/openssl-verification-options/).

## Changements locaux exacts

Trois clés de configuration uniquement : SAGE_SOAP_CA_BUNDLE, SAGE_SOAP_CREDENTIAL_FILE et SAGE_SOAP_DPAPI_USERNAME. Aucun mot de passe modifié, aucun contenu secret affiché. Sauvegarde précédente dans le répertoire DPAPI déjà protégé ; empreintes avant/après et liste des clés dans `client-config-change.json`. SAGE_WRITES_ENABLED reste false, SAGE_SOAP_CRL_BUNDLE reste le chemin manquant initial, aucune fausse CRL placée à cet endroit. Le nouveau bundle contient uniquement une copie publique de la racine déjà approuvée par Windows, sous `certs/approved-production/windows-trusted-<horodatage>/ca-chain.pem`, avec manifeste d'origine ; aucune nouvelle décision de confiance organisationnelle n'est prétendue.

Code :

- `backend/app/services/sage_tls.py`, `verified_context` : CRL réellement présente dans le magasin OpenSSL exigée ; un PEM de certificats seul est rejeté. `local_tls_readiness` expose le prérequis local sans prétendre avoir validé le pair.
- `backend/app/services/sage_crud.py`, `security` : ajout du blocage CA_CRL_MATERIAL_REQUIRED et d'un diagnostic TLS local. Les contrôles de politique, droits, identité, approbation ponctuelle et transport strict sont conservés.
- `scripts/audit_soap_save_readiness.py` : capture publique avec refus fatal de validation, aucun identifiant ni SAVE envoyé ; inspection locale DPAPI en booléens ; diagnostic IPv4 explicite.
- `scripts/audit_aiagt_sql_readonly.ps1` : SELECT fixes sur métadonnées, utilisateur AIAGT et profils ; exclusion des colonnes de mots de passe et limitation des droits par site aux fonctions pertinentes.
- `scripts/pki/validate_test_chain.py` et tests TLS : possibilité de créer une nouvelle génération **TEST ONLY** sans écraser les anciennes fixtures expirées ; import du script sans génération implicite ; aucun magasin de confiance changé.

Le backend local a été rechargé, parent PID 4976 / worker observé 12648. Aucun service de production redémarré. Vérifier `logs/backend.pid` et la commande du processus avant toute future intervention.

## AIAGT et droits TEST réellement lus

TEST.AUTILIS : USR/LOGIN AIAGT, ENAFLG=2, PRFFCT=ADMIN, PRFMEN=ADMIN, ALLACS=2. TEST.AFCTFCT : ADMIN, ALLFCT=2, ALLACS=2, FILTRE='*'. TEST.AFCTFCY contient notamment GESITF avec OPT=CMS et sites 201, 202, 209, 301, ainsi qu'une ligne sans site. Aucun profil AITST trouvé dans les sélections effectuées. Aucun compte AIAGT trouvé dans X3.AUTILIS ; cela ne prouve ni l'absence d'un utilisateur Syracuse ni l'impossibilité d'accès à d'autres dossiers.

La sémantique des indicateurs est confirmée par les menus installés et la [documentation Sage des profils de fonctions](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFT.htm) : toutes fonctions et tous codes d'accès sont des privilèges étendus. Un nom de compte dédié ne suffit pas à certifier un profil minimal. Le pool POOL_AI_TEST n'a pas encore été vérifié sous AIAGT par SOAP ; la révocation bloque avant envoi des identifiants.

## Conditions HTTP 423 actuelles

GET local protégé /api/v1/sage/security renvoie ready=false :

1. CA_CRL_MATERIAL_REQUIRED : détail TLS sage_crl_bundle_missing ;
2. VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED : aucun fichier de politique actif, revue datée et liée aux preuves absente ;
3. WRITES_DISABLED : verrou volontaire SAGE_WRITES_ENABLED=false.

Le blocage DEDICATED_TECHNICAL_ACCOUNT_REQUIRED lié à la sélection HTTP admin a disparu après sélection AIAGT. Cela ne certifie pas les droits minimaux : le profil ADMIN reste un blocage administratif à résoudre avant validation de la politique. Avec une politique présente, les droits/règles par ressource/action, l'identité X3, les empreintes de descriptions et de pièces justificatives, le périmètre TEST/pool/URL et la date d'expiration restent également contrôlés.

Deux POST locaux **vides**, sans code métier ni approbation, ont confirmé HTTP 423 sur articles et suppliers, avant toute exécution. Aucune charge utile de création envoyée à Sage. Preuve : `live-http-gate.json`, qui confirme aussi l'identité chargée par le worker, le secret disponible en booléen et writes_enabled=false.

## Tests exécutés, échecs conservés et retests

| Campagne du 30 octobre | Résultat final | Preuve |
|---|---|---|
| Régression backend isolée | 1489 réussites, 3 ignorés, 3 sous-processus exclus | full-regression-final.xml |
| Les 3 tests sous-processus exécutés séparément | 3 réussites | subprocess-local.xml |
| Scénarios métier distincts | 1000/1000, inclus dans le backend | catalogue exporté et contracts-executed.json |
| Conversations simulées persistées | 100/100, 790 tours | conversations/20261030T084554Z ; empreintes backend identiques au code actuel |
| Qwen réels forcés, extraction fournisseur | 3/3 | qwen-current-cycle.json ; environ 39,243 / 27,832 / 20,110 s |
| Frontend | 28 réussites | frontend.xml |
| TLS MemoryBIO réel sur fixtures fraîches | 8 réussites, dont chaîne valide, certificat révoqué et mauvais nom | real-tls-memorybio-final.xml |

Les 100 conversations utilisent des référentiels synthétiques et n'ont pas nécessité d'inférence Qwen sur ces formulations. Elles ne sont ni 100 utilisateurs humains ni une évaluation générale du modèle. Les trois essais Qwen forcés sont distincts et n'effectuent aucune écriture Sage.

Échecs conservés : premier passage général, une fixture d'exception administrateur ne déclarait pas son prérequis TLS ; fixture séparée des tests TLS puis retest complet réussi. Un test négatif vérifie qu'une exception administrateur ne lève jamais le blocage CRL. Les anciens certificats/CRL de laboratoire du 24 octobre ont provoqué deux échecs attendus de fraîcheur pendant les essais intégrés : CRL expirée, code 12. Aucune désactivation de date ou de révocation ; nouvelle génération de laboratoire indépendante, clés chiffrées et passphrases DPAPI, tests rejoués avec succès. Rapport de génération `logs/chain-validation-20261030T120000Z-result.json`. Ces objets TEST ONLY ne sont jamais utilisés pour Sage ni copiés dans le bundle client réel.

## Test métier envisagé — pas encore prêt à approuver

Candidat article TESTSOAP26103001, désignation « TEST AGENT SOAP 20261030 - NON COMMERCIAL », catégorie NEG, unité UN, site 201. Quatre SELECT TEST réussis : code absent, catégorie/unité/site présents. Code non réservé. Aucun taux ou code TVA, fournisseur ou paramètre comptable inventé. Preuve `test-candidate.json`.

Ce candidat n'est pas une fiche complète approuvée : description de publication et identité AIAGT à relire après TLS, règles conditionnelles et numérotation/saisie manuelle à valider, politique à faire approuver. Il ne faut pas lancer une approbation portant sur des paramètres techniques ou métier encore inconnus. L'approbation spécifique de la fiche exacte sera demandée après ces prérequis, puis SAVE unique, conservation des messages, SOAP read et SELECT concordants ; pour un fournisseur, vérification des deux statuts d'activation. Les anciens lots de vingt articles et trois fournisseurs ne reçoivent aucune nouvelle approbation implicite.

## Actions restantes et responsable

La demande administrative prête à transmettre est [DEMANDE-ADMIN-PKI-AIAGT-20261030.md](../../docs/DEMANDE-ADMIN-PKI-AIAGT-20261030.md). Aucun message externe n'a été envoyé.

1. **Responsable CA SAGE-CA-2** : livrer CRL courante réellement signée et processus de renouvellement. L'agent pourra vérifier et charger le fichier public sans changement du serveur Sage.
2. **Administrateur Sage** : valider/restreindre le profil dédié AIAGT dans TEST, sans modifier ADMIN partagé ; fournir les exports non sensibles de droits et l'identité du pool. Aucun élargissement ou changement de permission n'a été effectué par l'agent.
3. **Responsable sécurité / agent** : après recette TLS et SOAP de lecture, constituer une politique limitée et liée aux preuves réelles, sans fabriquer une attestation de droits ; activer uniquement le périmètre de test approuvé.
4. **Agent et utilisateur** : finir la proposition exacte, approbation spécifique, SAVE puis relectures. Aucune création tant que ces étapes sont bloquées.

L'objectif reste une seule interface de conversation préparant les données suffisantes dès le premier message, une confirmation exacte, puis création et relecture réelles. Le verrou de sécurité actuel et les limites du parcours fournisseur ne doivent pas être présentés comme une fonctionnalité de création achevée.
