# Nettoyant multi-site et demandes de création — 28 octobre 2026

## Résultat

Le message `CRRER UN ARTICLES DE Nettoyant FAP-NET 1L ECO1105 ... site 202 ET 201 ... ne pas de fornssieur` a été reproduit, corrigé puis vérifié avec le vrai navigateur, le backend local et les lectures SQL TEST.

Après la réponse **NEG**, le brouillon contient :

| Désignation | Catégorie | Unité | TVA demandée | Stock | Fournisseur | Sites demandés |
| --- | --- | --- | --- | --- | --- | --- |
| Nettoyant FAP-NET 1L ECO1105 | NEG | L | 12 % | Non géré | Sans fournisseur | 202 et 201 |

Les deux sites et l'existence de la catégorie ont été vérifiés séparément dans TEST. Les fiches article-site sont absentes dans les lectures de ce scénario ; aucune n'a été créée. Le code TVA reste inconnu : trouver un taux de 12 % ne certifie pas son applicabilité ni son mapping.

L'affichage en tableau demandé est maintenant suivi et conservé dans PostgreSQL. Il présente désignation, code proposé, catégorie, unité, sites, TVA, fournisseur, stock et état. Les contrôles et confirmations restent disponibles dans des détails séparés, sans transformer la demande d'affichage en création.

## Causes confirmées et corrections

| Défaut | Cause et correction | Fichier / fonction |
| --- | --- | --- |
| « CRRER » déclenchait l'IA générique | La grammaire courte ne reconnaissait pas ce verbe et cette structure sans séparateurs. Une extraction littérale bornée conserve maintenant la désignation complète et les champs explicitement fournis. | `backend/app/services/chat_article_requests.py:39`, `literal_extract` ; `chat_fast_extract.py:5`, `extract` |
| Site 201 perdu | Le schéma historique comportait un seul `site` ; le détecteur conservait le premier. Une sélection déclarative validée par Pydantic conserve maintenant `requested_sites=['202','201']`. | `chat_article_requests.py:8`, `SiteSelection` ; `declared_sites:32`, `apply:60` |
| « non gréer » ignoré | Le motif ne reconnaissait que « non géré ». La variante déclarée est reconnue par le détecteur et le contrôle de provenance ; elle devient `gestion_stock='1'`. | `chat_turns.analyse` ; `conversation_chat.grounded` |
| « pas de fornssieur » ignoré | Cette graphie manquait aux alias. Un motif partagé reconnaît désormais ce retrait explicite ; aucun fournisseur ni code n'est demandé ou inventé. | `chat_turns.SUPPLIER_WORD` ; `chat_semantics.supplier_decision` |
| « CRER LE » pouvait relancer une création d'entité | Une demande portant sur les fiches déjà décrites repartait vers Qwen et pouvait reproposer un fournisseur. Cette intention est reconnue sans ajouter d'article ou de fournisseur et sans accorder d'approbation. | `chat_article_requests.py:21`, `creation_request` ; `conversation_chat.merge`, `compose` |
| Tableau demandé mais cartes conservées | La préférence de présentation n'avait ni état ni rendu dédié. Elle est maintenant persistée dans `state.presentation.article_view` et rendue par un tableau. | `chat_article_requests.py:13`, `presentation` ; `frontend/src/ChatApp.jsx`, `ArticleTable` |
| « indiquez 201 » malgré les deux sites demandés | Le connecteur historique exige 201 dans son champ unique. Le message public distingue maintenant cette limite technique de la sélection métier déjà conservée. | `conversation_chat.compose` ; `ChatApp.jsx`, `articleErrorLabel` |

Le champ historique `site=202` reste présent pour compatibilité avec les fonctions existantes ; il ne représente pas toute la sélection. Les choix complets sont dans `requested_sites`, leur provenance et les contrôles par site. Les outils vérifient chaque site, chaque catégorie applicable et chaque fiche enfant séparément dans `conversation_chat.tool_plan:349` et `validate_article_draft:384`.

