# Intervention 1 — AIAGT dans V12/TEST

Préparation du 24/10/2026. **AT-AIAGT autorisée par le message utilisateur du 24/10/2026, sous réserve d’accès administratif approprié ; non appliquée.** L’accès Windows distant reste indisponible : WinRM refuse l’authentification avec la configuration actuelle et DCOM chiffré retourne accès refusé. Aucun TrustedHosts ou paramètre de sécurité modifié. La preuve d’autorisation est conservée séparément dans `config/security-evidence/user-technical-authorization-2026-10-24.json` ; elle ne vaut pas preuve de droits effectifs ou de TLS. Les libellés des menus peuvent varier ; utiliser les codes de fonction ou les représentations indiqués.

Appliquer depuis une console d’administration autorisée du serveur Sage, par exemple le navigateur local sur `http://localhost:8124`, dans **V12 / TEST**. Ne pas transmettre le nouveau mot de passe en HTTP sur le réseau entre 208 et 200. Les essais distants sous AIAGT attendent HTTPS.

## Ordre et valeurs à renseigner

Avant création, vérifier uniquement les collisions des nouveaux identifiants. Si AIAGT, AITST ou les nouveaux groupes/rôles existent déjà, ne pas les écraser ni modifier un objet partagé : faire valider leur périmètre ou proposer un autre identifiant.

### 1. GESAFT — Profils fonctions

| Champ | Valeur prévue |
|---|---|
| Code profil / PRFCOD | AITST |
| Description / INTPRF | Agent IA TEST — consultation et création articles |
| Toutes fonctions autorisées / ALLFCT | Non |
| Tous codes d’accès / ALLACS | Non |
| Codes d’accès | Uniquement ceux effectivement nécessaires aux fiches autorisées, relevés par le responsable X3 ; aucune liste inventée |
| Sites par défaut | 201 seulement lorsque le champ est applicable ; aucune valeur « tous sites » |

Ne pas dupliquer le profil ADMIN. Un code d’accès protégeant une catégorie ou une fiche peut nécessiter une autorisation de consultation/exécution/écriture distincte : la faire examiner sans accorder globalement tous les codes. [Référence GESAFT](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFT.htm).

### 2. GESAFP — Autorisations fonctionnelles

| Profil | Fonction | Accès | Option C | Option M | Option S | Périmètre |
|---|---|---|---|---|---|---|
| AITST | GESITM | Oui : consultation | Oui | Non | Non | Articles du dossier TEST ; ITM est une fiche commune, pas une restriction de site à prétendre acquise |
| AITST | GESITF | Oui : consultation | Oui | Non | Non | Type Site, site 201 uniquement |
| AITST | Autres fonctions | Non accordées par cette intervention | Non | Non | Non | Aucun ajout global de fonctions |

Ne pas cocher « Toutes options ». Ne pas ajouter BPS/BPC, administration ou suppression. Le site 201 est associé à la société 20 dans les contrôles SQL déjà réalisés ; cette information sert au contrôle du périmètre, pas à autoriser tous les sites de cette société. Toute dépendance fonctionnelle supplémentaire doit être nommée et validée avant ajout.

À la sortie de GESAFP, faire appliquer la mise à jour des autorisations croisées demandée par Sage ; aucune modification SQL directe d’AFCTFCY. [Référence GESAFP](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFP.htm).

### 3. GESAUS — Utilisateur métier X3

| Champ | Valeur prévue |
|---|---|
| Code / USR | AIAGT |
| Nom / INTUSR | Agent IA TEST |
| Actif / ENAFLG | Oui |
| Connexion X3 / USRCONNECT | Oui, compte autorisé à se connecter ; aucun privilège administrateur |
| Connexion Web Services / USRCONXTD | Oui |
| Login / LOGIN | AIAGT |
| Profil fonctions | AITST |
| Profil menus | Profil minimal approuvé existant ; valeur locale à relever, pas ADMIN |
| Rôles, accès, paramètres | Aucune délégation administrative ni autorisation globale ; contrôler les droits effectifs et hérités |

Créer/associer cette identité uniquement dans TEST. Ne pas lancer une synchronisation globale des utilisateurs vers d’autres dossiers. Ne pas utiliser « Créer utilisateur X3 » sur plusieurs endpoints : l’identité est préparée explicitement dans GESAUS. [Référence utilisateurs X3](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAUS.htm).

### 4. Syracuse — Utilisateurs, groupes et rôles

Pages d’administration `users/user`, `groups/group`, `roles/role` ; profil de sécurité administratif minimal approuvé.

| Objet/champ | Valeur prévue |
|---|---|
| Utilisateur — Login | AIAGT |
| Actif | Oui |
| Nom obligatoire | Agent IA TEST |
| Méthode d’authentification | Mécanisme existant approuvé et compatible avec le client ; ne pas modifier l’authentification globale ni activer un fallback faible |
| Groupe dédié candidat | G_AI_TEST, après vérification de disponibilité |
| Rôle dédié candidat | R_AI_TEST, sans administration |
| Groupe — Endpoints | Seulement V12 / TEST, dataset V12_TEST |
| Utilisateur — Endpoints login | Endpoint V12 / TEST ; User Login AIAGT |
| Autres groupes/rôles | Aucun héritage donnant accès à un autre dossier, à un autre pool ou à l’administration |

