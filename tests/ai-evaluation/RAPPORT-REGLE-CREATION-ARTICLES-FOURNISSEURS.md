# Règle de création articles → fournisseurs

30 octobre 2026. Demande : retrouver comment les articles ont réellement été créés et appliquer l'enchaînement aux fournisseurs. Aucune création réelle ni modification d'une fiche Sage pendant cette intervention.

## Preuve du parcours réellement utilisé pour les articles

| Article TEST | Horodatage de tentative UTC | SAVE | Relecture SOAP | Présence SQL relue aujourd'hui |
|---|---|---|---|---|
| TESTAGENT004 | 2026-10-27T19:35:27.5576336Z | 1 tentative, statut 1 | ReadConfirmed=true, statut 1 | 1 ligne |
| EXT_POUDRE | 2026-10-27T20:06:41.2623789Z | 1 tentative, statut 1 | ReadConfirmed=true, statut 1 | 1 ligne |

Les reçus historiques sont `runtime/powershell-soap-attempts/<code>.attempt.json.result.json`, State=CREATED_AND_READ_BACK. La mémoire réelle PostgreSQL du chatbot contient EXT_POUDRE avec opération PowerShell 5.1 succeeded, outcome.confirmed=true et sql_readback.ok=true. La consultation actuelle de soap_operations n'est pas suffisante pour retrouver ces créations : elles utilisaient un journal PowerShell et l'état de conversation, distincts du journal du connecteur Python générique.

Preuve sélectionnée sans secret : `reports/article-supplier-workflow-comparison.json`. Les deux articles existaient déjà ; ils ne sont ni recréés ni modifiés aujourd'hui.

## Pourquoi les articles fonctionnaient malgré le blocage CRL du fournisseur

Le parcours effectif est `conversation_chat.write_action` → `sage_powershell_chat.write_action` → `scripts/sage_chat_worker.ps1` → `SageTestSoap.psm1`.

Ce module utilise le secret DPAPI admin, le pool POOL_AI_TEST, les publications WS_ARTICLE/WS_AR_SITE et la validation Windows de chaîne/nom/dates. Il conserve le défaut .NET `HttpClientHandler.CheckCertificateRevocationList=false`, confirmé localement sans requête réseau. Son code documente une exception de test historique. Ses clés/catégories/unités/sites et cas spéciaux sont strictement bornés.

Le fournisseur utilise WS_FOURNIS et le connecteur Python exigeant strict + CRL_CHECK_CHAIN. **Le verrou Python HTTP 423 ne gouverne pas le parcours PowerShell historique.** Le diagnostic antérieur présentant ce verrou comme une interdiction commune à tous les parcours était incomplet.

La demande actuelle maintient l'interdiction d'affaiblir la révocation. L'exception de transport et l'utilisation d'admin ne sont donc pas étendues aux fournisseurs. Aucun ajout de WS_FOURNIS à l'allowlist PowerShell et aucun changement du module historique.

## Enchaînement fournisseur désormais branché au chat

Nouveau service `backend/app/services/chat_supplier_actions.py`, fonction `action`, et route de session `/api/v1/chat/conversations/{id}/partners/{partner_id}/{action}` :

1. Vérifier le propriétaire de la conversation, la révision, le type fournisseur, TEST et l'absence d'analyse/annulation en cours.
2. Vérifier la sécurité stricte fournisseur, indépendamment de l'exception article PowerShell. Une barrière fermée renvoie HTTP 423 avant tout appel au service Sage.
3. **prepare** : après relecture humaine, refaire les contrôles SQL de doublon et référentiels, construire le XML à partir des données exactes confirmées, puis créer l'opération locale avec le service SOAP générique. Aucun SAVE.
4. **approve** : confirmation booléenne explicite, empreinte des champs inchangée, nouveau contrôle SQL, approbation liée au digest de l'opération. Le token à durée limitée reste uniquement en mémoire serveur et n'est pas rendu dans la conversation.
5. **execute** : vérifier propriétaire, empreinte, opération et expiration ; contrôler à nouveau les doublons ; consommer le permis et enregistrer executing dans PostgreSQL avant l'appel SOAP. Le service générique consomme également son approbation ponctuelle. Aucune nouvelle tentative automatique.
6. Vérifier avec `supplier_readback` les réponses SOAP et les champs SQL, y compris nom, code et activation du fournisseur et du tiers. Publier uniquement le résultat effectif.

Les opérations exécutées, ambiguës, échouées ou non vérifiées ne sont pas rejouables. Une correction avant exécution invalide la préparation ; un nouveau prepare invalide son ancien journal/approbation locale. Une correction pendant ou après une tentative est refusée tant que son résultat n'est pas traité, pour ne pas afficher des valeurs conversationnelles différentes de celles envoyées.

