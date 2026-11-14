# Routage des groupes SOB

Le service utilise la règle approuvée `telegram_group_routing` de PostgreSQL :
`sob commandes` (13 membres lors de la vérification) est le groupe source ;
`COMMANDES SOB` est le groupe des réponses. Les demandes des utilisateurs du
premier groupe sont traitées par les actions existantes dans Sage TEST. Le
service publie ses résultats exclusivement dans le second, avec les identifiants
et un lien vers les messages d’origine. Il n’écoute pas le groupe des réponses.
Les corrections de mémoire restent réservées au compte opérateur.

Démarrage masqué : `powershell -NoProfile -File telegram-test/start-routed-assistant.ps1`.
Le script remplace l’ancien écouteur mono-utilisateur et refuse un second
écouteur routé. La règle est relue au démarrage, sans changer les droits Sage,
les règles métier, ni le moteur articles/fournisseurs. Les logs sont dans
`runtime/telegram-test/assistant-stdout.log` et `assistant-stderr.log`.

Le journal `runtime/sob-telegram-routing.sqlite3` réserve les identifiants des
messages source avant la préparation/création et conserve les réponses. Un lot
réservé n’est pas rejoué automatiquement. Une publication interrompue reste
`delivery_uncertain` ; vérifier le groupe destination avant toute reprise.
Les reçus SQL existants restent obligatoires. Depuis le 14 novembre 2026,
l'agrégation est désactivée : chaque message est traité séparément, sans délai
de regroupement et avec un historique isolé par message. Aucun ancien historique n'est rejoué au démarrage ;
une reprise doit avoir une période explicite et être rapprochée des reçus existants.
Les liens vers le groupe source nécessitent que le lecteur y ait accès.

Les sections historiques ci-dessous décrivent les étapes antérieures ; la règle
de routage et le périmètre TEST décrits ci-dessus ont priorité.

# SOB — étape 1 : test Telegram personnel

## Mémoire d’apprentissage persistante

Les corrections SOB sont maintenant dans la base PostgreSQL existante, tables
`sob_learning_rules`, `sob_learning_events`, `sob_learning_examples` du schéma
métier configuré. Les règles approuvées sont relues à chaque préparation ; les
alias mémorisés sont prioritaires sur les anciennes correspondances de code.
24 règles issues des demandes utilisateur et 52 exemples de l'audit ont été
importés. Les cas ambigus ne deviennent pas automatiquement des règles actives.

Dans la page SOB : ouvrir « Mémoire d’apprentissage des commandes » pour lire
les règles et enregistrer un alias. Sur Telegram :
`corriger article pointe 6 = PF-TP16X20` (ou `remplacer TRS par MANTD`).
Le code est vérifié dans Sage TEST avant activation. Une correction non structurée
est enregistrée comme proposition à préciser, sans provoquer de commande.

Chaque correction possède une révision et un historique. Redémarrer le service
ne l'efface pas ; le seed est idempotent et n'écrase jamais une correction.
Les contrôles clients/sites/taxes/écriture ne sont pas modifiables par une leçon.
Les poids DeepSeek ne sont pas réentraînés : il s'agit d'une mémoire persistante
utilisée dans la compréhension et dans la résolution des références.

## Audit réel des messages du 7 novembre 2026

Voir `TEST/RAPPORT-EVALUATION-COMMANDES-SOB-2026-11-08.md` et le CSV associé.
200 messages exportés du groupe source « sob commandes », dont 73 depuis le
samedi confirmé. 52 cas couvrent ces messages ; 43 ont une référence OB établie.
Après corrections, 29/43 structures concordent. Ce score ne valide pas une
création généralisée : seul FASM.IMO passe actuellement le périmètre de création
du jeu testé. Les dates/prix d'un rejeu ne constituent pas un ordre de création.

`export_audit.py`, `audit-read.ps1` et `evaluate_history.py` ne publient aucun
message et n'exécutent aucune création. Le banc interdit review/confirm et lit
OB uniquement avec des SELECT fixes. Les pièces jointes sont décodées pour le
banc d'essai ; leur intégration complète au bot reste à faire.

Les conditionnements appris dans les exemples OB restent à vérifier avant
création TEST. Les alias clients se résolvent dans les références existantes,
avec départage par commercial ; aucun code client n'est inventé.