La pièce jointe `7f9e1695-ff73-4dec-9561-4fc140532f0d/Pasted text.txt` décrit la conversation AHMNDE ; le second cas Nettoyant figure dans le message utilisateur. Les deux ont été pris en compte. Les demandes de création et de tableau ne recréent plus un brouillon fournisseur AHMNDE déjà présent.

## Vérifications exécutées

- **Avant correction : 4 tests en échec**, reproduisant extraction, absence de fournisseur, demande de création existante et préférence de tableau : `reports/nettoyant-before.xml`.
- **Après correction : 66 tests ciblés réussis**, incluant les régressions AHMNDE, Modern Foam et performances : `reports/nettoyant-cycle-02.xml`.
- **Régression complète : 1 423 réussites, 3 ignorés, 4 exclus** : [nettoyant-full-cycle-01.xml](nettoyant-full-cycle-01.xml). Les 1 000 scénarios distincts sont inclus, sans additionner les campagnes qui se recouvrent.
- **100 conversations simulées réussies, 790 tours**, aucun échec, aucun appel d'inférence Qwen nécessaire pour ces formulations : `conversations/20261028T151457Z/run_manifest.json`. Leur source backend a été comparée aux fichiers actuels, sans différence.
- **Vrai navigateur ordinateur et mobile, vrai backend et SELECT TEST : réussis** : [nettoyant-live-ui.json](reports/nettoyant-live-ui.json). Saisie exacte, réponse NEG, demande de création après confirmation, tableau, puis rechargement et restauration de la conversation.
- Un second site inexistant (`999`) bloque la validation tout en restant conservé dans les données. Les deux sites valides 202 et 201 ne sont plus redemandés.
- Le navigateur a interdit toute route POST de relecture, d'approbation ou d'exécution pendant ce test. La demande de création dans le texte n'a produit ni opération Sage ni approbation interne.
- Build Vite et navigateurs de non-régression fournisseurs/clients et Modern Foam : réussis. Les 17 tests frontend du suivi et des résultats de création ont leurs preuves séparées dans `reports/timeout-multi-frontend.xml`.

Le premier lancement du navigateur a précédé l'ouverture du port après redémarrage : échec de connexion conservé dans `reports/nettoyant-live-ui-before-ready.json`. Le test a été relancé après vérification de `/health` et a réussi. Aucun succès n'a été déduit de cet essai initial.

Captures vérifiées visuellement : [ordinateur](reports/nettoyant-desktop.png), [mobile](reports/nettoyant-mobile.png). Les tableaux sont défilables horizontalement si nécessaire ; les explications de blocage restent dans les contrôles de la fiche.

## Pourquoi la création ne devient pas directe après « OK »

La compréhension du besoin est corrigée. Le connecteur d'écriture reste volontairement limité : code de test, unité UN dans le parcours générique, site unique attendu et mapping de stock restreint. La demande contient L, deux sites et « Non géré ». La relecture d'un brouillon n'est pas l'approbation d'un XML de création validé.

Ces restrictions n'ont pas été modifiées ou contournées. L'unité L n'est pas remplacée par UN, aucun site n'est supprimé, le code proposé n'est pas transformé silencieusement et le stock demandé reste conservé. Une extension autorisée du connecteur et les validations métier/fiscales seraient nécessaires pour écrire ces données exactes. Le parcours article-site exécutable reste limité à EXT_POUDRE.

**Aucune création réelle Sage dans cette phase.** Le lot de vingt créations demeure non approuvé ; les droits SQL, certificats, politiques et connecteurs sensibles restent inchangés. Voir également [le rapport timeout/multi-opérations](RAPPORT-TIMEOUT-MULTI-OPERATIONS.md) et [la reprise](REPRISE.md).

Le backend local a été rechargé sur les sources vérifiées. Une page déjà ouverte doit être rechargée pour utiliser le nouveau frontend ; un rechargement complet évite de conserver l'ancien bundle affichant les cartes.
