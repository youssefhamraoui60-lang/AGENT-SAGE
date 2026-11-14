# Demande administrative ciblée — révocation SAGE-CA-2 et droits AIAGT

Préparée le 30 octobre 2026. Document à transmettre par le responsable du projet ; aucun message n'a été envoyé automatiquement. Aucun changement du serveur Sage demandé dans cette première étape, aucun redémarrage, aucun SAVE.

## A. Responsable de l'autorité SAGE-CA-2

Le serveur sage:8443 présente actuellement une chaîne directe feuille → racine SAGE-CA-2. L'ancienne CA sagex3 n'est plus l'émettrice du certificat présenté. La racine SAGE-CA-2 est déjà dans les magasins Root CurrentUser et LocalMachine de la VM agent 192.168.9.208 ; aucune nouvelle racine n'a été importée.

- Émetteur : `C=MA, O=SAGEX3-LAB, CN=SAGE-CA-2`.
- SHA-256 DER racine : `1CA60F430ECAFF47EE7E4BFC63C952628D57F2811FCAC137F00D3E2A40366C90`.
- SKI de cette CA, correspondant à l'AKI de la feuille : `4023125D1BCC07E496577B0F5C05E8C3E6E58289`.
- Feuille CN=sage, SAN DNS:sage et DNS:SAGE ; numéro de série `46D725F7BFC19FAE4A228E082B07C1F7`.
- SHA-256 DER feuille : `275D8597924516ED25B5305FA6FAEB0115140FA9413D8F9C1F540DF95269BB6B`.
- Validité feuille : 26 octobre 2026 19:12:26 GMT au 26 octobre 2029 19:22:26 GMT.
- La feuille et la CA ne publient ni CDP ni AIA/OCSP dans les extensions observées.

**Action requise :** fournir une CRL publique complète, courante, réellement signée par SAGE-CA-2, avec thisUpdate/nextUpdate valides et la liste réelle des révocations de cette autorité. Une CRL sans entrée est acceptable uniquement si la CA certifie réellement l'absence de révocations ; l'agent ne fabriquera jamais une fausse CRL vide. Utiliser le processus d'émission et la base de révocations de la CA existante, quel que soit son outil. Ne pas générer une nouvelle CA ni réémettre les certificats pour contourner cette vérification.

Fournir le fichier public PEM ou DER, son empreinte SHA-256, la référence de l'opérateur/validation et le processus de renouvellement. Une URL de publication approuvée est utile pour le renouvellement, mais une livraison contrôlée du fichier signé permet déjà un bundle CRL local sur 208, sans changement du certificat ni redémarrage de Syracuse. Aucun chemin ou nom de serveur CRL n'est inventé par l'agent. La chaîne actuelle ne comporte pas d'intermédiaire : il faut la CRL de l'autorité qui a signé la feuille, SAGE-CA-2, et non une CRL de l'ancienne sagex3 ou des autorités de laboratoire de l'agent.

**Ne transmettre aucune clé privée ni mot de passe.** Garder la clé et la base d'émission de CA dans leur périmètre d'administration. Dépôt public possible dans `C:\AGENT-SAGE-X3\certs\incoming-production\SAGE-CA-2.crl`, sans l'activer directement.

Recette ensuite sur 208 : vérifier l'empreinte, la signature, l'émetteur/AKI, les dates et la non-révocation de la feuille ; constituer un bundle public versionné ; vérifier chaîne, nom, usages et révocation complète avec OpenSSL strict ; connecter le backend sans désactivation de vérification. Les écritures restent désactivées pendant la recette. La vérification hors ligne de chaîne seule a déjà réussi ; avec révocation, OpenSSL refuse actuellement à la profondeur 0, erreur 3 « unable to get certificate CRL ».

## B. Administrateur Sage X3 / Syracuse

Relecture SQL sans modification : TEST.AUTILIS contient AIAGT actif (ENAFLG=2), LOGIN=AIAGT, PRFFCT=ADMIN, PRFMEN=ADMIN et ALLACS=2. Le profil TEST.AFCTFCT ADMIN possède ALLFCT=2, ALLACS=2 et FILTRE='*'. Les entrées AFCTFCY lues pour GESITF portent CMS, notamment sur 201, 202, 209 et 301. Ce n'est pas un profil limité lecture/création sur les seules fonctions et sites de test prévus. Aucune déduction d'accès aux dossiers de production n'est faite sur cette seule lecture TEST.

**Action requise :** faire valider ou préparer un profil technique dédié de privilèges minimaux pour AIAGT, limité au dossier TEST, aux publications et aux sites nécessaires. Ne pas modifier le profil ADMIN partagé. Fournir les exports non sensibles du compte, du profil de fonctions, des autorisations par fonction/site et des rôles/endpoints Syracuse ; préciser les droits C, M et S autorisés/refusés et examiner l'héritage.

Confirmer le pool exact autorisé, actuellement configuré côté agent `POOL_AI_TEST`, et son identité métier. Un nom de login HTTP AIAGT ne prouve pas l'identité USER d'une session SOAP. Après TLS/révocation validés, recette en lecture : getDescription WS_ARTICLE/WS_FOURNIS/WS_AR_SITE avec SOL=V12, FOL=TEST, USER=AIAGT, puis read/query bornés. Aucun changement de pool partagé ni redémarrage inclus dans cette demande.

Le secret AIAGT existe déjà sous DPAPI sur 208 et se déchiffre sous l'identité du backend ; il est désormais sélectionné localement. Cela ne prouve ni sa validité distante ni les droits métier effectifs ; aucun secret n'est joint à ce document.

## C. Responsable sécurité de l'agent

Après les recettes réelles, fournir une politique d'exécution datée, non expirée, limitée à V12/TEST, au pool et à l'URL HTTPS exacts, liée par empreintes aux identités HTTP/X3, aux preuves de rotation et de droits, aux règles métier revues et aux descriptions SOAP obtenues sous AIAGT. Le fichier de politique actif est actuellement absent ; aucun document fictif de validation n'a été créé.

L'activation technique de SAVE restera distincte de l'approbation humaine des données exactes de chaque opération. Ne lever WRITES_DISABLED qu'après les autres contrôles et dans le périmètre autorisé. HTTP 423 ne doit jamais être contourné.

## D. Critères de clôture

CRL courante validée et renouvelable ; chaîne réelle acceptée avec révocation ; identité distante AIAGT confirmée dans TEST ; droits restreints et preuves revues ; préparation métier et code unique vérifiés ; approbation spécifique des données ; SAVE unique ; messages conservés ; relecture SOAP + SQL concordante et activation fournisseur contrôlée. Aucune réussite de création ne sera annoncée avant cette dernière étape.