Telegram regroupe les messages rapprochés du même groupe, auteur et Contact.
Le traitement commence 30 secondes après le dernier message de ce contact.
Un lot donne un seul appel de préparation/création et une seule réponse courte.
Les contextes de contacts différents sont séparés. Après création réussie,
le contexte est vidé pour éviter de recopier une commande déjà créée.
« Trs = 50 dh » et « 50 trs » donnent MANTD, quantité 1, prix TTC 50.
Les anciens messages ne sont pas rejoués au démarrage.

Périmètre de création étendu à FASM.IMO / C10370 après lecture du profil client
et simulation complète de la commande CPJ45, PF-TP16X20, PF-TP08X20, MANTD.
Adresse, paiement, commercial et mode de facturation proviennent de Sage :
AD / CHQ60 / REP032 / IME=6 pour C10370 au moment du contrôle.
Le mode de facturation est relu pour chaque commande (C01401 également).
Les autres clients restent à contrôler avant extension du périmètre.

Règle de prix prioritaire autorisée par l'utilisateur : prix explicite, sinon
dernier prix historique utilisable du même client/article, sinon 0 TTC.
Le repli à zéro est affiché dans le récapitulatif et ne bloque plus pour prix
manquant. Une erreur de lecture SQL ne doit jamais déclencher le repli à zéro.

Correction prioritaire de l'utilisateur (nouvelle capture Sage) :
« pointe 6 » → PF-TP16X20 ; « pointe 8 » → PF-TP08X20.
Cela remplace les anciennes correspondances des descriptions « pointe 6/8 ».
Les codes PP06 / PP08 explicitement saisis restent leurs propres fiches.

Correspondances confirmées par l'utilisateur et vérifiées dans TEST :
« pointe 6 » / « PP6 » → PP06 ; « pointe 8 » / « PP8 » → PP08.
Lors du contrôle, ces fiches avaient l'unité de vente UN et aucun rattachement
au site 201. La reconnaissance ne modifie ni l'unité ni le rattachement Sage.

Valeurs par défaut : livraison = jour courant en Europe/Paris si non précisée.
Prix TTC absent : reprendre NETPRIATI_0 de la dernière commande du même client
et article, avec même devise client et même unité de vente article. Le prix
explicite est prioritaire. Sans historique utilisable, le prix reste vide ;
il n'est jamais remplacé par zéro et la création attend un prix renseigné.

Règle prioritaire : TRS / TRC / transport sont toujours remplacés par l'article
Sage MANTD à la préparation et à la création. Quantité 1, montant fourni conservé
comme prix TTC. Exemple : « 50 trs » → MANTD, quantité 1, prix TTC 50.
La simulation SQL MANTD a été vérifiée sans INSERT réel.

Messages commerciaux : « Contact » est le commercial principal, la ligne de nom
suivante est le client. Recherches paramétrées LIKE sur les noms, avec espaces,
points et accents normalisés ; le commercial est recherché dans les deux ordres
prénom/nom. Exemple vérifié : Fasm imo → C10370 FASM.IMO ; Rachida Mansali → REP032.
Les correspondances multiples d'articles restent à préciser et ne sont pas choisies
automatiquement. TRS n'a pas été retrouvé par code exact dans TEST lors du contrôle.
Règle confirmée : TRS/trc/transport et MANTD/manutention ont une quantité de 1,
le montant devant le mot est le prix TTC. Aucune manutention n'est ajoutée seule.
Ces règles de compréhension n'élargissent pas le périmètre SQL de création testé.

L'ancienne interface HTML du port 8011 a été supprimée. Ce port sert uniquement
aux API internes relayées par Sage. Utiliser exclusivement
http://127.0.0.1:8000/sage/#/commandes-sob pour l'interface de commandes.
Les indications historiques ci-dessous sur l'interface 8011 sont obsolètes.

## Interface web SOB (avec Telegram conservé)

