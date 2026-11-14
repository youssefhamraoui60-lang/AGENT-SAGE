# Quatre créations TEST — méthodes disponibles et accords séparés

Analyse réelle du 19 octobre 2026. Aucun appel d’écriture exécuté, aucun droit ou paramètre serveur modifié. Choix des raisons sociales délégué par l’utilisateur : FOURNISSEUR TEST IA et CLIENT TEST IA. Ce choix n’est pas un accord de création.

## Méthodes métier examinées

| Méthode | Support officiel | État de l’installation testé | Exécution depuis FastAPI et conditions |
|---|---|---|---|
| SOAP save d’objet publié | Sage X3 SOAP, objets et mapping publiés | WS_ARTICLE/ITM, WS_AR_SITE/ITF, WS_FOURNIS/BPS décrits dans TEST et présents dans AWEBSERVIC ; aucun BPC trouvé | Connecteurs et approbations existants pour ces trois objets. Bloqués par le gate de sécurité actuel ; jamais ajouter save à la liste blanche de lecture |
| Import natif associé à un objet | GESAOE, contrôle métier de l’objet | Modèles BPC/GESBPC, BPS/GESBPS et ITM/ITMA/GESITM réellement présents dans TEST | Utilisable depuis l’agent seulement avec un canal Sage autorisé, droits d’import et mapping validé ; le seul SELECT SQL du modèle ne l’exécute pas |
| Import automatisé SOAP AOWSIMPORT | Sous-programme IMPORT appelé par le service SOAP run | getDescription renvoie statut 0, « Service web inexistant » ; aucune ligne correspondante trouvée dans le périmètre AWEBSERVIC testé | Non opérationnel ici. Publication/configuration et adaptateur ciblé FastAPI nécessaires, après autorisation ; même sécurité et approbation, pas de run générique libre |
| API métier REST | Dépend d’une classe/représentation réellement publiée et des droits | GET catalogue V12_TEST HTTP 400 ; prototypes ITM/BPC HTTP 500. Aucun POST testé | Aucune API de création REST validée pour ces objets ; les erreurs de métadonnées ne prouvent pas une panne SOAP. Ne pas inventer un endpoint de création |
| Traitement/batch Sage autorisé | Import batch ou traitement métier documenté et installé | Aucun canal de déclenchement batch authentifié, périmétré et validé établi depuis cette session | Pas de lancement OS/RPC ou dépôt de fichier serveur présumé possible. Nécessite droits, destination TEST, compte rendu de traitement et approbation spécifique |
| INSERT/UPDATE SQL ou procédure non validée | Non retenu | Compte db_datareader, DML refusé sur les quatre tables | Explicitement exclu ; ni ajout de droits ni procédure SQL arbitraire pour remplacer les contrôles Sage |

Sources officielles : [modèles d’import et contrôles objets](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAOE.htm), [API d’import/export et AOWSIMPORT](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/api-guide_api-soap-import-export.html).

### Points d’attention pour l’import natif

- Employer seulement un modèle rattaché à l’objet et à sa fonction métier. Exclure l’import de table sans objet et les traitements spécifiques non examinés : ils ne garantissent pas les validations souhaitées.
- Les modèles BPC/BPS/ITM/ITMA relevés ont ENAFLG=2, IMPORT=2, ENAWRK=2, OPTSPE=1 et fonction métier correspondante. Les codes, détails de format et champs sont conservés dans four-creation-sql-discovery.json. Confirmer leur sémantique dans GESAOE et le dictionnaire de cette installation, pas à partir d’une convention seule.
- **OPTUPD=2 est relevé sur ces modèles** : leur possibilité de mise à jour doit être examinée. Aucun fichier ne sera exécuté si une collision peut transformer silencieusement une création en modification. Ne pas modifier le modèle standard ou partagé pour contourner ce risque ; proposer, si nécessaire et après accord, une copie dédiée en création seule avec toutes les validations.
- Les règles workflow/contrôles doivent rester actives. Le mode de stockage temporaire n’est pas une simulation garantie sans écriture. Aucun import « à blanc » exécuté.
- Les lignes de modèle AOBJEXTD ont été lues avec leurs indicateurs SEL/OBL, formats et ordre. Elles n’établissent pas à elles seules tous les champs conditionnels, ni l’adresse requise d’un tiers. Aucun fichier d’import client prétendument complet n’est fabriqué avec une adresse/taxe/identifiant inventé.
- Si le mode batch est retenu, conserver numéro de requête et statut terminal métier ; une acceptation de demande ne prouve pas une création. Contrôler SQL avant tout nouvel envoi.

## Plan d’exécution proposé

