# Timeout et demandes multi-opérations — 28 octobre 2026

## Résultat vérifié

La demande AHMNDE fournie, en une ligne et avec les retours à la ligne de la conversation, est maintenant traitée en brouillons dépendants. Les champs attendus sont conservés, la catégorie manquante reste inconnue, aucun code fournisseur ou code TVA n'est inventé. Les vérifications sont séparées de l'extraction et une reprise contrôlée conserve les identifiants des brouillons.

La vérification finale comprend **1 423 tests backend réussis**, **17 tests frontend réussis**, **100 conversations simulées réussies / 790 tours**, deux scénarios HTTP avec vraies lectures TEST et un parcours du vrai navigateur avec le vrai backend. Aucun SAVE Sage, aucune création fournisseur/article/article-site et aucun SQL DML Sage dans cette campagne. La mission globale et les vingt créations restent incomplètes.

## Diagnostic : faits établis et limite de l'investigation

Le rejeu initial a pris **64,201 s** et a échoué fonctionnellement, mais **n'a pas reproduit le timeout** signalé. Le fournisseur n'était pas créé comme brouillon et le site 202 était perdu. Sans les métriques de la requête historique, il n'est pas possible d'affirmer quelle durée exacte ou quelle contention a déclenché ce timeout-là.

Causes confirmées dans le code et dans le rejeu :

- La demande ne correspondait à aucune extraction courte et partait vers le schéma générique Qwen : `chat_fast_extract.extract` et `chat_model.extract`. Le premier token arrivait après 45,878 s, dont 13,374 s de chargement observé et 32,482 s d'évaluation du prompt. Ce relevé n'est pas un benchmark garanti à froid.
- Le modèle proposait `site="20"` et `code_fournisseur="AHMNDE"`. Les garde-fous du contrôleur ont rejeté ces références non déclarées comme telles ; ils n'ont pas été contournés. Le résultat final conservait donc un site manquant et aucun fournisseur maître. Voir le delta et l'état du cycle initial.
- Le schéma `PartnerPatch` ne contenait pas forme juridique, capital, année de création, RC, ville RC et ICE. Ces informations ne pouvaient pas être conservées dans un fournisseur validé par ce schéma.
- Le détecteur de création de tiers ne reconnaissait pas les formes `veuxc réer`, `founiseur`, `forniseur` et la coordination « et le fournisseur ». Le détecteur de site ne reconnaissait pas le libellé intercalé avant 202.
- Les informations extraites n'étaient persistées en état conversationnel qu'après les vérifications. Un échec intermédiaire pouvait garder le delta dans une trace d'erreur, sans conserver les nouveaux brouillons comme état reprenable.
- Le client HTTP Ollama utilisait un délai de 180 s par opération réseau ; un flux continu pouvait dépasser ce temps au total. Le frontend utilisait `fetch` sans `AbortController` ni délai applicatif explicite. Aucune preuve ne désigne un timeout frontend comme cause historique.

Deux autres anomalies ont été découvertes et corrigées pendant les retests : `uniter` pouvait être tronqué en unité `R` par un motif trop permissif ; avec un fournisseur en mémoire, `site 201` pouvait modifier le site du fournisseur plutôt que celui de l'article.

## Mesures avant/après

| Mesure | Rejeu initial, SQL simulé | Après, demande exacte par HTTP local et vrai SQL TEST |
| --- | ---: | ---: |
| Acceptation HTTP du travail | Ancien appel synchrone/streaming | 268,993 ms, HTTP 202 |
| Temps du service de conversation | 64 200,619 ms | 884,279 ms |
| Appels d'extraction Ollama | 1 | 0, extraction contrôlée |
| Temps HTTP Ollama | 64 029,046 ms | Non appelé |
| Premier token Ollama | 45 878,459 ms | Sans objet |
| Chargement rapporté par Ollama | 13 373,518 ms | Sans objet |
| Évaluation du prompt | 32 481,730 ms | Sans objet |
| Génération | 18 151,370 ms | Sans objet |
| Tokens entrée / sortie rapportés | 1 214 / 98 | 0 / 0, aucun appel d'inférence |
| Extraction métier contrôlée | Non utilisée | 7,282 ms |
| Vérifications SQL, temps mural | Simulées, non comparables à SQL réel | 609,990 ms |
| Somme des temps de requêtes SQL | Non mesurée sur Sage dans ce rejeu | 247,034 ms |
| Ouvertures de connexions SQL | Sans objet | 75,092 ms cumulés |
| Appels API SOAP/REST Sage | 0 | 0 ; les lectures passent par SELECT |

Les temps SQL cumulés et le temps mural diffèrent : deux workers SELECT peuvent travailler en parallèle et les consultations peuvent réutiliser des résultats. Ne pas les additionner au temps total.