L'accès principal est maintenant dans l'espace existant :
http://127.0.0.1:8000/sage/#/commandes-sob (menu « Commandes SOB »).
La page reprend les styles et composants de discussion articles/fournisseurs,
ainsi que leur connexion utilisateur et protection CSRF.
Les API de cette page sont sous `/api/v1/chat/sob/` et relaient le service 8011.
Les cookies SOB sont séparés par compte authentifié et aucune clé Sage/DeepSeek
n'est exposée au navigateur. Le service 8011 doit rester lancé avec start-web.ps1.
L'ancienne interface 8011 et Telegram sont conservés. Leurs conversations ne
sont pas automatiquement importées dans la nouvelle page.

### Création après validation

L'interface web propose désormais un récapitulatif SQL contrôlé et un bouton
« Valider et créer dans Sage TEST ». Exécuter une seule fois
`sage-sob-enable-creation.sql` dans SSMS avec un compte administrateur pour ajouter
les quatre droits INSERT et l'UPDATE de la colonne VALEUR_0 du compteur.
Le compte utilisé reste `agent_sage_x3` ; aucun secret ni compte n'est modifié.
Le contrôle des droits est visible dans l'interface et peut être relancé.

La création reprend la requête SQL fournie le 08/11/2026, avec paramètres .NET,
transaction, contrôles et verrouillage du compteur. Son périmètre testé est
TEST / société 20 / site 201 / SON / année 2026 / C01401 / MAD / T20 à 20 %,
articles RAB10, RAB12, RAB16, RAB8, RAB14, RABT6 et CPJ45.
Signature non gérée et statuts initiaux repris de cette requête ; leur validité
pour d'autres clients n'est pas présumée. Fournisseur laissé vide.
Les autres clients/articles restent consultables mais la création est bloquée.
Le prix TTC et la livraison sont explicites, sans calcul de tarif ou délai.

Avant validation, un SELECT/ROLLBACK construit le récapitulatif depuis Sage.
La validation est liée à la conversation et expire au bout de 15 minutes.
Une correction invalide le récapitulatif précédent ; le SQL compare à nouveau
les données à l'intérieur de la transaction avant tout INSERT.
L'utilisateur coche la validation puis clique sur le bouton de création.
Un simple message « oui » dans le chat ne crée jamais une commande.

API : `POST /api/sob/orders/confirm` avec `{"review_id":"..."}` et le cookie
de session qui a préparé le récapitulatif. Le navigateur ne fournit pas de SQL
ni de nouvelles valeurs lors de la confirmation.
Les reçus et instantanés sont conservés dans `runtime/sob-orders.sqlite3`,
déjà exclu de Git. Une référence SOB unique est inscrite sur la commande.
Une confirmation répétée renvoie le même numéro ; après une réponse incertaine,
seule une recherche du reçu est autorisée, sans relance automatique d'écriture.
Les conversations sont en mémoire : un redémarrage impose une nouvelle session,
mais les reçus sur disque restent disponibles pour diagnostic dans Sage.

L'insertion SQL directe conserve les limites de la requête utilisateur : elle
ne reproduit pas tous les traitements métier X3. Vérifier la commande dans Sage
avant livraison ou facturation. Telegram reste en préparation uniquement.

Tests sans écriture Sage :
`backend/.venv/Scripts/python.exe -m pytest telegram-test/test_creation.py -q`.

Les paragraphes ci-dessous décrivent le mode de préparation initial.

Lancer `./telegram-test/start-web.ps1` puis ouvrir http://127.0.0.1:8011.
Serveur autonome sur le port 8011 ; aucun changement du backend existant.
DeepSeek et le compte SQL sont repris de la configuration existante, sans copie
des secrets ni modification de `.env`. Il n'y a aucune nouvelle clé à renseigner.
Les conversations web sont isolées par cookie local, en mémoire pour huit heures
maximum. Un redémarrage les efface. Ce service est réservé à la machine locale.

API : `GET /api/sob/status`, `GET /api/sob/conversation`,
`POST /api/sob/chat` avec `{"message":"..."}`,
`DELETE /api/sob/conversation`. Documentation : `/api/docs`.
Les appels clients doivent conserver le cookie de session entre les requêtes.
La page présente une discussion et permet de recommencer une préparation.
Toutes les réponses indiquent l'absence de création Sage.

## Assistant de préparation DeepSeek

