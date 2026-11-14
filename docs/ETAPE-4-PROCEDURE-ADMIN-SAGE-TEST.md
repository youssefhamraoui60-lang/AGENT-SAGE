# Déblocage des quatre créations réelles — procédure administrateur

Contrôles du 21 octobre 2026. **Proposition non appliquée.** Ne pas exécuter de création métier pendant le paramétrage. Les chemins de menus varient selon le profil ; utiliser la recherche par intitulé ou le code fonction indiqué. Ne pas créer dans OB, TEST1 ou un autre dossier.

## 1. Ce qui existe réellement

- Administration Syracuse accessible par GET : utilisateurs, groupes, pools, hôtes et certificats. Pas de session administrateur Windows sur Sage.
- POOL_AI_TEST : V12 / TEST, dataset V12_TEST, initialisation 1, maximum 1, canaux démarrés sur deux processus. getDescription retourne encore une identité administrateur.
- Syracuse sage 12.23.3.6-0 : connexion active 8124, SSL=false. Aucun HTTPS vérifié sur 443 ou 8443 depuis l’agent.
- Certificat public sage : SAN DNS sage ; validité 26/02/2026–24/02/2036 ; SHA256 `8ea053b47994c560e9c094fa79635fe3a7238144148f43c9c998bd8986d03ed9`. Autorité sagex3 : SHA256 `d2ca116411f5a3e6cf09aa661330cbb45e92b99b40bdefb9e1d316e76a080f4f`. Fichiers publics relus via HTTP : empreintes à confirmer hors bande avant confiance. Aucune clé privée consultée, aucune CA installée.
- Dans les 50 utilisateurs renvoyés par la requête : admin actif, test actif, import inactif. Ce relevé n’est pas garanti exhaustif. Les recherches exactes Syracuse AIAGT, agent_sage_x3 et agent_sage_test retournent HTTP 200 sans résultat. Le compte SQL agent_sage_x3 n’est donc pas un compte Syracuse identifié sous ce nom.
- Aucun service objet BPC trouvé, quel que soit PUBLI, dans la sélection de TEST.AWEBSERVIC filtrée par OBJET=BPC. Le modèle d’import BPC existe ; AOWSIMPORT répond Service web inexistant. Cela n’exclut pas un sous-programme spécifique dont l’objet n’est pas BPC ; aucun canal spécifique client opérationnel n’est établi.

## 2. Compte métier dans TEST — administrateur X3

À appliquer seulement après autorisation des changements de comptes/profils. Noms ci-dessous proposés ; vérifier l’absence avant création et ne pas écraser un profil existant.

1. Se connecter avec l’administrateur ; sélectionner **V12 / TEST**. Vérifier le dossier dans le contexte avant chaque fonction.
2. Ouvrir **Profils fonction — GESAFT**. Créer le profil `AIAGT`, intitulé `Agent IA TEST - creations controlees`. Laisser **Toutes fonctions autorisées** décoché. Ne pas copier les privilèges admin ni autoriser tous les codes d’accès.
3. Ouvrir **Autorisations fonctionnelles — GESAFP** pour le profil AIAGT. Ajouter les fonctions ci-dessous avec accès autorisé. Dans les options, sélectionner les libellés Consultation/Création effectivement disponibles dans cette installation, sans cocher Toutes options. Ne pas inventer une lettre d’option. Ne pas autoriser Modification/Suppression pour cette phase.

| Fonction | Usage | Périmètre |
|---|---|---|
| GESITM | Article : lire/créer | TEST ; codes d’accès/catégorie NEG autorisés après revue |
| GESITF | Article-site : lire/créer | Site 201 seulement |
| GESBPS | Fournisseur : lire/créer | TEST ; catégorie FR après revue |
| GESBPC | Client : lire/créer | TEST ; catégorie CL après revue |

