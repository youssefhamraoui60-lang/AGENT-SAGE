# Agent conversationnel Sage X3 — première version locale

Adresse : http://127.0.0.1:8000/sage/ sur la VM agent, ou par le transfert local de port déjà autorisé. Aucune ouverture de port réseau n’a été effectuée.

## Parcours

L’écran principal est uniquement un chat : historique, messages, propositions d’articles, questions et confirmation. Aucun jeton à copier, aucune information SQL/SOAP à saisir. Les anciennes interfaces restent dans les sources pour maintenance ; les connecteurs et routes protégées existants sont conservés.

Cliquer sur l’exemple Modern Foam Boards ou écrire une demande libre. Le même fil accepte plusieurs articles, des informations communes, les réponses courtes « 131. », « F234. », une TVA proposée, une catégorie comptable et des corrections ciblées (« le deuxième article… »). Jusqu’à dix articles par conversation. Les cartes évoluent au fil des messages ; les anciennes valeurs restent dans les messages/audits.

L’agent sépare :
- Déclarations utilisateur : catégorie AR, site 131, fournisseur F234, TVA 20 %, catégorie comptable Marchandises.
- Propositions de l’application : code article non réservé, référence interne provisoire qui ne provient pas du fournisseur.
- Observations SQL datées : existence, candidats proches, données de catégorie, unités, conversions, sites, codes comptables, taux et règles fiscales consultés.
- Règles métier : seules les règles explicitement validées et les traitements Sage peuvent autoriser l’écriture. Un exemple historique ou un taux trouvé n’en tient pas lieu.

Les unités achat/vente non déclarées ne sont pas prétendues confirmées par la seule existence de l’unité de stock. Les valeurs de catégorie et conversions sont consultables ; les différences demandent revue. Une référence fournisseur déclarée n’est pas annoncée officielle sans rapprochement probant.

## Session et périmètre autorisé

Le backend émet une session locale aléatoire, cookie HttpOnly, SameSite=Strict, durée sept jours. Le cookie est Secure sur HTTPS ; l’exploitation actuelle HTTP est limitée à loopback. Son empreinte et un identifiant de périmètre sont conservés dans PostgreSQL. Une protection CSRF et une vérification stricte de l’origine protègent les mutations. Les rôles opérateur/lecteur sont vérifiés côté serveur. La session est retrouvée après rechargement ; les conversations ne sont visibles que dans son périmètre.

Cette première version définit le navigateur local autorisé comme périmètre utilisateur. Elle ne fournit pas une connexion nominative d’entreprise : les clients LAN sont refusés, même si une route réseau vers le backend apparaissait. Pour exposer à plusieurs personnes, prévoir une authentification nominative approuvée (OIDC/annuaire), TLS, attribution des rôles et rattachement durable des propriétaires. Aucun proxy ou compte de production modifié. Une nouvelle session après expiration ne récupère pas automatiquement l’historique d’un autre périmètre.

L’ancien jeton mémorisé dans localStorage est supprimé par la nouvelle interface. Aucune valeur APPROVAL_TOKEN ou identifiant SQL/SOAP n’est intégrée dans le bundle React. Le jeton CSRF en mémoire protège la session ; il n’est pas un identifiant ERP et n’est jamais demandé à l’utilisateur.

## Outils de consultation

Le modèle ne propose ni SQL libre ni commandes système. L’orchestrateur construit un plan à partir d’un registre fermé. Les paramètres transitent en JSON sur stdin vers un lecteur PowerShell/.NET existant ; les SELECT et identifiants TEST sont fixes. Limites TOP, tailles de paramètres et délais s’appliquent. Les recherches fournisseurs utilisent le code, le nom complet et un mot significatif ; les candidats restent à confirmer. Les requêtes ne sélectionnent pas les coordonnées bancaires ni les mots de passe.

Le lecteur conserve le mode SQL TMS à chiffrement non exigé précédemment autorisé. Les droits SQL serveur n’ont pas été modifiés ; les outils sont strictement en lecture et ne constituent pas une réduction des anciens GRANT administratifs. Un compte réellement limité à SELECT reste le modèle de moindre privilège à maintenir côté DBA.

Pour la comptabilité : catégorie article, libellé comptable, code comptable et compte général sont distincts. Pour la fiscalité : taux proposé, code taxe et niveau de taxe article sont distincts. Les taux sont consultés avec date/compagnie lorsque ce contexte est disponible ; la détermination fiscale inclut aussi régime et autres conditions non évaluées automatiquement. Aucune sélection silencieuse d’un code à partir du seul taux 20 %.

## Mémoire, RAG et évolution

Tables PostgreSQL ajoutées par 007-conversation-chat.sql : sessions web, conversations propriétaires, messages utilisateur/assistant/outils et exemples métier. Les corrections remplacent le brouillon courant tout en gardant les messages et snapshots.

