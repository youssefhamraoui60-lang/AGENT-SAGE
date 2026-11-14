# Validation unique regroupée — proposition de production

25 octobre 2026. **PROPOSITION NON APPROUVÉE, NON ACTIVÉE.** Elle regroupe les décisions nécessaires pour ne plus demander un accord à chaque commande de préparation. L'approbation future d'un SAVE métier restera distincte.

## Périmètre concret proposé

| Élément | Proposition soumise à validation |
|---|---|
| Autorités distinctes | Nouvelle racine `SOB Sage HTTPS Root CA`, émettrice `SOB Sage HTTPS Issuing CA`, aucun réemploi des clés/certificats TEST ONLY ou sagex3 |
| Racine | Clé chiffrée créée en cérémonie contrôlée sur support chiffré conservé hors ligne ; **support, chemin de garde, responsable et seconde sauvegarde à désigner** avant toute génération ; aucune clé racine permanente dans le projet/VM208 |
| Émettrice | Garde dédiée sur 208 sous **nouveau compte Windows non administrateur `VM7\pki_issuer`**, ACL privées réservées à ce compte/SYSTEM/administrateurs ; compte FastAPI seulement lecteur des fichiers publics. Compte/tâches non créés sans accord Windows inclus dans cette validation |
| Secrets émettrice | Clé PEM chiffrée et récupération DPAPI liée au compte émetteur ; pas de mot de passe en commande, .env ou logs. Provisionnement interactif sécurisé quand requis |
| Validités proposées | Racine 10 ans, émettrice 5 ans, serveur 365 jours au maximum, bornées par l'émetteur ; calendrier de renouvellement et responsables à approuver |
| CSR | **Réutiliser sans nouvelle clé serveur** la CSR `sage-https.req` vérifiée, SHA256 fichier 62BB1D812991FE0CD0DB18E2541633F19F12557FFCC0CAEF2615B93E9C1CC3FC |
| CRL racine | Signée hors ligne ; durée proposée 180 jours, renouvellement anticipé sous responsabilité de garde |
| CRL émettrice | Durée 7 jours, régénération quotidienne sous le compte émetteur ; publication atomique uniquement après vérification signature/date/émetteur et validation de chaîne |
| Publication permanente | Réutiliser **FastAPI existant sur 208:8000**, avec quatre routes publiques exactes ; pas de nouveau serveur/service de publication |
| Supervision | Tâche locale toutes les 15 minutes : disponibilité HTTP, hash public attendu et nextUpdate ; alerte avant 48 h, échec bloquant si objet périmé. Destination d'alerte et responsable à préciser ; aucune tâche installée maintenant |
| Installation Sage | Objet certificat non interne distinct ; affectation seulement à 8443 dans un créneau séparément approuvé, 8124/certificats internes inchangés |

Les responsables/gardes et la destination d'alerte sont des décisions réelles, pas des valeurs que l'agent peut inventer. La création d'une racine privée nécessite une approbation organisationnelle explicite, pas seulement la création technique d'un fichier auto-signé. Si une PKI approuvée existante est désignée à la place, abandonner cette création et utiliser sa procédure de signature avec la même CSR.

## Publication CRL : configuration proposée, pas URLs déjà exploitées

Après approbation seulement, inscrire dans les nouveaux certificats :

- CRL racine : `http://192.168.9.208:8000/pki/root.crl`
- CRL émettrice : `http://192.168.9.208:8000/pki/issuing.crl`
- Certificat racine : `http://192.168.9.208:8000/pki/root.cer`
- Certificat émettrice : `http://192.168.9.208:8000/pki/issuing.cer`

Ces adresses sont **une proposition explicite à approuver et rendre opérationnelle avant émission**, pas une URL de PKI découverte. Le service actuel n'écoute que sur 127.0.0.1 ; les URLs LAN ne fonctionnent pas à ce stade. Aucun certificat n'est émis avec ces URLs avant validation de l'hébergement permanent et de l'accessibilité depuis les clients autorisés.

Le profil prévoit HTTP pour objets publics signés, sans mot de passe ; signatures, hash et fraîcheur sont vérifiés, sans dépendance circulaire à Syracuse HTTPS. Publication active même si Sage est arrêté, mais dépendante de VM208 : sauvegarde, redémarrage automatique et suivi du service FastAPI doivent être inclus dans l'exploitation permanente.

### Préparations déjà réalisées sur 208

