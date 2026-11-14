# Préparation de trois fournisseurs de test

28 octobre 2026. Demande utilisateur : tests réels avec des noms différents. Dossier cible exclusivement TEST ; OB reste en lecture seule. Aucune écriture Sage exécutée.

| Test | Nom proposé | Recherche SQL TEST | Code définitif |
|---|---|---|---|
| 1 | TEST AGENT FOURNISSEUR ALPHA 20261028 | Aucune correspondance au nom | Non attribué |
| 2 | TEST AGENT FOURNISSEUR BETA 20261028 | Aucune correspondance au nom | Non attribué |
| 3 | TEST AGENT FOURNISSEUR GAMMA 20261028 | Aucune correspondance au nom | Non attribué |

Preuve : `reports/supplier-real-tests-preparation.json`, quatre consultations réussies, dont le profil FR dans TEST. L'absence de correspondance au nom ne constitue pas une vérification fiscale de nouvelles identités. Aucun ICE, IF ou RC fictif n'a été inventé.

Profil cible relu : FR, MA, MAD, CHQ00, MAR, STD ; existence des références vérifiée. Ces valeurs ne sont pas encore approuvées, et l'applicabilité société/législation de CHQ00 reste à valider. F10013 est une suggestion non réservée pour un seul candidat à l'instant de lecture, pas trois codes disponibles attribués et pas le prochain numéro officiel Sage.

Le connecteur déclare une ressource suppliers / publication WS_FOURNIS (`backend/app/services/sage_gateway.py`, RESOURCES), mais cela ne démontre pas que les règles d'écriture et les autorisations du dossier cible sont satisfaites. La préparation conversationnelle conserve creation_ready=false. Ne pas modifier de politique pour exécuter ces tests.

À terminer avant une demande d'approbation des fiches exactes : confirmer la numérotation réellement affectée, les obligations de la transaction, l'adresse de test et les autres champs requis, l'admissibilité d'identifiants fiscaux vides pour des fournisseurs fictifs, puis préparer les trois charges utiles et vérifier les droits existants. L'approbation doit porter sur ces données exactes, pas seulement sur les trois noms. Ensuite seulement : création officielle unitaire avec relecture effective du fournisseur, du tiers et des adresses ; conserver les réponses et erreurs sans réessai aveugle.

Statut : préparation partielle ; **0/3 fournisseur créé**, aucune création déclarée réussie.