Frontend : `SupplierActions.jsx` et `SupplierPreparation.jsx`, appel depuis `ChatApp.jsx`. Préparation puis bouton **« Approuver et créer ce fournisseur dans TEST »** ; ce clic effectue approve puis execute avec la révision retournée. Aucun token ni choix de publication SOAP demandé à l'utilisateur. L'état créé/incomplet est dérivé des preuves `supplierResult`, pas d'une simple réponse positive.

L'interface reçoit maintenant `supplier_security` distinct de `security` article. Si la sécurité fournisseur n'est pas prête, elle affiche explicitement l'indisponibilité ; la relecture du brouillon ne donne plus l'impression d'être une commande de création. Les champs nécessaires au XML doivent être réellement renseignés et validés : le nouveau parcours ne transforme pas silencieusement les suggestions métier non confirmées en valeurs applicables.

## Tests réellement exécutés

- `reports/supplier-same-workflow-full.xml` : **1498 réussites, 3 ignorés, 3 tests sous-processus exclus**. Les sept premiers tests de parcours sont inclus dans cette régression.
- Dernière régression `reports/supplier-same-workflow-full-final.xml` : **1502 réussites, 3 ignorés, 3 tests sous-processus exclus**, incluant les onze tests de parcours et le garde-fou lié à la description SOAP.
- `reports/supplier-same-workflow-cycle-02.xml` : **71 réussites**, dont huit tests de parcours fournisseur avec PostgreSQL isolé et Sage/SQL simulés : création active confirmée, absence de token dans le chat, aucun envoi avant approbation, doublon d'exécution refusé, gate 423 à chaque étape, confirmation manquante, permis expiré, modification après préparation, CSRF et doublon apparu après approbation.
- `reports/supplier-same-workflow-final-targeted-02.xml` : **11 réussites** sur le parcours seul, incluant aussi refus d'OB, propriétaire différent et échec de sécurité lié à la description SOAP. Une préparation ne devient pas approuvable si le contrôle spécifique de publication échoue, même si le contrôle général est positif.
- `reports/supplier-same-workflow-frontend.xml` : **28 réussites** ; compilation Vite réussie.
- `reports/supplier-workflow-mocked-browser.json` : navigateur sur réponses simulées, clic unique d'approbation de création entraînant prepare/approve/execute dans l'ordre attendu ; succès actif affiché uniquement avec preuves concordantes, fournisseur inactif présenté comme vérification incomplète. Aucun envoi Sage réel.
- Navigateur réel ordinateur/mobile avec le backend et SELECT TEST : `reports/palmeraie2-live-browser.json`, contrôle du message de blocage fournisseur, conservation du brouillon et des identifiants. Un premier lancement trop tôt après rechargement local a donné ERR_CONNECTION_REFUSED ; preuve conservée dans `reports/supplier-workflow-live-startup-failure.json`, puis health vérifié et retest réussi.
- Session réelle : `reports/supplier-workflow-live-closed-gate.json`, nouvelle route fournisseur prepare répond **423**, sans opération créée ni SAVE. Cette preuve montre aussi sécurité article PowerShell et sécurité fournisseur séparées.

Les SAVE de cette suite fournisseur sont contrôlés/simulés. Ils ne constituent pas des fournisseurs réellement créés. La campagne historique de 100 conversations n'a pas été relancée sur cette modification de parcours ; ne pas la présenter comme telle.

Un rechargement local a interrompu une analyse réelle en cours. L'état PostgreSQL et la demande originale ont été conservés ; cette analyse orpheline, antérieure au redémarrage, a été reprise de façon ciblée par le parcours d'analyse uniquement. Résultat completed, même empreinte de demande et aucun message utilisateur ajouté en double. Preuve `reports/supplier-workflow-orphan-recovery.json`. Aucun SAVE ni approbation de création déclenché par cette reprise. Pour toute intervention suivante, attendre la fin des analyses actives avant le rechargement. Backend final parent PID 11320, à vérifier avec logs/backend.pid et sa commande avant tout arrêt.

## Ce qui reste bloqué et objectif non atteint

Le fournisseur ne peut toujours pas être créé réellement : CRL SAGE-CA-2 absente, droits AIAGT ADMIN à revoir et politique d'exécution non validée ; écritures génériques désactivées. Aucun contournement HTTP 423. Demande administrative existante : `docs/DEMANDE-ADMIN-PKI-AIAGT-20261030.md`.

Les données DROGUERIE PALMERAIE 2 et le code F10013 restent une préparation : code non réservé, défauts métier non encore confirmés et aucune charge utile finale approuvée. Les valeurs requises par `supplier_xml.proposal` et les règles conditionnelles doivent être validées ; une demande fiscale courte ne suffit pas encore à certifier les paramètres manquants.

Une fois les prérequis réels satisfaits, ce parcours pourra être exercé avec un fournisseur TEST et l'approbation des données exactes, puis contrôlé par SOAP read et SELECT. **Le branchement logiciel est testé ; le fonctionnement réel fournisseur reste à valider. Le projet n'est pas déclaré terminé.**
