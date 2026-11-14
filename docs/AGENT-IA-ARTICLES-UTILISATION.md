# Agent IA local — préparation et création contrôlée d’articles

Interface : http://127.0.0.1:8000/sage/?resource=agent depuis la VM agent ou via le transfert de port déjà utilisé. Le backend écoute sur loopback ; aucun port réseau ou pare-feu n’a été modifié pour cette livraison.

## Utilisation

1. Ouvrir l’onglet **Agent IA**. Renseigner le jeton local APPROVAL_TOKEN du fichier privé C:\AGENT-SAGE-X3\.env dans le champ dédié ; ne jamais le mettre dans la conversation.
2. Écrire par exemple : « Crée un nouvel article Ciment CPJ35, catégorie NEG, unité SAC, pour le site 201. » Cliquer **Analyser ma demande**. Ollama Qwen 2.5 7B extrait les informations explicitement présentes. Les valeurs manquantes restent vides. Un code absent est proposé par l’application, clairement identifié comme généré et non réservé.
3. Modifier la fiche si nécessaire, puis **Enregistrer les corrections**. Chaque modification incrémente la révision et invalide la validation et la préparation précédentes. Une demande déjà approuvée ou ayant fait l’objet d’une tentative est immuable.
4. **Vérifier dans SQL Server** : recherche exacte du code, désignations identiques (cinq maximum), catégorie, unité, site, fournisseur éventuel et article de référence. Les erreurs et résultats de référence sont affichés. Les requêtes sont des SELECT fixes avec paramètres et délais bornés, dans TEST uniquement.
5. **Valider le brouillon** : validation humaine locale avec nouveaux contrôles SQL. Cela ne vaut pas approbation d’écriture, ni certification de toutes les règles conditionnelles Sage.
6. **Préparer la création Sage** : le connecteur existant recontrôle la publication V12/TEST et l’absence du code par SOAP read ; il enregistre une opération et son XML, sans save. L’enveloppe n’est pas envoyée.
7. Lorsque toutes les conditions serveur sont satisfaites : saisir valideur et motif, cocher la confirmation spécifique puis **Approuver cette création**. Un jeton d’exécution à usage unique reste seulement en mémoire dans l’onglet. Une seconde action **Exécuter la création approuvée** déclenche le connecteur existant, sans retry.
8. Le résultat est confirmé uniquement si le statut/relecture Sage et le SELECT SQL correspondent aux champs demandés. Sinon, afficher non confirmé et investiguer sans relancer. L’historique permet de rouvrir les demandes ; aucun jeton n’y est exposé.

## État réellement livré

Le parcours réel analyse → correction → SQL → validation → préparation SOAP → historique fonctionne. Les protections existantes restent actives. L’interface affiche **Création en attente de configuration Sage** et les boutons d’approbation/exécution restent désactivés. Aucune création Sage n’a été effectuée pendant le développement.

Les limites sont explicites : un article par conversation ; le site est vérifié mais aucune fiche ITF n’est créée implicitement ; un fournisseur demandé doit être identifié et son mapping de relation revu avant préparation. Les catégories, taxes, comptabilité et autres obligations conditionnelles ne sont pas complétées par des valeurs techniques inventées. Les valeurs de catégorie peuvent être consultées, mais ne sont pas copiées automatiquement. La confirmation SQL du code est une photographie, pas une réservation ; le contrôle est répété avant exécution.

Le lecteur SQL réutilise le mode TMS à chiffrement non exigé autorisé précédemment et le secret DPAPI local. Cela ne lève aucune exigence HTTPS SOAP. Les identifiants SQL/Sage et jetons de l’application ne sont pas ajoutés aux prompts ; les collages manifestes de secrets et les secrets configurés reconnus sont refusés avant analyse.

## Fichiers et maintenance

- API : backend/app/api/article_agent.py ; service : backend/app/services/article_agent.py.
- SQL de consultation : scripts/article_agent_sql_reader.ps1 ; aucune interface de SQL libre, aucun DML Sage.
- PostgreSQL local : migration additive backend/migrations/006-article-agent.sql, tables article_agent_drafts et article_agent_events. Les demandes/modèle restent dans requests ; les approbations/tentatives/réponses/relectures SOAP dans les tables soap_operations et associées existantes. Les réponses SOAP complètes suivent le mécanisme d’archivage existant.
- UI : frontend/src/ArticleAgent.jsx ; build dans frontend/dist, servi par FastAPI.
- Redéploiement sur cet environnement : exécuter backend\.venv\Scripts\python.exe scripts\migrate_article_agent.py après les migrations existantes, reconstruire le frontend avec le Node existant, puis redémarrer seulement le backend agent si nécessaire. Aucun besoin de redémarrer Sage, Ollama, PostgreSQL ou n8n pour charger ce code.
- Sauvegarde : inclure le schéma PostgreSQL de l’agent, les fichiers du projet et les preuves/réponses privées existantes. Le fichier DPAPI reste lié à son identité Windows ; ne pas le publier ni supposer qu’il est portable vers une autre machine.

La validation des prérequis Sage et une approbation spécifique restent indispensables pour le premier vrai save ; les tests automatisés d’exécution utilisent un faux connecteur, jamais l’ERP.
