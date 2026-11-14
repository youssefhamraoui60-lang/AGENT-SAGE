# Demande PEINTURE avec « / » et sites 201 + 209

1er novembre 2026. Correctif appliqué au projet et backend local rechargé. **Aucune création ni modification Sage exécutée.**

## Cause exacte reproduite

La trace réelle se trouve dans `reports/slash-sites-original.json`. Les deux tentatives ont reçu une réponse Qwen après 77,24 s puis 20,33 s. L'erreur enregistrée est **ValueError**, pas un timeout ni une erreur de connexion Ollama.

Le delta contenait une désignation, UN, TVA 20, stock 1, `targets:[1]` et `accounting_category:NEG` ; catégorie article et sites étaient omis. Le format existant ne reconnaissait pas cette déclaration slash avec des libellés et sans fournisseur.

L'expression de reconnaissance d'intention dans `chat_turns.analyse` ne reconnaissait pas « créer ce nouvel article ». La phrase finale « vérifier qu'il n'existe pas déjà » faisait donc classer le message comme vérification mixte. Ses valeurs scalaires étaient retenues, mais ses articles supprimés du delta appliqué. `chat_article_requests.apply` tentait ensuite d'affecter les sites à l'article 1 d'une liste vide : **`invalid_article_target`**, reproduit en rejouant le delta enregistré. Ce sont des causes confirmées, pas des hypothèses sur les délais.

## Corrections

| Fichier / fonction | Modification |
|---|---|
| `backend/app/services/chat_slash_extract.py`, `parse_labelled`, `parse` | Grammaire complète pour la demande « créer ce nouvel article », désignation / unité / catégorie / TVA / sélection de sites / stock. Markdown, salutation et formule finale de proposition/contrôle de code reconnus. Champs inconnus, ambiguïtés ou segments supplémentaires refusés par cette voie courte, sans perte silencieuse. Ancien format avec fournisseur conservé. |
| `backend/app/services/chat_article_requests.py`, `simple_initial` | Utilise cette extraction littérale ; le mécanisme existant `declared_sites`/`apply` conserve la sélection complète des sites. |
| `backend/app/services/chat_turns.py`, `analyse` | Reconnaît les déterminants et qualificatifs « ce/cet/un nouvel article ». Une demande explicite de création reste une déclaration même si elle demande aussi une vérification. Les questions et annulations gardent leurs protections. |
| `backend/app/services/conversation_chat.py`, `grounded` | Accepte l'unité déclarée dans ce format slash strict. Ne confond toujours pas « l'article » avec l'unité L ni « un article » avec UN. |
| `backend/app/services/chat_model.py`, `single_article_schema`, `extract` | Schéma court conforme aux longueurs Pydantic, catégorie séparée de catégorie comptable ; consigne Markdown et premier site pour le champ scalaire, sélection complète conservée par le contrôleur. Aucun délai augmenté. |
| `backend/tests/test_slash_sites_creation.py` | Régression exacte, ancien delta fautif, variantes de sites/Markdown, inconnues rejetées, unité L explicite, corrections, maintien des questions en lecture seule et absence d'appel Qwen sur le parcours court. |

La demande normale passe désormais par l'extraction littérale, sans appel Qwen. Les données ne sont pas déduites d'exemples historiques : NEG, UN, 20 %, stock non géré et les deux sites proviennent du message. Le fournisseur non indiqué reste non renseigné. Le code est une proposition, pas une réservation.

## Reprise de votre conversation réelle

Conversation `7c7adc96-ace1-462b-8faf-17ba562a197a` reprise par le mécanisme de reprise existant, depuis son message original, sans ressaisie ni ajout d'un nouveau message utilisateur. Les garde-fous de reprise et de persistance sont conservés.

Preuve : `reports/slash-sites-original-resumed.json`.

| Champ | Résultat |
|---|---|
| Statut de l'analyse | completed |
| Messages utilisateur avant / après | 1 / 1 |
| Brouillons article | 1 |
| Désignation | PEINTURE ACRYLIQUE BLANCHE 20 KG |
| Code proposé | PEINTURE-ACRYLIQUE-B |
| Catégorie article | NEG |
| Catégorie comptable | Non inventée |
| Unité | UN |
| Sites demandés | **201 et 209** |
| Site scalaire | 201 ; il ne remplace pas la sélection multisite |
| TVA demandée | 20 % |
| Gestion stock | 1 — Non géré |
| Vérifications de base | Réussies, aucune erreur ; les deux sites existent et la catégorie est retrouvée pour chacun |
| Durée backend de reprise | 956,390 ms |
| Appels Qwen / tentatives d'écriture Sage | 0 / 0 |

Les anciennes erreurs restent dans l'historique ; le résultat courant est la reprise réussie. Rouvrir la conversation recharge son état actuel.

## Vérifications exécutées

**Résultat final : 1 550 tests backend réussis, 3 ignorés et 3 tests locaux exécutés séparément avec succès ; 28 tests frontend réussis.**

Les résultats chiffrés définitifs et lignes des fonctions figurent dans `reports/slash-sites-validation-summary.json`.

- Tests ciblés : **30 réussis**, couvrant les 13 nouveaux cas, l'ancien format extincteur et la précédente extraction PEINTURE.
- Qwen réel forcé, distinct du parcours littéral : **2/2 réussis** avec les ordres 201→209 puis 209→201. Durées 25,249 s et 20,190 s ; 281/279 tokens d'entrée, 90 de sortie. NEG reste une catégorie article et les deux sites sont conservés. `slash-sites-real-qwen.json`.
- Navigateur réel ordinateur/mobile, backend local et SELECT TEST : demande exacte puis « Créer l'article », un seul brouillon, deux sites, aucune approbation ni exécution. `slash-sites-live-browser.json`.
- Non-régression backend complète, incluant les 1 000 scénarios de contrat ; tests frontend et trois tests locaux de subprocessus exécutés séparément. Les campagnes antérieures de 100 conversations ne sont pas présentées comme une nouvelle campagne de cette correction.
- SELECT réel : 201 et 209 retrouvés ; `PEINTURE-ACRYLIQUE-B` absent lors du contrôle. `slash-sites-readonly.json`.

## Création réelle et sécurité

**L'article et ses fiches article-site ne sont pas créés.** Les contrôles actuels restent fermés : CRL non disponible/valide pour la validation stricte, preuves de politique et droits AIAGT non validées, écritures désactivées. La reprise ne contourne aucune de ces conditions et ne constitue pas une approbation d'écriture.

Le parcours général d'article/site reste distinct du périmètre historique PowerShell. Chaque article-site nécessite son contrôle de parent, sa préparation, son approbation spécifique et sa relecture. Aucun parent n'étant créé ici, aucun SAVE enfant n'est tenté. Aucun certificat, droit, politique ou service Sage de production modifié ; seul le backend local agent est rechargé après contrôle d'absence d'analyse récente en cours.

L'objectif de création réelle vérifiée reste ouvert. Après résolution des contrôles et validation des règles métier/fiscales applicables, il faudra présenter les données finales exactes et obtenir une approbation humaine spécifique avant tout SAVE.