Lancer `./telegram-test/start-assistant.ps1` après avoir arrêté le test avec Ctrl+C.
Il utilise la même session Telegram et le fournisseur IA du backend (clé jamais copiée).
Les appels DeepSeek passent par les contrôles de budget existants.
Choisir le groupe, puis envoyer un **nouveau** message depuis son propre compte.
L'assistant répond dans ce groupe sous le marqueur « 🤖 SOB » ; l'historique ancien
ne déclenche aucune réponse. Les messages des autres membres ne déclenchent rien
dans ce prototype personnel. Les huit derniers tours sont conservés en mémoire,
séparément par auteur, jusqu'à l'arrêt. Rien n'est persisté comme brouillon.

Le module consulte uniquement clients et articles/site dans TEST avec des SELECT
paramétrés. Il utilise le compte SQL existant sans changer sa configuration.
Société 20, site 201 et type SON sont des valeurs fixes demandées par l'utilisateur.
Prix manquant, TVA finale et livraison calculée restent à compléter : aucun tarif,
taux ni délai n'est inventé. Même « valide » ne crée aucune commande.
Les messages sélectionnés sont transmis à DeepSeek pour compréhension.

Les indications ci-dessous décrivent le mode test `start.ps1`, sans réponse.

Interface console indépendante. Aucun import de l’agent, aucun appel Sage,
aucun changement du backend ni de ses dépendances. Aucun envoi de message,
aucun marquage comme lu, aucune création de commande, aucun téléchargement de média.

Depuis PowerShell à la racine du projet :

```powershell
.\telegram-test\start.ps1
```

Le lanceur crée son propre environnement Python et installe Telethon dedans.
Créer une application sur https://my.telegram.org sous « API development tools »
pour obtenir `api_id` et `api_hash`. Les saisir dans le terminal local uniquement,
puis saisir le numéro du compte, le code Telegram et, si demandé, le mot de passe 2FA.
Les secrets masqués ne sont pas enregistrés dans un fichier de configuration.
Les variables TELEGRAM_API_ID et TELEGRAM_API_HASH sont aussi acceptées.

Après « CONNEXION RÉUSSIE », choisir un groupe : les dix derniers messages
s’affichent, puis les nouveaux messages apparaissent en direct jusqu’à Ctrl+C.
Le test de lecture est confirmé lorsque de vrais messages du groupe apparaissent.
Une connexion réussie seule ne prouve pas la lecture des messages.

La session de connexion est conservée dans `runtime/telegram-test/personal.session`
(répertoire déjà exclu de Git). Ce fichier donne accès au compte : le garder privé.
Les messages sont affichés uniquement dans le terminal, sans journal applicatif.
Pour révoquer l’accès, terminer la session correspondante dans les paramètres
Telegram, rubrique Appareils. Ne pas exécuter deux tests simultanément.

Documentation : https://docs.telethon.dev/en/stable/basic/signing-in.html
et https://docs.telethon.dev/en/stable/modules/client.html


## Reprise autorisée du 11 novembre 2026

La reprise utilise un export figé du groupe source et un plan couvrant chaque
message une seule fois : `runtime/sob-day-20261111/messages-reviewed.json` et
`day-plan-reviewed.json`. La règle PostgreSQL `telegram_replay_2026-11-11`
conserve la date, les groupes, la cible TEST et le dernier message autorisé.
Le service en direct continue de traiter les nouveaux messages.

Le lanceur `telegram-test/replay_day.py --date 2026-11-11` partage le journal des
messages avec le service en direct et appelle les actions SOB existantes. Il
vérifie les reçus par identifiants source et signale les copies exactes de
commandes déjà créées le même jour dans l’autre groupe. Les écritures en cours
ou incertaines ne sont pas rejouées. Une reprise datée conserve les tentatives
précédentes ; elle n’efface pas le journal ni les reçus. Les annulations,
rattachements de messages et valeurs ambiguës restent à vérifier.

Chaque résultat est enregistré avant publication dans `replay-results.json`,
puis envoyé uniquement dans COMMANDES SOB avec ses liens source. Le bilan se
trouve dans `replay-summary.json`. L’état d’envoi évite un nouvel envoi à chaque
relance ; un envoi interrompu doit être contrôlé avant une reprise manuelle.
Les transcriptions visuelles conservent l’empreinte du document source ; elles
ne deviennent pas des règles générales d’alias, de prix ou de conversion.