Un premier contrôle indépendant avec PostgreSQL isolé et les vraies requêtes TEST a mesuré 1 259,898 ms de service, dont 831,266 ms SQL, 14 appels planifiés et 12 lectures fraîches. Le scénario HTTP **1 fournisseur + 20 articles** a ensuite pris **349,978 ms** de service, avec cache déjà alimenté, 44 lectures fraîches et acceptation HTTP en 259,807 ms. Ce résultat ne prédit pas le temps d'un lot quelconque à froid.

L'amélioration mesurée vient surtout du retrait de l'appel générique au modèle pour des faits explicitement étiquetés. Ce n'est pas une preuve d'accélération universelle de Qwen ni une augmentation du délai. Les textes non reconnus continuent à utiliser l'extraction IA structurée.

Preuves : [mesure initiale](reports/timeout-multi-before.json), [delta initial](conversations/20261028T103706Z/ahmnde-before.json), [premier rejeu réussi](reports/timeout-multi-after-cycle02.json), [lecture réelle isolée](reports/timeout-multi-live-readonly.json), [HTTP réel](reports/timeout-multi-http-live.json).

## Informations extraites et état métier

| Fournisseur | Valeur conservée |
| --- | --- |
| Nom | AHMNDE |
| Forme juridique | SARL AU |
| Capital | 100 000 DH, sans conversion de devise déduite |
| Année de création | 2018 ; l'âge indiqué entre parenthèses n'est pas stocké comme année |
| RC / ville RC | 129251 / Rabat |
| ICE | `002033808000048`, chaîne de 15 chiffres conservant les zéros |

| Article | Valeur conservée |
| --- | --- |
| Désignation | Africa EV Mobility Expo |
| Unité / TVA demandée | UN / 10 % |
| Gestion de stock | Non géré, valeur déclarative `1` |
| Site | 202 ; lecture TEST : « Frais généraux », société 20 |
| Fournisseur demandé | AHMNDE, dépendance vers son brouillon |
| Catégorie / code fournisseur / code TVA | Inconnus, non inventés |

La recherche réelle par nom n'a retourné aucun fournisseur AHMNDE : un brouillon de création est conservé, **pas une fiche Sage créée ou prête à écrire**. Un fournisseur existant ou proche déclenche une sélection préalable et bloque la création d'un doublon. Une recherche indisponible reste « non vérifiée », jamais « fournisseur absent ».

Le plan contient recherche/résolution fournisseur, article à compléter, puis rattachement fournisseur–article bloqué tant que le code fournisseur et le mapping ne sont pas vérifiés. Le contrôle de l'article consulte les codes et articles proches. La catégorie est demandée ; la TVA reste un taux demandé et ne devient pas un code taxe.

La description locale WS_FOURNIS ne certifie ni les champs métier obligatoires, ni le mapping des nouveaux attributs juridiques. `required_fields_verified`, `creation_ready` et la validation de publication restent faux. Il faudra vérifier ces règles avant toute future préparation d'écriture. Les fiches article-site restent un processus séparé, dans leur périmètre existant.

## Architecture de traitement et reprise

1. Le POST authentifié `analysis-jobs` enregistre la demande originale dans `chat_messages`, réserve la révision et un identifiant de travail dans PostgreSQL, puis répond HTTP 202. Le propriétaire et le CSRF restent contrôlés.
2. Le worker asynchrone appelle l'extracteur littéral contrôlé ou Qwen. Les résultats passent par les modèles Pydantic `Delta`, `Patch` et `PartnerPatch`. La limite des brouillons articles et de leurs cibles passe à 20 ; les limites des connecteurs d'écriture restent inchangées.
3. Le delta validé et les brouillons fusionnés sont enregistrés dans un **checkpoint avant les appels SQL**.
4. Les outils exécutent uniquement leurs SELECT TEST prédéfinis et paramétrés. Les résultats alimentent les validations, les dépendances et le récapitulatif. Les données déclarées ne sont pas remplacées par les restrictions du parcours de création.
5. Le frontend suit le statut par GET, affiche l'étape et propose « Reprendre l'analyse » après échec ou interruption. La fermeture du navigateur ne supprime pas le travail déjà lancé.
6. Une reprise après extraction recharge le checkpoint sans réextraire ni refusionner les entités. Une reprise avant extraction réutilise le message original. Un nouveau jeton d'essai invalide les résultats d'une ancienne tentative devenue obsolète.
7. Répéter un même `request_id` avec les mêmes données retourne le même travail ; réutiliser cet identifiant avec un autre contenu est refusé. Un travail en cours et un travail terminé ne sont pas relancés par « resume ».