Le groupe porte les accès aux endpoints ; la grille Endpoints login associe l’identité classique. Un simple endpoint par défaut TEST ne restreint pas les autres accès. Ne pas modifier un groupe/rôle partagé. Le nom du profil de sécurité administratif minimal reste à relever dans l’installation ; ses droits doivent exclure gestion des utilisateurs, certificats, hôtes et paramètres système. Aucun mot de passe dans les exports, captures ou le chat. [Référence Syracuse Users](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_users.html).

Dans l’endpoint TEST, examiner aussi la correspondance du rôle R_AI_TEST vers les profils de menus/métiers : aucun renvoi vers ADMIN ou un métier à droits étendus. Si une nouvelle correspondance est nécessaire, faire approuver seulement la ligne dédiée à ce rôle et à TEST, avec le profil de menus minimal retenu et un profil fonctionnel effectif AITST ; ne pas remplacer une correspondance partagée. Relever les codes locaux utilisés dans le procès-verbal, sans les inventer.

### 5. Syracuse — Configuration des pools SOAP classiques

Choisir et faire approuver **une seule** option avant application :

- POOL_AI_TEST, uniquement si l’administrateur confirme son usage exclusif par l’agent ;
- sinon nouveau pool candidat POOL_AIAGT_TEST, sans modifier le pool partagé.

| Champ | Valeur |
|---|---|
| Alias | Celui explicitement approuvé ci-dessus |
| Endpoint | V12 / TEST — V12_TEST |
| User | AIAGT |
| Locale | Français (France), fr-FR ; langue SOAP FRA côté agent |
| Initialization size | 1 |
| Maximum size | 1 |
| Auto start | Conserver le réglage existant si réutilisation ; pour un nouveau pool, Oui proposé, sous réserve d’accord sur les sessions/licences |
| Runtime tags | Conserver les tags TEST validés ; ne pas modifier les runtimes ni choisir un tag inventé |

Start/Update peut recycler des canaux. Avec deux processus Web Services, maximum 1 peut représenter deux sessions classiques : vérifier licences et ressources, sans changer les processus Syracuse. Aucune opération de pool avant autorisation. [Référence pools SOAP](https://online-help.sagex3.com/erp/12/es-es/Content/V7DEV/administration-reference_soapClassicPool.html).

## Recette sans écriture Sage

| Contrôle | Résultat nécessaire / preuve |
|---|---|
| Revue administrateur | Exports GESAUS/GESAFT/GESAFP : AIAGT, AITST, consultation/C sur ITM et ITF, M/S absents, ITF limité à 201 ; droits hérités examinés |
| Session AIAGT isolée | TEST accessible ; fonctions autorisées visibles ; administration et endpoints de production absents/refusés |
| SOAP getDescription | WS_ARTICLE : FOL=TEST, SOL=V12, OBJ=ITM, USER=AIAGT ; WS_AR_SITE : mêmes contexte/identité, OBJ=ITF |
| SOAP read ITM | Lire un article existant de TEST choisi par l’administrateur ; statut/messages cohérents et données attendues |
| SOAP read ITF | Lire une fiche existante TEST/site 201 choisie par l’administrateur ; contexte et données attendus |
| Contrôle négatif ITF | Avec accord de test en lecture, utiliser une fiche connue existante d’un autre site TEST : accès refusé. « Fiche inexistante » seule ne prouve pas une restriction |
| Production | Revue des groupes/endpoints et restrictions : aucun accès accordé. Ne pas essayer un pool administrateur de production ou charger ses fiches pour cette recette |
| Autorisation de création | Option C et publication revues par l’administrateur ; noter **CONFIGURÉE, NON EXERCÉE** jusqu’au save approuvé |

Faire ces lectures localement avant HTTPS, puis depuis la VM agent seulement après la recette TLS. Ne pas déduire un droit de création d’un read réussi ou de la présence de save dans le WSDL. Aucun « save à blanc », modify ou delete.

Faire confirmer par le responsable Sage que les restrictions couvrent aussi l’usage des **autres pools SOAP**, dont l’identité classique peut différer de l’identité HTTP. L’appartenance à un groupe Syracuse ou le nom POOL_AI_TEST ne suffit pas à prouver ce point. Si ce périmètre ne peut pas être établi, la recette reste NON VALIDÉE ; ne pas élargir les droits pour la faire passer. Un éventuel test négatif de métadonnées d’un pool hors TEST doit être autorisé et réalisé par l’administrateur, sans lecture de fiches de production.

Conserver les exports datés sans secrets, le nom de l’opérateur, le périmètre, l’alias retenu et les restrictions. Les preuves seront liées à la description de publication obtenue sous AIAGT ; ne pas certifier une politique avec les anciennes empreintes du compte admin.

## Retour arrière et autorisation

Sauvegarder les affectations avant intervention. Si échec, garder les écritures agent désactivées, désactiver seulement les nouveaux objets dédiés après contrôle de leurs usages ; restaurer l’affectation autorisée du pool si elle a été changée. Ne pas supprimer de donnée métier ni remettre un secret exposé. Aucun redémarrage global de Syracuse inclus dans AT-AIAGT.

**Périmètre technique désormais autorisé :** création/association AIAGT + profil AITST + autorisations ITM/ITF site 201 + objets Syracuse dédiés et pool dédié si nécessaire, sans perturber les consommateurs existants. Aucune autorisation sur un dossier de production et aucun save d’article. L’opérateur administratif et le choix de pool doivent être relevés avant application ; aucune nouvelle autorisation générale AIAGT n’est à redemander. L’activation HTTPS et son impact restent soumis à un accord de maintenance distinct.
