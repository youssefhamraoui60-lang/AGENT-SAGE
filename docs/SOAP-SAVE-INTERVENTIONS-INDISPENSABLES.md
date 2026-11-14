# SOAP SAVE : deux interventions externes à autoriser

État contrôlé le 24 octobre 2026 depuis la VM agent. Aucune modification du serveur 200 appliquée.

**Ordre d’intervention demandé le 24/10/2026 :** [1. AIAGT et recette des droits](ADMIN-01-AIAGT-TEST.md), puis [2. Maintenance HTTPS et retour arrière](ADMIN-02-MAINTENANCE-HTTPS-SYRACUSE.md). Ces fiches détaillent les paramètres préparés et les autorisations distinctes nécessaires. Elles ne valent ni modification appliquée ni approbation de save. Les constats ci-dessous ne sont pas rejoués pour cette préparation.

**Autorisation utilisateur reçue ensuite :** les corrections locales et AT-AIAGT sont autorisées sous réserve d’accès administratif approprié. Cet accès Windows n’a pas pu être établi ; aucune configuration AIAGT/pool appliquée. Ne pas redemander l’autorisation générale AIAGT. L’accord de maintenance AT-HTTPS et l’approbation métier d’un save restent distincts et non accordés. Voir [la demande ciblée de maintenance](AT-HTTPS-8443-SAGE.md).

**Exécution désormais prévue en RDP local, sans nouveaux essais distants :** utiliser [RDP-200-EXECUTION-GUIDEE.md](RDP-200-EXECUTION-GUIDEE.md), avec script de consultation et copie de sauvegarde protégée. Les catégories consultation, changements TEST et maintenance HTTPS sont séparées ; les opérations futures ne sont pas présentées comme déjà réalisées.

## 1. Transport natif Syracuse — autorisation technique T1

Constat : WSDL HTTP 200 sur 8124 ; aucune connexion HTTPS joignable sur 443/8443. L’administration Syracuse déclare une seule connexion active, 8124 sans SSL. Aucun proxy ou tunnel existant de bout en bout n’est démontré. Un proxy sur l’agent suivi d’HTTP réseau ne convient pas.

**Solution proposée sans installation :** faire activer HTTPS dans le Syracuse déjà installé. Sur la page d’administration **Hôtes / Hosts**, représentation `host`, ouvrir `sage`, tableau **Connexions / Connections**. Après sauvegarde et autorisation : conserver la ligne 8124 ; ajouter la connexion candidate `8443`, active, SSL activé, certificat serveur `sage` seulement après validation. Ne pas modifier une politique d’authentification client existante. La disponibilité locale de 8443 doit être confirmée par l’administrateur avant cette action.

**Impact :** un redémarrage/rechargement de Syracuse doit être prévu. Les connexions actives et certificats peuvent provoquer ce redémarrage ; ne pas promettre une opération sans interruption. Fenêtre de maintenance obligatoire sur ce serveur partagé. [Documentation officielle Hôtes](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).

**Certificats publics constatés, authenticité encore à confirmer hors bande :**

```text
Serveur : 8EA053B47994C560E9C094FA79635FE3A7238144148F43C9C998BD8986D03ED9
CA      : D2CA116411F5A3E6CF09AA661330CBB45E92B99B40BDEFB9E1D316E76A080F4F
SAN serveur : DNS=sage
Fin de validité : 24/02/2036
URL candidate : https://sage:8443
```

Ne pas utiliser l’IP ou `sage.local` avec ce certificat : ils ne figurent pas dans le SAN constaté. L’administrateur doit confirmer ces empreintes depuis une source locale indépendante, vérifier la chaîne, l’usage TLS, la présence et la correspondance de la clé privée. Fournir uniquement les certificats publics CA/intermédiaires ; aucune clé privée ni mot de passe à transmettre. Le stockage Syracuse est distinct du magasin Windows. [Documentation certificats](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_certificates.html).