Le worker réside **dans le processus FastAPI**, avec tâches suivies en mémoire et état durable dans PostgreSQL. Ce n'est pas un broker externe : après arrêt du processus, une reprise authentifiée explicite est nécessaire. L'état de reprise est testé après interruption, travail resté en file et indisponibilité de PostgreSQL pendant le nettoyage d'une erreur.

Les anciens endpoints de messages/streaming restent disponibles. Le parcours séparé de rattachement d'EXT_POUDRE est conservé et testé ; aucune extension de son connecteur n'a été appliquée.

## Délais et instrumentation

| Niveau | Comportement actuel |
| --- | --- |
| Budget total extraction IA | 180 s configurées, désormais appliquées aussi au total de l'attente et de l'inférence |
| File IA locale | 15 s au maximum, dans le budget total ; une seule inférence à la fois par boucle du processus |
| HTTP Ollama | Connexion et pool 5 s maximum ; envoi 10 s ; lecture bornée par le budget configuré, le budget total restant prioritaire |
| SQL Server | Connexion 5 s, requête 3 s, attente du worker 75 s, paramètres existants inchangés |
| PostgreSQL | Connexion 5 s, inchangée |
| SOAP Sage | Délai configuré 20 s, non utilisé dans ces scénarios |
| Frontend | Pas de délai global arbitraire sur l'analyse ; acceptation courte puis suivi du travail, et récupération après rechargement |

Les erreurs distinguent modèle occupé, connexion Ollama, flux interrompu, budget total, extraction et vérification. Les métriques contiennent appels IA, route d'extraction, temps PostgreSQL, SQL et service, ainsi que chargement/tokens/durées Ollama lorsqu'une réponse finale est disponible. En cas de timeout avant les statistiques finales, le nombre réel de tokens n'est pas inventé : il reste inconnu, avec durée et taille de sortie partielle.

## Fichiers modifiés ou ajoutés

| Fichier / fonction | Rôle |
| --- | --- |
| `backend/app/schemas/conversation_entities.py:5`, `PartnerPatch` | Champs juridiques typés ; ICE sous forme de chaîne |
| `backend/app/services/chat_multi_operations.py:14`, `literal_extract` | Extraction mixte des faits explicitement étiquetés ; `plan:74`, `compose:102` pour les dépendances |
| `backend/app/services/chat_model.py:14`, `ExtractionTimeout` ; `request_stream:19`, `extract:106` | Mesures, classification, budget total, sérialisation des appels IA, JSON structuré et limite 20 |
| `backend/app/services/chat_fast_extract.py`, `extract` | Routage mixte et corrections de rattachement fournisseur, sites et cibles 1–20 |
| `backend/app/services/chat_turns.py`, `analyse` | Site avec libellé, unité « uniter », frontières de mots |
| `backend/app/services/chat_partners.py`, `merge`, `_single_partner_update` | Création explicite, attribution des champs au bon objet et provenance juridique |
| `backend/app/services/chat_semantics.py`, `expected_count`, `targets` | Cardinalités et cibles jusqu'à 20 |
| `backend/app/services/conversation_chat.py:643`, `reserve_analysis` ; `checkpoint_analysis:666`, `send:678`, `merge`, `questions` | Persistance, checkpoint, maintien des faits, reprise, renommage cohérent du fournisseur |
| `backend/app/services/chat_jobs.py`, `submit`, `produce`, `status`, `resume` | Worker, suivi par propriétaire, idempotence et reprise contrôlée |
| `backend/app/api/chat.py:58`, endpoints `analysis-jobs` | HTTP 202 et statut/reprise avec contrôles d'accès existants |
| `backend/app/services/chat_performance.py`, `measured` | Compteur explicite des appels IA |
| `frontend/src/analysisJobs.js`, `followAnalysisJob`, `analysisStatus` | Suivi et messages précis sans réémission implicite |
| `frontend/src/ChatApp.jsx:44`, `updateAnalysis`, `monitorAnalysis`, `resumeAnalysis`, `send` | Soumission asynchrone, reprise et affichage du statut |
| `backend/tests/test_multi_operations.py` | Régressions métier, pannes, sécurité et reprise |
| `frontend/tests/analysisJobs.test.mjs`, tests navigateur multi-opérations | Tests du suivi, des erreurs, de la reprise et des fiches |
| `scripts/diagnose_multi_operations.py`, `evaluate_multi_operations_readonly.py`, `exercise_multi_operations_http.py` | Reproductions et mesures sans route d'écriture Sage |
| `scripts/export_evaluation_evidence.py`, `report_reliability.py` | Consolidation des preuves actuelles ; choix explicite du JUnit source |