1. Choisir la voie : SOAP save pour ITM/ITF/BPS ; pour BPC, soit publier un objet BPC autorisé, soit rendre opérationnel AOWSIMPORT avec un modèle métier revu. Aucun de ces changements serveur n’est autorisé par la présente préparation.
2. Valider le transport et l’identité technique, les droits TEST et règles conditionnelles, puis les preuves locales. Le mode SQL TMS demandé antérieurement ne lève pas l’exigence SOAP du gate. Pas d’activation globale pour faire disparaître HTTP 423.
3. Recontrôler SQL et read SOAP juste avant chaque opération. Refaire les préparations après un changement d’identité/mapping/publication. Présenter les nouveaux UUID/digests, valeurs et dépendances ; enregistrer un accord par opération.
4. Exécuter l’article une fois via FastAPI. Conserver réponse SOAP complète, code et messages. Read Sage puis SELECT SQL exact ; comparer la désignation, NEG, unités UN et champs réellement initialisés.
5. Rechercher ITF AITEST001/201 après création article. Si généré automatiquement, déclarer EXISTANT avec preuve et ne pas envoyer save. Sinon, valider les droits site, repréparer et demander son propre accord avant une tentative.
6. Créer le fournisseur une fois après accord spécifique ; read BPS et SELECT BPSUPPLIER/BPARTNER, comparaison des données métier.
7. Pour le client, uniquement après canal autorisé disponible, mapper et compléter les champs manquants, soumettre le jeu final et demander son propre accord. Une exécution, log/résultat métier, puis SQL BPCUSTOMER/BPARTNER et relecture Sage via un service ou écran autorisé.
8. Si réponse ambiguë : ne pas relancer automatiquement. Contrôler l’existence par clé et rapprocher les journaux avant toute autre décision humaine. Pas de suppression ni de rollback métier automatique.

## Quatre demandes d’accord — NON accordées, NON exécutables en l’état

Ces fiches servent à la revue. Aucun accord d’écriture n’a été sollicité/délivré côté serveur pendant le diagnostic. Tant que les prérequis ne sont pas satisfaits, **ne pas créer de jeton d’approbation** : il serait refusé par le gate et ne remplacerait pas les preuves de sécurité.

### C1 — Article

- Clé AITEST001 ; désignation **ARTICLE TEST CREATION API SAGE X3** ; catégorie NEG ; unités stock/achat/vente UN ; coefficients 1.
- Valeurs issues de la catégorie : STOMGTCOD=2, LOTMGTCOD=1. Les autres valeurs requises seront initialisées par Sage ou complétées seulement après validation ; pas de code comptable CPJ35 repris arbitrairement.
- Méthode prévue : WS_ARTICLE / save, V12/TEST, POOL_AI_TEST. Code absent SQL et SOAP lors de la préparation.
- Accord à demander une fois prêt : « Autorisez-vous une seule création de AITEST001 dans TEST via FastAPI/WS_ARTICLE, sur l’UUID/digest final et les données affichées ? »

### C2 — Article-site

- Clés AITEST001 / 201. Catégorie ABC proposée 1, selon la catégorie NEG ; autres paramètres dépendants des défauts et contrôles Sage à revoir.
- Site 201 présent dans TEST, société 20 ; existence du site ne prouve pas l’autorisation applicative de création.
- Méthode prévue : WS_AR_SITE / save. Seulement après existence ITM confirmée et absence ITF recontrôlée.
- Accord à demander une fois prêt : « Autorisez-vous une seule création de AITEST001 / 201 dans TEST via FastAPI/WS_AR_SITE, si la fiche est toujours absente, sur l’UUID/digest final ? »

### C3 — Fournisseur

- Clé F_AITEST01 ; raison sociale **FOURNISSEUR TEST IA** ; catégorie FR ; pays MA ; langue FRA ; devise MAD.
- Défauts observés de FR : ACCCOD STD, VACBPR MAR, PTE CHQ00. Ces valeurs sont dans le XML préparé ; leur acceptation conditionnelle reste à vérifier. Les adresses et autres champs éventuellement requis ne sont pas inventés.
- Méthode prévue : WS_FOURNIS / save. Absence vérifiée dans BPSUPPLIER et BPARTNER ; absence SOAP également obtenue à la préparation.
- Accord à demander une fois prêt : « Autorisez-vous une seule création de F_AITEST01 dans TEST via FastAPI/WS_FOURNIS, sur l’UUID/digest final et toutes les données affichées ? »

### C4 — Client

- Clé C_AITEST01 ; raison sociale **CLIENT TEST IA** ; catégorie CL ; pays MA ; langue FRA ; devise MAD.
- Défauts observés de CL : ACCCOD STD, VACBPR MAR, PTE CHQ00. Adresses et autres obligations à déterminer, pas de données réelles d’un autre tiers copiées.
- Méthode non sélectionnée définitivement : modèle natif BPC constaté, mais AOWSIMPORT inexistant dans le contexte testé ; pas de publication BPC SOAP disponible. Aucun fichier final exécutable ni UUID d’écriture client validé.
- Accord à demander seulement après sélection de la méthode et préparation complète : « Autorisez-vous une seule création de C_AITEST01 dans TEST, avec la méthode métier explicitement retenue et le jeu final affiché ? »

## Impact et actions nécessaires, sans application

- Transport SOAP conforme au gate et compte technique/droits : encore bloquants. Aucun service, certificat, port ou pare-feu changé ; le compte SQL reste en lecture seule.
- Publication BPC ou AOWSIMPORT : configuration Sage à faire examiner par l’administrateur, avec droits/règles et impact sur les consommateurs. Pas de publication automatique ni de traitement arbitraire.
- Modèle d’import création seule si nécessaire : proposition séparée, ne pas altérer un modèle partagé utilisé en production. Toute modification exige autorisation spécifique, sauvegarde du paramétrage et retour arrière ciblé.
- Avant exécution réelle, finaliser les éventuels champs obligatoires manquants avec des informations de test approuvées et vérifier la conservation du résultat. Sans ces éléments, le statut reste BLOQUÉ.

Le [rapport principal](../logs/TEST-CREATION-SAGE-X3.md) présente les preuves SQL/SOAP et le tableau de statut. Aucun test réel d’écriture ne sera déclaré réussi sur la base de cette préparation.
