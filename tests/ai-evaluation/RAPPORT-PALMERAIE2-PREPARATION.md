# DROGUERIE PALMERAIE 2 — préparation et blocage réel

Vérification du 30 octobre 2026. Aucune écriture Sage ni modification de fiche existante.

Demande conservée : NOM DROGUERIE PALMERAIE 2, ICE 001850814005094, IF 20734924, dossier cible TEST. RC non fourni, non inventé. La relecture SQL n'a trouvé aucune correspondance exacte sur le nom ou ces identifiants à l'instant du contrôle.

## Défaut applicatif corrigé

La recherche élargie utilisait le mot DROGUERIE et retournait F438 LA HAUTE DROGUERIE, F548 DROGUERIE SETTAT et F934 DROGUERIE LYNE. `chat_partners.validate` transformait toute ligne trouvée en erreur bloquante `similar_partner_requires_review`, indépendamment de l'identité exacte. Le texte disait ensuite « Des fiches proches existent » sans les afficher, tandis que le rapprochement fiscal ne contenait aucun doublon.

Correction dans `backend/app/services/chat_partners.py` : pour les fournisseurs, les correspondances de nom exactes restent bloquantes ; les noms seulement proches deviennent une liste informative `near_names`, avec leurs codes et noms. Les correspondances ICE/IF/RC et codes déjà occupés restent contrôlées. `chat_supplier_preparation.prepare` bloque explicitement aussi le nom exact retrouvé dans le rapprochement tiers. Aucune fiche existante fusionnée, modifiée ou sélectionnée automatiquement. Le comportement client n'est pas changé.

React `SupplierPreparation.jsx` affiche ces résultats comme recherche élargie, sans prétendre qu'ils constituent un doublon fiscal. Le bouton de relecture du brouillon peut être utilisé ; il ne constitue toujours pas une approbation de SAVE.

Preuves avant/après : `reports/palmeraie2-creation-readiness.json` et `reports/palmeraie2-creation-readiness-after.json`. Après correction : aucune erreur de base, aucun doublon exact, code proposé F10013 non réservé et non officiellement alloué ; creation_ready reste false. Les données ne sont pas déclarées prêtes à créer lorsque le mapping, les règles conditionnelles et la sécurité ne le permettent pas.

Tests dédiés : noms proches vs nom exact, conservation des blocages fiscaux et répétition sans nouveau brouillon. `reports/palmeraie2-targeted.xml` : 98 réussites. Régression complète : `reports/palmeraie2-full-regression.xml`. Frontend : `reports/palmeraie2-frontend.xml`, 28 tests réussis. Navigateur réel ordinateur/mobile, backend réel, SELECT uniquement : `reports/palmeraie2-live-browser.json`. Le même brouillon et les mêmes identifiants sont conservés après « créer le » ; aucune route d'approbation ou d'exécution appelée.

## Pourquoi aucune création réelle n'a été exécutée

Le contrôle TLS actuel échoue toujours sur `sage_crl_bundle_missing` ; le handshake avec la chaîne actuelle SAGE-CA-2 reste refusé. La politique d'exécution n'est pas validée, le profil AIAGT ADMIN doit être revu et les écritures restent désactivées. La demande « terminer la création » ne permet pas de contourner ces contrôles et ne constitue pas une approbation de paramètres encore non validés.

Action externe ciblée déjà préparée : `docs/DEMANDE-ADMIN-PKI-AIAGT-20261030.md`. Le responsable de SAGE-CA-2 doit fournir une CRL courante réellement signée et son processus de renouvellement. L'administrateur Sage doit valider les droits et l'identité métier du pool. Aucun mot de passe ni aucune clé privée ne doit être transmis.

Ensuite : lecture SOAP sous AIAGT/TEST, validation des paramètres et du code exact non réservé, présentation de la fiche complète, approbation spécifique, SAVE unique, relecture SOAP + SELECT et contrôle de l'activation. **Zéro création de DROGUERIE PALMERAIE 2 confirmée.** Ne pas déclarer le projet terminé.
