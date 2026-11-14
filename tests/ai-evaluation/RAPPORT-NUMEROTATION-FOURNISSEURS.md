# Vérification des codes fournisseurs — 28 octobre 2026

Lectures SQL réelles OB et TEST, sans aucune écriture Sage. Preuves brutes : `runtime/supplier-ob-audit/code_convention.json`, `rules.json`, `numbering3.json`, `counter_values.json`. Script : `scripts/inspect_supplier_ob_readonly.ps1`, fonction `Read-Only`, phase `code_convention` : six SELECT réussis.

## Formats présents

| Format numérique | Nombre OB | Nombre TEST |
|---|---:|---:|
| F + 3 chiffres | 961 | 961 |
| F + 4 chiffres | 120 | 111 |
| F + 5 chiffres | 11 | 1 |

Ces nombres concernent uniquement les codes F suivis exclusivement de chiffres. Les codes atypiques, dont DROGUERIEPALME dans TEST, existent aussi et ne sont pas comptés ici. Ils ne sont ni renommés ni supprimés.

**F012 existe dans OB et TEST : LAFARGE TETOUAN, catégorie FR.** Ce code ne peut pas servir à créer DROGUERIE PALMERAIE. F0012 n'a pas été trouvé parmi les codes contrôlés, ce qui ne constitue ni une réservation ni une proposition conforme au compteur. OB contient F10022 DROGUERIE PALMERAIE ; TEST contient toujours DROGUERIEPALME nommé erreur avec les mêmes identifiants fiscaux.

Les quinze derniers fournisseurs F ont été relus par date de création : TEST commence par F1115, F1114, F1113 ; OB par F10022, F10021, F10020. Cela confirme plusieurs longueurs et interdit de confondre date récente, ordre lexical et prochain numéro.

## Compteurs et règle non encore démontrée

ACODNUM XBPS décrit F + quatre chiffres, longueur totale cinq, dans chaque dossier. AVALNUM XBPS vaut 1033 dans les deux. Le compteur BPS décrit BPS- + six chiffres. Aucune affectation BPS/XBPS n'a été relevée dans les lignes TABCOUAFF consultées ; REFCOU de la catégorie FR était vide lors de l'audit fournisseur. On ne peut donc pas certifier le compteur effectivement utilisé par la transaction manuelle sur la seule base de ces tables. Ni F1034 ni F10023 ne sont déclarés prochain numéro officiel.

## Application dans l'agent

Le moteur existant `backend/app/services/chat_supplier_preparation.py`, fonction `prepare`, accepte déjà uniquement une proposition `F[0-9]{1,14}`, avec absence contrôlée dans le dossier cible, absence de doublon fiscal et absence d'erreur. Il ne fabrique pas un code à partir du nom. Les zéros sont conservés dans une proposition reçue. La proposition reste non réservée, non officielle et non appliquée au brouillon ; elle n'autorise aucune création. L'allocation MAX+1 observée par la requête du profil est une suggestion manuelle, pas une reproduction certifiée du compteur Sage.

Aucune modification de la logique applicative n'était nécessaire pour imposer F + chiffres : cette règle est déjà en place. Les codes existants atypiques doivent néanmoins rester visibles pour détecter les doublons. Une nouvelle règle de longueur fixe F + trois chiffres serait contraire aux données réellement présentes.

Tests ajoutés dans `backend/tests/test_supplier_ob_preparation.py` : conservation littérale de F012/F0012/F1115/F10022 sur disponibilité synthétique, zéros initiaux, absence d'attribution et de réservation ; refus de proposer un code occupé. F012 est occupé dans la vraie base : le test synthétique ne prétend pas le rendre disponible. Résultats : `reports/supplier-code-convention.xml`.

Avant toute création future : établir l'affectation effective du compteur de la transaction cible, ou confirmer explicitement l'autorisation du code manuel, puis recontrôler l'unicité et obtenir l'approbation de la fiche exacte. OB reste exclusivement en lecture seule. Aucune création, modification ou consommation de numéro n'a été effectuée pendant cette vérification.