Les tests navigateur de fiabilisation et Modern Foam ont été adaptés au nouvel endpoint. Les fichiers de reprise et manifestes ont été actualisés. Aucune installation ni migration de schéma applicatif n'a été nécessaire : le travail et son checkpoint utilisent le JSONB conversationnel existant.

## Tests effectivement exécutés

| Campagne | Résultat / preuve |
| --- | --- |
| Reproduction initiale réelle Ollama | Échec fonctionnel conservé : fournisseur/site perdus ; pas de timeout reproduit |
| Cycles spécifiques | Cycle 01 : 21 réussites, 1 échec de synchronisation du test ; cycle 02 : 25 réussites, 1 défaut réel d'attribution du site ; échecs conservés dans `reports/timeout-multi-cycle-*.xml` |
| Non-régression finale | **1 423 réussites, 3 ignorés, 4 exclus**, [JUnit](nettoyant-full-cycle-01.xml) |
| Campagne 1 000 scénarios distincts | **1 000/1 000**, incluse dans le JUnit final ; export dans `results/contracts-executed.json` |
| Conversations de la mission initiale, relancées | **100/100**, 790 tours, aucun échec ; `conversations/20261028T151457Z/run_manifest.json` |
| Tests frontend | **17/17**, `analysisJobs.test.mjs` et `creation-result.test.mjs` |
| Vite et navigateur simulé ordinateur/mobile | Réussis ; [preuve](reports/timeout-multi-browser.json), captures associées ; panne de vérification puis reprise sans nouvelle soumission |
| HTTP authentifié, vrai backend et SQL TEST | Demande exacte et fournisseur + 20 articles réussis ; idempotence vérifiée : [preuve](reports/timeout-multi-http-live.json) |
| Vrai navigateur, vrai backend et SQL TEST | Champs juridiques, ICE, site, TVA, stock, corrections site/fournisseur et catégorie bloquante vérifiés : [preuve](reports/timeout-multi-live-ui.json), captures `timeout-multi-live-article.png` et `timeout-multi-live-supplier.png` |

Les cas spécifiques couvrent fournisseur existant/absent/indisponible, catégorie manquante, fautes et retours à la ligne, 20 articles avec sites distincts, cible article 20, corrections successives, timeout Ollama, coupure SQL, interruption, reprise avec/sans checkpoint, double demande, réutilisation d'identifiant avec un contenu différent, accès non autorisé et panne PostgreSQL pendant la sauvegarde d'erreur.

Les 100 conversations sont simulées et utilisent des résultats ERP synthétiques. Elles passent désormais par les routes d'extraction contrôlées sans appel d'inférence Qwen : cela ne constitue pas 100 validations du modèle sur du texte libre ni une revue humaine. Le test streaming exclu du cycle complet a été exécuté avec succès dans le cycle ciblé. Les trois tests système exclus restent distincts ; les ignorés/exclus ne sont pas comptés comme réussites.

## Limites et suite

- La requête historique qui a dépassé le délai n'a pas ses métriques complètes : le rejeu mesuré suffit à confirmer la lenteur et les défauts d'extraction, pas à prouver une cause historique unique du timeout.
- Le chemin littéral est volontairement borné. Les formes libres non reconnues utilisent encore Qwen et peuvent atteindre le budget ; elles bénéficient du suivi, des mesures et de la reprise.
- Aucun mapping d'écriture juridique fournisseur ni rattachement fournisseur–article n'est certifié ici. Les règles métier, catégorie, fiscalité, publication et données exactes devront être validées avant toute future écriture.
- Aucun broker externe ni reprise automatique après redémarrage n'est installé. Le fonctionnement vérifié est celui du backend natif à un processus de travail ; une architecture multiprocessus demanderait une coordination durable complémentaire.
- Les restrictions TEST/NEG/UN et EXT_POUDRE restent en place. Le défaut sensible antérieur de comparaison d'une fiche article-site existante reste ouvert ; sa proposition de correction n'a pas été appliquée sans l'autorisation distincte requise.
- Les droits SQL excessifs observés sur quatre tables TEST n'ont pas été utilisés ni modifiés. Les vingt créations restent à zéro et leur manifeste n'est pas approuvé.

Le backend local a été rechargé sur les sources vérifiées. Aucun évaluateur n'est laissé en arrière-plan à la fin de cette phase. Les services backend et Ollama restent des services locaux ; l'état exact de reprise figure dans [REPRISE.md](REPRISE.md).

## Complément Nettoyant

La dernière régression inclut aussi le cas Nettoyant multi-site et les demandes de tableau/création existante. Voir [RAPPORT-NETTOYANT-MULTISITE.md](RAPPORT-NETTOYANT-MULTISITE.md). Les mesures de latence AHMNDE ci-dessus restent celles des exécutions identifiées ; elles ne sont pas remplacées par des estimations.