Un brouillon relu explicitement et dont les contrôles de base sont satisfaits peut devenir un exemple local du même périmètre. La récupération lexicale classe les exemples similaires via la recherche textuelle PostgreSQL, sans nouveau service vectoriel. Leur provenance est human_reviewed_example_not_rule ; une validation locale n’est pas une création Sage. Les historiques et exemples ne sont jamais partagés avec un autre propriétaire par défaut. Les recherches SQL restent séparées de l’extraction Qwen ; le modèle reçoit uniquement le contexte conversationnel utile et les exemples autorisés, pas les secrets ni un export des données ERP.

Évolution LoRA/QLoRA : conserver messages, corrections et provenance ; obtenir le consentement au périmètre d’utilisation ; anonymiser ; constituer un jeu supervisé humainement validé et un jeu d’évaluation indépendant ; mesurer la qualité comparée au RAG ; vérifier les ressources GPU/mémoire et versions ; autoriser séparément un entraînement et sa publication. Aucun fine-tuning ni installation de librairie d’entraînement effectué automatiquement.

## Création réelle

Confirmer un brouillon ne déclenche pas une écriture. La préparation/approbation/exécution utilise les connecteurs existants. HTTP 423 reste actif sans HTTPS vérifié, compte technique et preuves réelles de droits. Une approbation vise les valeurs exactes d’un article ; une correction significative invalide le permis, son jeton et l’état approuvé en PostgreSQL. Les permis à usage unique restent côté serveur, jamais dans React.

Le parcours article-site, les relations fournisseur et les correspondances fiscales complexes ne sont pas inventés ni envoyés via un mapping approximatif. Ces cas restent bloqués avant save jusqu’à revue du mapping. Si une création article autorisée a lieu : le connecteur effectue SOAP read puis le contrôle SQL compare les valeurs ; aucune relance automatique après réponse ambiguë. Le rattachement ITF exige son propre traitement et sa confirmation.

## Maintenance locale

Après les migrations existantes : backend\.venv\Scripts\python.exe scripts\migrate_chat.py. Reconstruire frontend avec le Node existant, puis redémarrer le backend agent seulement. Inclure les tables chat et l’audit existant dans les sauvegardes privées. La clé serveur de session et les secrets restent dans les emplacements privés ; ne pas les publier. Les tests réels sont décrits dans logs/ETAPE-5-TESTS-AGENT-CONVERSATIONNEL.md.

## Correctifs conversationnels du 24 octobre 2026

« Et pour le site, est-ce qu’il existe ? » et « Vérifie le site 131 » relancent des consultations sans modifier les valeurs déclarées. « Change le site 131 vers 201 » utilise la destination 201 ; « Le site est 131 » est une déclaration. Les questions ne peuvent pas injecter EST comme code site. Un message mixte est traité par clauses : « vérifier la catégorie … pour le fornisseur est F992 » recherche la catégorie sans la remplacer et conserve la déclaration explicite du fournisseur.

« Recherche la catégorie NEGOSE » recherche aussi les intitulés proches de Négoce dans ITMCATEG. Le code NEG est proposé avec son intitulé et son contexte de site ; il attend une confirmation, par exemple « Oui, utilise la catégorie NEG ». La catégorie article n’est pas confondue avec le libellé comptable. Les lignes générales et les déclinaisons par site sont distinguées.

Les références internes sont recalculées si le fournisseur change ; leurs anciennes valeurs sont archivées comme obsolètes et affichées comme telles. Elles restent des propositions internes, pas des références officielles fournisseur. Les comparables affichent une confiance indicative (correspondance d’unité, non probabilité statistique) et restent à confirmer.

Constats réels lors de ce correctif : site 131 non retrouvé dans TEST.FACILITY ; sites retournés 201, 202, 209, 301. F992 existe sous le nom CORYAD, différent de Modern for Foam and Plastic. NEG a l’intitulé Négoce. Les paramètres XPS et le taux T20 sont consultés sans écraser les déclarations ni certifier les règles de création. Une consultation indisponible est distinguée d’une recherche exacte sans résultat.

La conversation affectée par EST a été réparée à partir de ses propres messages, avec audit et nouvelle consultation SQL. Recharger le fil : 131 et F992 sont conservés ; NEG reste une proposition à confirmer. Aucune TVA absente de ce fil historique n’a été inventée. Aucune écriture Sage effectuée, HTTP 423 maintenu.

Preuves détaillées : logs/ETAPE-5-CORRECTIONS-CONVERSATION-SQL.md et logs/ETAPE-5-CORRECTIONS-TRANSCRIPTION.md. Ces preuves distinguent la campagne Qwen avec outils contrôlés, les consultations SQL réelles, le parcours navigateur réel et le test de rendu de captures réelles.
