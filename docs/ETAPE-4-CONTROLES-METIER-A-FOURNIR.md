# Pièces de contrôle métier avant l'unique essai TEST

Aucune modification de droit ou de paramètre n'est demandée par cette liste. Il faut d'abord consulter/exporter l'existant.
Les droits d'administration Syracuse déjà constatés ne remplacent pas ces contrôles dans le dossier X3 TEST.
Les seules publications disponibles dans ce diagnostic ne permettent pas de lire toutes ces fiches, et les prototypes REST répondent 500.
Aucun export métier supplémentaire n'a été trouvé dans knowledge/documents ou config.

| Consultation dans TEST | Informations nécessaires | Pourquoi |
|---|---|---|
| GESAUS, utilisateur X3 réellement associé au pool | Compte actif, profil fonctions, autorisation Web Services, restrictions applicables | Identifier l'identité métier effective et son profil, pas uniquement le login HTTP/Syracuse |
| GESAFT et GESAFP pour ce profil | Accès à GESITM/objet ITM et autorisation de création, restrictions sociétés/sites/rôles/codes d'accès | Établir le droit effectif de créer; ne pas déduire ce droit du nom admin ou de CREATE dans getDescription |
| GESAWE, publication WS_ARTICLE | Objet, écrans/blocs, champs transmis, options et traitement généré | Confirmer que le mapping publié est compatible avec la création envisagée |
| GESITG, catégorie DIVE au niveau dossier et éventuelles déclinaisons pertinentes | Compteur produit et référence manuelle autorisée ou non, mode de création et statut initial | Garantir que le code demandé sera accepté sans création sous une autre référence |
| GESITG DIVE et paramétrage des groupes statistiques | Valeurs initiales, groupe FG autorisé au premier index, obligation éventuelle des index 2/3 | Les deux dernières positions sont vides dans le brouillon; ne pas supposer qu'elles sont facultatives |
| Paramètres d'unités et conversions applicables à DIVE | UN en stock/achat/vente, coefficients 1, paramètres de quantité | Distinguer les valeurs lues sur un ancien article des règles actuelles d'une nouvelle création |
| Règles de stock et de création de DIVE | Article non géré compatible, statut Élaboration accepté ou remplacé par défaut | Éviter d'imposer des valeurs incompatibles avec les règles de catégorie |
| Écrans et traitements spécifiques de l'objet ITM | Fournisseur XBPS obligatoire ou non, site, famille, fiscalité, comptes, autres contrôles conditionnels | La publication contient des champs personnalisés; l'indication Input ne prouve pas qu'un champ est facultatif |

Une capture/export validé par le responsable Sage peut être conservé dans un répertoire privé du projet avec date, dossier et provenance.
Ne pas inclure de mot de passe ni de clé privée. Ne pas publier les profils ou données sensibles dans un dépôt distant.
En l'absence de ces informations, le statut reste « non vérifié », pas « refusé » ni « autorisé ».

Après vérification, adapter le XML si nécessaire, recalculer les empreintes et présenter **les valeurs finales** à l'opérateur.
Toute modification du brouillon exige que la confirmation porte sur cette nouvelle version.
Aucun appel save à blanc : une validation distante par save pourrait réellement créer l'article.

Référence officielle : [autorisations fonctionnelles et profils](https://online-help.sagex3.com/erp/12/howtoguides/en-US/manufacturing/Mobile%20Automation-Manufacturing/Content/How-to%20guides/Manufacturing/Mobile%20Automation/T2_X3_Prerequisites.htm).
