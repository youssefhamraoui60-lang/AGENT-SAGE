# AGENT SAGE X3

Agent IA Windows pour Sage X3 : interface web, commandes Telegram SOB,
fournisseurs par e-mail, lecture de PDF/photos et mémoire PostgreSQL.

## Installation et utilisation

- [Guide de restauration de A à Z](docs/INSTALLATION-RESTAURATION-A-Z.md)
- [SQL Sage : lecture, création et modification](docs/SQL-SAGE-CREATION-MODIFICATION.md)
- [Module commandes SOB](telegram-test/README.md)
- [Lecture des documents et voyages ciment](telegram-test/SOB-LECTURE-ET-CHARGEMENTS.md)

Ce dépôt public contient le code et la documentation. La sauvegarde privée avec
les bases, `.env`, sessions, modèles et documents est conservée séparément.
Copier `.env.example` vers `.env`, puis renseigner localement les paramètres.
Le dossier `TEST` contient aussi des workers utilisés en exploitation : le garder.
Les fonctions Sage nécessitent un serveur et des comptes autorisés ; les scripts
de création/modification doivent passer par leurs validations et simulations.

Depuis le 14 novembre 2026, les messages Telegram sont traités séparément.

- [Publier dans GitHub](docs/PUBLICATION-GITHUB.md)
