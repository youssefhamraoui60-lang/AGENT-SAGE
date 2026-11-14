# Analyse SQL et documentation Sage — 21 octobre 2026

Intervention en lecture seule. Preuves datées : logs/SQL-ISOLATED-PREREQUISITES.json. Aucune écriture Sage ni modification serveur.

## Constat supplémentaire réel

L’article de référence TSTAI2610174D94B4 existe dans TEST.ITMMASTER **et TEST.ITMSALES**. Aucune ligne retournée pour ce code dans ITMFACILIT, ITMBPS ou ITMBPC. Cela décrit cet exemple seulement : toutes les tables possibles n’ont pas été vérifiées.

Colonnes observées, toutes non nullables : ITMMASTER 232 ; ITMFACILIT 195 ; ITMSALES 36 ; BPARTNER 82 ; BPSUPPLIER 287 ; BPCUSTOMER 209. Chaque table a une colonne identité et un défaut SQL visibles dans la requête de métadonnées. Le nombre de colonnes non nullables ne signifie pas que l’utilisateur doit saisir autant de champs : Sage initialise des valeurs, dont certaines peuvent être vides ou zéro. Les valeurs valides ne se déduisent pas de la seule nullabilité.

Les tables liées ITMSALES, ITMBPS, ITMBPC, ATEXTRA, GACCCODE, ITMCATEG et TABUNIT ont été trouvées dans TEST. Leur présence ne rend pas chacune obligatoire pour tout article.

## Documentation officielle consultée

- [Import articles achetés ITMA](https://online-help.sagex3.com/erp/12/en-us/Content/OBJ/AOE_ITMA.htm) : catégorie TCLCOD, code ITMREF et désignation DES1AXX obligatoires dans le modèle ; unités, coefficients, code comptable et niveau de taxe peuvent être nécessaires selon les défauts de catégorie. Pour un article vendu, unité de vente et coefficient doivent être déterminés.
- [Modèles d’import](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAOE.htm) : un objet peut regrouper plusieurs tables et ses contrôles/actions sont exécutés par l’import objet. Cette garantie ne s’applique pas à une copie SQL arbitraire.
- [Dictionnaire ITMMASTER](https://online-help.sagex3.com/erp/12/fr-fr/Content/MCD/ITMMASTER.htm) : clés et liens vers les référentiels, notamment le code comptable.

## Conséquence pour la préparation

L’analyse ne s’arrête plus aux seules tables maître/site : l’exemple créé par SOAP a aussi une ligne ventes. Une copie d’ITMMASTER seule ne reproduirait pas même les lignes déjà observées de cet exemple.

Pour AITEST001, catégorie NEG et unités UN restent proposées. Le niveau de taxe, le code comptable et les obligations conditionnelles doivent être résolus à partir du paramétrage TEST, sans recopier arbitrairement CPJ35 ni inventer des valeurs. La description d’un modèle d’import n’est pas une spécification exhaustive d’INSERT physiques ou des spécifiques locaux.

Une création réellement validée doit utiliser l’objet ITM publié ou l’import métier ITMA autorisé. Les blocages d’accès de ces canaux restent indépendants de la lecture SQL ; aucune preuve ni autorisation fictive ajoutée. Aucune insertion exécutée dans cette analyse.