- Routeur `backend/app/api/pki_publication.py`, intégré mais **pki_publication_enabled=false par défaut** : allowlist de quatre noms, aucun listing ou chemin libre, aucune clé privée, limite de taille, hash et expiration selon manifeste public contrôlé. Tout objet absent/altéré/périmé est refusé.
- Garde réseau : lorsque publication activée, les clients non loopback n'accèdent qu'aux quatre URLs exactes ; les API métier, /docs, /sage et autres routes restent interdites sur le LAN. Les clients loopback conservent les accès actuels. Le lancement approuvé désactive les proxy headers afin qu'un client LAN ne puisse se faire passer pour loopback par X-Forwarded-For.
- Lanceur **préparé mais non utilisé** `scripts/pki/Start-ApprovedPkiPublication.ps1` : exige un switch d'accord et PKI_PUBLICATION_ENABLED=true, vérifie les écritures désactivées, puis reconfigure le processus FastAPI existant sur 0.0.0.0:8000. Le lancement ordinaire reste 127.0.0.1. Ce changement d'exposition nécessite l'accord inclus ci-dessus et la règle réseau minimale approuvée si un filtrage actif le demande.
- Moniteur `scripts/pki/check_crl_publication.py --manifest CHEMIN_MANIFESTE_PUBLIC` : requêtes publiques sans authentification/redirection, taille bornée, hashes et échéances ; code 0 PASS, 2 WARNING, 1 FAILED. Une sortie doit être raccordée à la destination d'alerte réelle avant exploitation ; pas de supervision prétendue fonctionnelle sans tâche/alerte configurées.
- Préparateur `scripts/pki/build_public_distribution.py` : réutilise le contrôle strict des éléments approuvés, vérifie la correspondance certificat/CSR, produit seulement les quatre objets DER publics et leur manifeste avec hashes/échéances. Requiert explicitement l'URL publique approuvée et une référence de décision ; ne démarre aucun serveur et ne modifie pas la configuration active. Pas d'exécution avant réception des certificats de production.
- Tests : 10 réussis (publication et DPAPI), dont publication désactivée=404, whitelist, refus LAN des routes privées, maintien loopback, refus d'expiration et d'altération. Ce sont des fixtures, aucun certificat de production publié.
- Aucun compte Windows/tâche/règle pare-feu créé, aucune clé ou CA de production générée, aucun port exposé. Le backend local a seulement été redémarré sur loopback avec publication désactivée.

## Manifestes et activation après approbation

Les fichiers DER publiés seront dérivés **uniquement** de la chaîne/CRL approuvées et vérifiées. Le manifeste local public-manifest.json, protégé par ACL, doit déclarer exactement les quatre objets, leurs URLs approuvées, hashes SHA256 et expires_at issus des dates du certificat/CRL ; statut APPROVED_PUBLIC_DISTRIBUTION. Ce manifeste n'accorde pas lui-même la confiance PKI.

Déployer une version atomique validée sous certs/approved-production, accès d'écriture au seul processus de publication/émetteur autorisé ; servir en lecture seule. Ne pas publier le répertoire CA, fichiers DPAPI, index d'émission ou clés. Renouveler avant nextUpdate. Le moniteur signale un échec ; il ne réactive pas un objet périmé et ne change pas la validation TLS. Le connecteur SOAP contrôle déjà CRL_CHECK_CHAIN et refuse CRL manquantes/périmées.

Les paramètres PKI_PUBLICATION_ENABLED et PKI_PUBLICATION_DIRECTORY ne seront ajoutés/activés qu'après accord. Aucun changement du PATH système. Aucun service sur 200 n'est inclus dans l'activation de publication sur 208.

## Interventions groupées sur 200, après réception du certificat signé

La procédure exécutable est **docs/VM200-INSTALLATION-CERTIFICAT-APRES-DECISION-PKI.md**, sections A à D :

1. Recevoir le certificat PEM signé et la chaîne publique, confirmer les empreintes et la correspondance avec la CSR existante ; `certreq -accept -machine .\sage-issued.pem` dans C:\Sage\HTTPS-NEW. Aucune nouvelle clé/CSR.
2. Préparer la clé existante en PEM chiffré via export PFX protégé seulement si nécessaire et approuvé. Outil de conversion approuvé dans le périmètre de 200 ; jamais transférer la clé à 208 ni utiliser -nodes/-noenc.
3. Nouvel objet non interne `sage_https_pki`, hôte sage, CA approuvées et clé correspondante ; aucun remplacement de sage.crt/sage.key/ca.cacrt internes.
4. Dans le créneau autorisé, affecter cet objet uniquement à la ligne 8443 existante. Préserver 8124, authentification client, pool et autres paramètres. Vérifier les accès existants ; retour arrière = ancienne référence 8443 selon la sauvegarde, sans restauration globale improvisée.

## Recette 208 et SAVE unique — étapes conditionnelles

Après installation, contrôler chaîne/nom/révocation et empreinte authentifiée avant tout identifiant. Puis AIAGT/getDescription, read CPJ35, read du candidat **TAI2610255B57B4**, vérification des droits métier ITM et des champs du XML manuel. Les SQL SELECT antérieurs ne remplacent pas ce nouveau contrôle d'inexistence SOAP.

Le XML et le parcours simulé sont déjà préparés ; ne pas les recréer sans changement de mapping. Présenter ensuite le code, les champs, le digest et le dossier TEST pour **une approbation métier distincte**. L'activation temporaire ne doit permettre que cette opération approuvée ; les preuves sont limitées à ITM/create/TEST, les approbations à usage unique. Le verrou global sera refermé en finally après tentative. Résultat ambigu = read seulement, pas de nouvel envoi. Aucun code exécutant une activation automatique n'a été installé par cette préparation.

## Une seule réponse de validation regroupée attendue

Confirmer ou corriger **ce périmètre complet**, puis préciser :

- nom du responsable PKI et référence d'approbation de la nouvelle autorité ;
- support/chemin de garde hors ligne et emplacement de seconde sauvegarde de la racine ;
- accord sur le compte émetteur dédié sur 208, les durées et les tâches de renouvellement/supervision ;
- accord sur les quatre URLs et l'exposition contrôlée du seul contenu PKI sur 208:8000, destinataires/règles réseau nécessaires, destination d'alerte ;
- opérateur et créneau de maintenance de 8443 sur 200 (ce dernier peut rester à fixer, mais aucun changement actif ne sera effectué avant).

Une réponse absente, un paramètre non renseigné ou une simple approbation du test n'autorise ni émission de production ni modification serveur. L'accord SAVE pour TAI2610255B57B4 ne sera demandé qu'après recette HTTPS/droits réussie.