Les maîtres article/tiers ne sont pas tous des données rattachées exclusivement à un site : un filtre 201 ne remplace pas le contrôle du dossier. N’ajouter les fonctions auxiliaires que si un refus identifié les nécessite. Dans GESAFP, valider la mise à jour des autorisations croisées AFCTFCY lors de la sortie, selon le message de la version installée. Ne pas modifier ces tables par SQL.

4. Ouvrir **Utilisateurs — GESAUS** dans TEST. Créer le code `AIAGT` (5 caractères), nom `Agent IA TEST`, actif, profil fonction AIAGT. Profil menu minimal correspondant au rôle retenu, langue française. Conserver les contraintes société/site/codes d’accès applicables ; pas de super-utilisateur.
5. Ne pas créer automatiquement ce code dans les autres dossiers. Exporter ou capturer la fiche de profil, les quatre autorisations/options et la fiche utilisateur, sans secrets.

**Droits réels non encore attestés** : l’accès actuel en admin et CREATE dans un WSDL ne prouvent pas les permissions d’AIAGT. Après paramétrage : connexion sous AIAGT, ouverture des quatre fonctions, contrôle de l’option création sans enregistrer de fiche, puis preuves des autorisations effectives. Un essai de save prétendument à blanc n’est pas autorisé.

## 3. Identité Syracuse et accès exclusivement TEST

1. **Administration → Utilisateurs → Groupes** : créer un groupe dédié `AGENT_TEST` si absent. Seul point de connexion autorisé : **V12 / TEST (V12_TEST)**. Ne pas sélectionner d’autres endpoints.
2. Associer un rôle non administrateur adapté aux usages Web Services. Si un rôle dédié est nécessaire, le créer avec les seules capacités de connexion requises ; aucun droit d’administration des utilisateurs, hôtes, certificats, publications ou pools. Vérifier les droits hérités des autres groupes : un groupe restrictif n’annule pas un autre groupe permissif.
3. **Administration → Utilisateurs → Utilisateurs** : créer le login `AIAGT`, actif, nom de famille `Agent IA TEST`, groupe AGENT_TEST uniquement. Utiliser la politique d’authentification existante compatible avec l’API ; si DB doit être choisi, le faire uniquement au niveau de ce compte et après validation de la politique. Mot de passe long géré localement, non communiqué au chat. Ne pas modifier les paramètres d’authentification globaux.
4. Dans **Connexions aux points de connexion / Endpoints login** : endpoint V12_TEST, **User Login AIAGT**. Vérifier que la fiche utilisateur X3 associée est bien celle créée dans TEST. Ne pas mapper vers ADMIN.
5. Si une première connexion/changement de mot de passe est requis, l’effectuer manuellement avant l’usage non interactif ; ne pas désactiver globalement les protections de mot de passe. Enregistrer les secrets dans le fichier privé du projet, pas dans un export de preuve.

## 4. Pool : éviter de modifier un consommateur existant

**Administration → Services Web → Configuration des pools SOAP classiques** (rechercher l’intitulé si le menu diffère).

Proposition à approuver : créer `POOL_AI_TEST_TECH` plutôt que changer le compte de POOL_AI_TEST utilisé actuellement.

| Champ | Valeur proposée |
|---|---|
| Alias | POOL_AI_TEST_TECH |
| Point de connexion | V12 / TEST |
| Locale | Français (France) |
| Utilisateur d’initialisation | AIAGT, via la sélection de l’utilisateur Syracuse |
| Dimension initialisation | 1 |
| Dimension maximum | 1 |

Faire vérifier les ressources, sessions/licences et le nombre de processus Web Services avant démarrage : les tailles s’appliquent par processus. Aucun Stop all/Start all. Démarrer seulement le nouveau pool après accord. Pas de promesse d’impact nul ; cela consomme de nouvelles sessions. Ne pas redémarrer Syracuse. Le compte effectif de l’appel dépend également du mapping endpoint de l’utilisateur HTTP : vérifier ensuite le USER retourné par getDescription, pas seulement le champ utilisateur du pool.