**Filtrage :** faire examiner le flux `192.168.9.208 → 192.168.9.200:8443` dans l’infrastructure existante. Une simple règle Windows Allow ne limite rien si le pare-feu est désactivé. Ne pas activer globalement ce pare-feu ni modifier une ACL existante sans étude et autorisation séparées.

**Sauvegarde/retour arrière :** relever/exporter les paramètres de l’hôte, connexions et références de certificats avant intervention ; conserver la configuration Syracuse selon la procédure d’exploitation existante. En cas d’échec, garder les écritures de l’agent désactivées, retirer/rétablir seulement la connexion ajoutée et les changements autorisés dans la même fenêtre ; un nouveau rechargement est possible. Ne pas supprimer les certificats existants ni changer 8124. Ne pas effectuer de compensation métier.

Si aucune interruption n’est acceptable : l’administrateur doit fournir un **proxy, VPN ou tunnel déjà exploité**, avec preuve de protection de tous les segments jusqu’à Sage. Aucun tel chemin n’est actuellement établi. Le garde actuel exige HTTPS ; un autre transport demande une conception et une validation explicites, pas une exception arbitraire.

## 2. Compte technique TEST — autorisation technique T2

Le contrôle exact de l’annuaire Syracuse n’a trouvé aucun utilisateur `AIAGT`. Cela ne constitue pas un inventaire exhaustif des utilisateurs classiques X3 : l’administrateur doit aussi vérifier GESAUS avant création.

1. **Dans TEST, GESAFT — Profils fonctions :** vérifier la disponibilité puis préparer `AITST`, description `Agent IA TEST`. Laisser **Toutes fonctions autorisées** et **Tous codes d’accès** décochés. Ne pas copier les privilèges d’ADMIN. Définir seulement les codes d’accès réellement nécessaires aux données autorisées. [Profils fonctions](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFT.htm).
2. **GESAFP — Autorisations fonctionnelles :** profil `AITST`, fonction `GESITM` : accès consultation et option `C` création uniquement ; aucune modification ou suppression pour ce test. Fonction `GESITF` : mêmes droits, restriction au site **201** après vérification de son appartenance à TEST ; aucune ligne autorisant tous les sites. Ne pas donner globalement toutes les options. En quittant, faire appliquer la mise à jour des autorisations croisées selon la procédure Sage. Ne pas écrire manuellement dans AFCTFCY. [Autorisations fonctionnelles](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFP.htm).
3. **GESAUS — Utilisateurs :** vérifier puis préparer le code `AIAGT` (cinq caractères), actif, intitulé `Agent IA TEST`, profil fonctions `AITST`, connexion Web Services autorisée. Choisir un profil de menus minimal existant adapté à cet usage ; ne pas inventer une valeur locale. Examiner les onglets Rôles/Accès et les codes d’accès, sociétés/sites et paramètres effectifs. [Utilisateurs X3](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAUS.htm).
4. **Administration Syracuse — Utilisateurs/groupes/rôles :** préparer l’identité technique `AIAGT`, sans rôle administrateur, associée au seul endpoint **V12 / TEST**, dataset `V12_TEST`. Vérifier qu’aucun groupe ou rôle hérité ne donne accès à d’autres dossiers/pools. Créer un secret neuf uniquement dans le canal local sécurisé ; ne pas le mettre dans ce document ou dans le chat.
5. **Configuration des pools SOAP classiques :** inventorier les consommateurs de `POOL_AI_TEST`. S’il est exclusivement réservé à l’agent, proposer son affectation à l’identité classique `AIAGT`, endpoint V12/TEST, initialisation 1, maximum 1. Arrêter/recycler ce pool peut interrompre ses appels : autorisation préalable. S’il est partagé, ne pas le modifier ; faire approuver un pool dédié candidat `POOL_AIAGT_TEST`, mêmes restrictions, puis adapter l’alias côté agent après validation. Aucun redémarrage global de Syracuse ne doit être lancé pour cette seule opération sans accord.
6. Vérifier GESAWE : `WS_ARTICLE` → objet ITM et `WS_AR_SITE` → objet ITF, publications TEST. Revoir catégorie NEG, unités, numérotation/clés manuelles et contrôles conditionnels. La présence de `save` dans le WSDL ou de CREATE dans une description ne prouve pas les droits effectifs d’AIAGT.

