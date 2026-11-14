# Propositions sensibles — non appliquées

## Relecture d'une fiche article-site existante

Défaut reproduit par `scripts/probe_existing_site_simulation.ps1` : le plan demande UN, la fiche existante simulée contient M2, et le connecteur retourne `ReadConfirmed=true`. Aucun appel Sage ni SAVE n'a été effectué. La preuve est `tests/ai-evaluation/failures/existing-site-mismatch-simulation.json`.

Cause : le retour anticipé `ALREADY_EXISTS` de `Invoke-SageTestArticleSiteCreation` ne compare pas les champs réels aux valeurs attendues.

Le fichier `PROPOSITION-ARTICLE-SITE-READBACK.patch` propose une comparaison explicite des champs du plan. En cas d'écart ou d'absence de valeurs attendues, il retourne `EXISTING_RECORD_MISMATCH`, `ReadConfirmed=false`, zéro SAVE et aucune réémission. Les fiches existantes conformes gardent l'état `ALREADY_EXISTS` et zéro SAVE.

Ce patch n'est pas appliqué. Après approbation distincte de cette modification du connecteur, il faudra l'implémenter, exécuter la simulation négative et les régressions multisites, puis vérifier les cas de plan incomplet et de modification concurrente.

## Extension bornée pour la recette des 20 paires

Le connecteur article-site actuel n'accepte que EXT_POUDRE. Aucun appel privé direct à SAVE ne doit servir à contourner cette restriction.

Après réception des corrections demandées par l'utilisateur et validation du lot exact, une adaptation distinctement approuvée devra :

- limiter les codes, sites et valeurs au manifeste final approuvé ;
- lier l'approbation à l'empreinte du manifeste, des XML et des descriptions TEST/V12 ;
- conserver les contrôles de doublons, les marqueurs atomiques et les approbations à usage unique ;
- créer et relire le parent avant de préparer sa fiche article-site ;
- comparer chaque champ attendu, en distinguant présence antérieure, création confirmée, écart et résultat ambigu ;
- ne jamais réémettre automatiquement une opération incertaine ;
- conserver une seule voie d'écriture contrôlée, sans modifier certificats, comptes ou permissions.

Les données exactes sont encore à corriger et le périmètre final n'est pas approuvé. Aucune extension du connecteur n'est installée.

## Droits SQL

Les lectures de préparation ont révélé INSERT/UPDATE sur quatre tables TEST pour le compte de consultation. Aucun droit n'a été utilisé en écriture ni modifié. Ce constat interdit de certifier ce compte comme strictement lecture seule ; sa régularisation relève d'une approbation séparée, hors de la simple validation du lot.