## 5. Client BPC : voie minimale proposée

Choisir **une** voie après accord ; ne pas publier un service supplémentaire inutilement.

### Voie privilégiée : publication objet BPC

1. Dans TEST, **Services Web — GESAWE**. Rechercher toutes les publications de type Objet avec objet BPC, sans limiter la recherche au nom WS_CLIENT.
2. Si aucune publication réutilisable n’existe, proposer une nouvelle publication `WS_CLIENT_AI` ; type **Objet**, objet **BPC**. Transaction : sélectionner une transaction BPC valide du dossier si l’objet en exige une ; sinon laisser le champ non applicable. Ne pas inventer une transaction.
3. Onglet Mapping : identifier BPCNUM, catégorie BCGCOD, raison sociale, nom court, pays/langue/devise et blocs d’adresses, taxes, paiement/comptabilité exigés par TEST. Conserver les champs nécessaires aux contrôles ; aucune recette de champs cachés copiée d’une autre installation.
4. Faire générer/publier uniquement cette nouvelle publication après accord. Exporter le paramétrage avant/après. Ne pas modifier WS_ARTICLE/WS_AR_SITE/WS_FOURNIS ni une publication partagée.
5. Me fournir le nom public et le contexte TEST. Je pourrai lire getDescription et développer l’adaptateur client FastAPI/React suivant le mapping réel, avec les mêmes approbations. **Cet adaptateur client n’existe pas encore ; une publication seule ne le rend pas exécutable dans l’application.**

### Alternative : import métier existant BPC

Dans **Modèles import/export — GESAOE**, ouvrir BPC et vérifier objet BPC, fonction GESBPC, champs/format, contrôles, création seule. OPTUPD=2 observé : faire examiner le risque de mise à jour ; ne pas altérer le modèle partagé. Dans **Imports — GIMPOBJ**, l’import manuel est un canal applicatif possible pour un utilisateur autorisé, mais ne constitue pas une exécution depuis FastAPI. Ne pas lancer d’import pendant cette préparation.

Pour automatiser, le service standard AOWSIMPORT.IMPORT doit être présent, publié et autorisé : il ne l’est pas dans le contexte testé. Ne pas tenter de le reconstituer au hasard. Sa mise en place et un adaptateur d’import contrôlé nécessiteraient une proposition distincte. Aucun fichier incomplet contenant une adresse ou une taxe inventée ne sera exécuté.

## 6. HTTPS : décision technique indispensable

**Aucun HTTPS déjà utilisable établi.** Ne pas mettre https devant le port 8124 HTTP. Le certificat disponible seul ne fournit pas un listener.

Option sans nouveau logiciel : **Administration → Serveurs → Hôtes → sage → Connexions**. Valeurs candidates après accord technique : port 8443, SSL Oui, certificat sage, nom d’accès `https://sage:8443`. Conserver la connexion 8124. Confirmer préalablement port libre côté serveur, clé privée utilisable, chaîne/empreintes par l’administrateur, SAN sage et chemin réseau restreint à 192.168.9.208 et aux administrateurs autorisés.

**Ne pas enregistrer ces changements maintenant** : la documentation prévient que les modifications de connexions actives/certificats entraînent un redémarrage serveur. Si toute interruption reste interdite, fournir l’URL d’un reverse proxy ou tunnel approuvé déjà disponible, protégeant aussi le segment proxy→Sage. Aucun proxy existant n’a été démontré. Un filtrage Windows ajouté alors que son pare-feu est désactivé ne suffit pas ; utiliser une politique réseau existante approuvée ou différer le changement.

Avant une activation approuvée : export des paramètres hôte/certificat public et état des connexions, fenêtre et plan de restauration validés. Retour arrière par l’administrateur : remettre les seules valeurs modifiées, avec éventuel redémarrage planifié ; aucune suppression de certificat partagé. Si aucune solution sans interruption n’existe dans l’infrastructure actuelle, une fenêtre de maintenance doit être explicitement autorisée.

