# Lecture des commandes SOB — corrections du 13 novembre 2026

Le module conserve le dossier TEST et le routage Telegram existants. Les moteurs
articles/fournisseurs ne sont pas modifiés. Les rejeux de contrôle n'appellent pas
la création des commandes.

## Voyages de ciment

VYS, VGS, VGE, VOY, voyage, plusieurs écritures sans espaces et variantes
orthographiques sont normalisés en voyages de CPJ35/CPJ45. Un voyage ne vaut pas
automatiquement 560 ou 540 sacs. Les anciennes équivalences globales CPJ45 → 560
ont été retirées de la mémoire PostgreSQL.

Exemples :

- `2 VYS CPJ35` : article et nombre de voyages reconnus ; chargement à préciser.
- `2 VYS CPJ35 ; 560 sacs par voyage` : 1 120 sacs.
- `2 voy CPJ45 ; soit 1080 sacs` : 1 080 sacs, pas deux fois ce total.
- Des chargements contradictoires ou plusieurs grades sans affectation claire
  ne permettent pas la création.

La quantité en sacs d'un voyage non confirmé reste vide dans le brouillon.
Le programme ne présente pas un voyage comme un sac et ne calcule pas un total
commercial à partir de ce nombre provisoire.

## Documents

L'OCR Windows conserve les lignes et les mots avec leurs coordonnées. Une lecture
agrandie récupère les en-têtes, pieds de page/cachets et colonnes de prix, notamment
les prix dans des cellules fusionnées. Les images et PDF scannés peuvent aussi
être lus par GLM-OCR sur le serveur Ollama local. Le modèle `glm-ocr` a été installé
et testé sur des photos réelles ; aucune image n'est envoyée à un nouveau service
cloud par ce lecteur. Le fournisseur texte existant reste utilisé pour préparer
la commande à partir du texte extrait.

La politique PostgreSQL `document_visual_ocr` contrôle cette lecture. En cas de
modèle indisponible ou de délai dépassé, l'OCR d'origine reste disponible. Une
lecture initiale très faible reste explicitement à confirmer. Il ne suffit pas
qu'une réponse du modèle soit grammaticalement correcte pour garantir les chiffres.

Les tableaux acier et ciment présentant les colonnes et données requises sont
repris de façon déterministe : toutes les lignes, diamètre, quantité, unité et
base du prix. Le programme contrôle aussi le total TTC du document quand il est
lisible. Un prix TTC par tonne n'est pas un prix par sac.

Les noms d'émetteurs sont comparés sans les seules formes juridiques STE/Société,
SARL/AU/SA, mais tous les mots d'identité/projet sont conservés. Les homonymes et
les noms du fournisseur ne remplacent pas le client. L'ICE et les codes Sage
doivent toujours être vérifiés dans le référentiel.

Des transcriptions relues visuellement par Codex ont été conservées en mémoire
pour des pièces vérifiées, uniquement sous leur empreinte SHA256 exacte. Une modification
du fichier ne réutilise pas cette transcription. Ces corrections ne constituent
pas un entraînement des poids du modèle et ne garantissent pas une lecture
identique d'une nouvelle écriture manuscrite.

## Variantes et contrôles

Les corrections d'alias vérifiées dans Sage sont persistées dans PostgreSQL,
notamment F14/F6t, HLE, Tradicim/Tradissim, références de madriers et l'alias client
C7009 → C07009. Les clés de mémoire conservent les lettres arabes, au lieu de les
supprimer ou de les confondre avec un alias numérique.

Les quantités explicites du texte sont conservées avant conversion ; par exemple
`4T6` signifie 4 tonnes de diamètre 6. Pour P_MD3/P_MD4 vendus en ML, des pièces
explicitement dimensionnées sont converties en mètres linéaires indépendamment
de la base du prix. Un fardeau sans conditionnement vérifié reste à confirmer.

Les corrections propres à un autre document/client ne sont pas injectées dans
le contexte général du modèle. Activation, relance et consigne de récupération
de chèques ne doivent pas créer une nouvelle commande.

`Ciment blanc 40 kg` sans marque/type reste ambigu : une recherche partielle ne
prouve pas qu'il faut choisir POWER CEM plutôt que CEM I 52.5R. Le code exact doit
être précisé avant création.

## Validation et reprise

Les tests ciblés couvrent la lecture, les unités/prix, les langues, les documents,
la séparation des clients, le routage et les refus de création. Les sources et
résultats des rejeux sont dans `runtime/sob-improvements-20261113` et les exemples
sont conservés dans `sob_learning_examples`.

Les sous-processus de préparation et de lecture chargent le code à chaque demande.
Les modifications de ces modules et de la mémoire s'appliquent aux prochaines
préparations ; il n'est pas nécessaire de couper le listener pour ces changements.
Les commandes historiques et les reçus de création existants ne sont pas modifiés.

Pour réinstaller le lecteur local sur un autre poste : `ollama pull glm-ocr`.
Les paramètres du modèle et du délai restent des paramètres du service, jamais
des instructions acceptées depuis un document reçu.