**Preuves attendues :** exports/captures des profils et restrictions, identité X3 effective du pool, paramètres métier revus et approbation du responsable Sage. Les droits de création ne seront pas revendiqués comme testés tant que ce compte et ces preuves n’existent pas. Une lecture réussie ne suffit pas à établir un droit de création. Aucun save de diagnostic n’est prévu.

**Risques/retour arrière :** éviter un accès hérité trop large et le changement d’un pool partagé. Sauvegarder les affectations avant intervention. Désactiver seulement les nouvelles identités/pool si nécessaire et rétablir les affectations approuvées, sans réintroduire un secret exposé. Aucun compte administrateur modifié automatiquement. Faire traiter la rotation/remplacement des identifiants exposés par leur responsable avant d’attester cette condition.

## Commandes locales de lecture seule sur le serveur 200

Ces commandes ne sont pas exécutées à distance par l’agent ; aucun accès administrateur Windows autorisé n’est disponible dans cette session. Elles ne changent aucun paramètre :

```powershell
hostname
Get-CimInstance Win32_Service | Where-Object Name -EQ 'Sage_Syracuse_-_NODE0' | Select-Object Name,State,StartMode,StartName
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 8124,8443,443 | Select-Object LocalAddress,LocalPort,OwningProcess
Get-NetFirewallProfile -PolicyStore ActiveStore | Select-Object Name,Enabled,DefaultInboundAction
Get-ChildItem Cert:\LocalMachine\My | Select-Object Subject,Issuer,Thumbprint,NotAfter,HasPrivateKey
```

Le script existant `scripts/inspect_sage_tls_host.ps1` a aussi été relu : inventaire uniquement, aucune installation ni modification ; il refuse un hôte dont l’IP locale n’est pas 192.168.9.200. Le magasin Windows vide ne signifie pas que le certificat Syracuse est absent.

Pour les journaux : faire relever localement les événements Syracuse/SOAP aux horaires de test, avec type/code erreur et pool ; masquer Authorization, mots de passe, cookies et clés. Ne pas activer une nouvelle trace en production sans autorisation. L’agent n’a pas consulté les journaux Windows/Syracuse locaux du serveur 200.

## Ce que l’agent pourra faire ensuite

Après les autorisations et changements réellement effectués : contrôler TLS avec chaîne et nom vérifiés, charger le WSDL via HTTPS, vérifier getDescription/read et `USER=AIAGT`, V12/TEST, puis comparer les preuves au mapping courant. Configurer les secrets privés et `SAGE_SOAP_CA_BUNDLE` si nécessaire dans le projet ; aucune installation globale de CA non vérifiée.

Le modèle `config/sage-write-policy.example.json` reste volontairement inactif : ne pas simplement remplacer false par true. Les preuves doivent être réelles, datées, limitées, avec leurs SHA-256 et l’empreinte de publication obtenue sous AIAGT. `SAGE_WRITES_ENABLED` reste false pendant cette recette. Son activation nécessite ensuite l’accord technique ; elle ne remplace pas l’approbation d’une création.

Enfin seulement : préparer un **nouveau code unique**, vérifier absence et données métier, présenter le XML final, demander une approbation spécifique expirante/non réutilisable. Après cet accord : une tentative FastAPI → save, read immédiat, SELECT SQL, affichage React et historique PostgreSQL. Réponse ambiguë : relecture uniquement, aucun retry. Aucun code n’est annoncé créé aujourd’hui.