## 7. Paramètres agent — préparés, non appliqués

```dotenv
SAGE_SOAP_BASE_URL=https://sage:8443
SAGE_SOAP_POOL=POOL_AI_TEST_TECH
SAGE_SOAP_USERNAME=AIAGT
# SAGE_SOAP_PASSWORD : secret technique à saisir localement
SAGE_SOAP_CA_BUNDLE=C:/AGENT-SAGE-X3/runtime/sage-approved-ca.pem
SAGE_SECURITY_POLICY_FILE=C:/AGENT-SAGE-X3/runtime/sage-write-policy.json
SAGE_WRITES_ENABLED=false
```

L’URL ci-dessus est une candidate, pas un endpoint déjà actif. Le bundle doit provenir de la CA confirmée hors bande. Conserver false pendant les lectures de recette. La politique de preuves suit config/sage-write-policy.example.json : expiration, V12/TEST, pool/URL exacts, hashes des identités HTTP/X3, identifiants renouvelés, droits et règles revus pour chaque ressource, conservation des clés manuelles, chemins/hashes des preuves et description réellement obtenue. Ne jamais cocher des attestations sans preuve. L’approbation individuelle ne remplace aucun prérequis.

Après validation : redémarrage local de FastAPI seulement si nécessaire pour recharger .env, TLS vérifié, getDescription/read/query sous AIAGT, accès refusé hors TEST. Puis autorisation technique d’activation des écritures et accords individuels liés à chaque préparation finale. Pas d’activation globale pour effacer 423.

## 8. Impacts, retour arrière et exécution finale

| Changement proposé | Impact | Retour arrière |
|---|---|---|
| Utilisateur/profil/groupe AIAGT | Nouvelle identité et accès TEST | Désactiver le compte dédié, retirer ses seules associations ; conserver les preuves |
| Nouveau pool | Sessions/mémoire/licences supplémentaires | Arrêter uniquement ce pool, rétablir la configuration agent précédente |
| Nouvelle publication BPC | Génération de wrapper/description dans TEST | Dépublier la nouvelle publication après inventaire de ses consommateurs ; garder l’export |
| HTTPS | Listener partagé, redémarrage possible | Restaurer les paramètres sauvegardés dans une fenêtre autorisée |
| Paramètres agent | Connexion et portée des approbations | Écritures false, restaurer les paramètres privés antérieurs sans réintroduire un secret exposé |

Les comptes/connexions/publications ci-dessus ne sont pas encore modifiés. Aucun droit SQL supplémentaire demandé. Aucun essai d’écriture sans sécurité validée.

Ordre final : AITEST001 via ITM ; read + SELECT ; rechercher ITF 201 automatique avant une éventuelle création distincte ; F_AITEST01 via BPS ; C_AITEST01 via BPC ou import autorisé. Une tentative par accord, réponse ambiguë → lecture seulement. Comparaison des valeurs enregistrées, historique PostgreSQL et affichage React après implémentation BPC. Contrôle manuel TEST → GESITM/GESITF/GESBPS/GESBPC.

## Sources officielles et preuves

- [Utilisateurs Syracuse et mapping endpoint](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_users.html).
- [Utilisateur X3 GESAUS](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAUS.htm), [profil GESAFT](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFT.htm), [autorisations GESAFP](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAFP.htm).
- [Pools SOAP](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_soapClassicPool.html), [publication GESAWE](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAWE.htm).
- [Connexions hôte et impact de redémarrage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html), [import standard](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/api-guide_api-soap-import-export.html).
- Preuves locales : logs/step4-remote-readonly-diagnostic.json, logs/sage-available-accounts.json, logs/four-creation-sql-discovery.json et logs/native-creation-methods.json. Aucun secret inclus dans ces relevés.
