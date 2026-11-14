# Corrections du module commandes SOB

Les corrections utilisateur de ce module doivent être conservées dans la mémoire
PostgreSQL du module via `learning_memory.py`, et pas uniquement dans un prompt
ou une condition de code. Ne pas modifier le moteur articles/fournisseurs.

- Pour un alias article : vérifier le code cible dans Sage, puis appeler
  `learning_memory.save('article_alias', alias, {'code': code}, actor=..., source=...,
  approved=True)`. Une nouvelle correction explicite remplace la règle active ;
  la révision précédente reste dans `sob_learning_events`.
- Pour une nouvelle règle de prix/date/unité/interprétation : conserver sa source
  utilisateur ; la structurer avant activation. Une proposition déduite d'un
  échec de test reste `pending` tant qu'elle n'est pas vérifiée.
- Les exemples historiques sont stockés dans `sob_learning_examples`. Une
  correspondance partielle OB ne prouve pas une règle générale de conditionnement.
- Les règles sont des données métier : elles ne donnent jamais le droit de
  produire du SQL, de changer le dossier cible ou de contourner les contrôles.
- Garder les tests de correction/priorité/révision et le rejeu des exemples.
  Ne pas réinitialiser une correction utilisateur en réexécutant le seed.

Les API et le formulaire « Mémoire d’apprentissage » de la page SOB permettent
de mémoriser un alias sans éditer les fichiers. Dans Telegram :
`corriger article pointe 6 = PF-TP16X20`.
