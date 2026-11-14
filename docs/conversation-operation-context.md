# Contexte métier JSON et moteur DeepSeek

Chaque conversation conserve `state.operation_context` dans PostgreSQL, avec
`schema_version`, le dossier TEST ou OB, l’objectif courant, les opérations,
leurs paramètres, leurs changements, leurs blocages et les événements récents.
Les identifiants de brouillon restent stables lorsqu’une fiche est complétée.
Une création annulée et ses valeurs restent distinctes d’une modification.

Le schéma est dans `config/conversation-state.schema.json`. Le fichier
`docs/agent-session.example.json` illustre une session fictive ; il ne constitue
ni une préparation réelle ni une autorisation d’écriture.

## Routage

Avec `CONVERSATION_DEEPSEEK_PRIMARY_ENABLED=true`, DeepSeek reçoit en premier
le message et le contexte métier via les outils natifs. Les valeurs extraites
doivent être justifiées par les propos de l’utilisateur. Les outils valident les
types, la cible, le dossier et les règles Sage. DeepSeek peut compléter un
brouillon, consulter, proposer plusieurs modifications, annuler une demande
ou demander une précision.

Le choix explicite du mode local reste respecté. En cas d’indisponibilité du
prestataire, les lecteurs locaux peuvent reprendre les faits littéraux sans
inventer de réussite. Le prestataire réellement utilisé et le motif de repli
sont distingués dans les diagnostics du contexte. Aucun changement automatique
de dossier TEST/OB n’est permis.

## Export privé

Dans une conversation ouverte : **Mon compte → Mon espace → Exporter la session (.json)**.
L’API correspondante est `GET /api/v1/chat/conversations/{id}/operation-state.json`.
Elle exige la session authentifiée du propriétaire et renvoie un téléchargement
non mis en cache. Les anciennes conversations sont projetées à la demande.

L’export ne contient ni clé API, ni permis d’exécution, ni plan SQL, ni mot de
passe. Il n’existe pas de route d’import qui transforme ce JSON en autorisation.
PostgreSQL demeure la source de vérité ; le téléchargement est une projection.
La liste `events` conserve au maximum 100 événements d’outils, sans remplacer
l’historique complet des messages. Le JSON et les propositions du modèle ne
déclenchent jamais une écriture Sage : les confirmations existantes s’appliquent.

## Vérification

`TEST/test_operation_context.py` vérifie le moteur prioritaire, la conservation
des paramètres, le passage création → annulation → modifications multiples,
la validité du JSON, l’annulation ciblée d’un article et l’isolation des comptes.
