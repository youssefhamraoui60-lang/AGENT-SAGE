# Intervention 2 — maintenance HTTPS native Syracuse

Préparation du 24/10/2026. **Non appliquée. Autorisation technique AT-HTTPS et fenêtre de maintenance requises.** Pas d’installation de logiciel. Référence de départ : SOAP-SAVE-INTERVENTIONS-INDISPENSABLES.md ; aucune répétition du diagnostic historique.

## Avant la fenêtre : décision et sauvegarde

Renseigner opérateur, responsable exploitation, date/heures en **Europe/Paris**, durée et critère d’abandon. Inventorier les utilisateurs/intégrations concernés. Obtenir l’accord couvrant le rechargement/redémarrage éventuel de Syracuse et le retour arrière : enregistrer une connexion active peut le provoquer, même sans commande Restart-Service. [Documentation Hôtes](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).

L’administrateur conserve dans son stockage sécurisé approuvé : export/captures des lignes Connections, références et métadonnées des certificats/CA, paramètres d’hôte et sauvegarde Syracuse selon sa procédure existante. Noter l’état et les paramètres 8124 ainsi que les accès applicatifs de référence. Les sauvegardes pouvant contenir des secrets restent protégées sur le périmètre d’exploitation ; aucune clé privée à copier dans le projet agent ou le chat.

Vérifier uniquement les préconditions de changement : 8443 toujours libre localement, sauvegarde exploitable, identité AIAGT préparée, filtrage du nouveau flux approuvé. Ne pas activer globalement le pare-feu Windows. Si une nouvelle ACL est nécessaire, obtenir son autorisation distincte et son retour arrière ; une règle Allow n’assure pas un filtrage quand le pare-feu est désactivé.

## Certificat et confiance — critères bloquants

| Élément | Valeur candidate / validation nécessaire |
|---|---|
| Certificat Syracuse | sage, existant ; ne pas le remplacer ni le régénérer pour cet essai |
| SHA-256 DER serveur historique | 8EA053B47994C560E9C094FA79635FE3A7238144148F43C9C998BD8986D03ED9 |
| SHA-256 DER CA historique | D2CA116411F5A3E6CF09AA661330CBB45E92B99B40BDEFB9E1D316E76A080F4F |
| Nom vérifié | sage ; SAN DNS=sage |
| URL | https://sage:8443 |
| Validité historique | Fin 24/02/2036 ; vérifier aussi début de validité et horloge actuelle |
| Chaîne | Signatures, contraintes CA, intermédiaires et usages compatibles TLS serveur ; absence de révocation ou état non vérifiable explicitement traité selon la politique |
| Clé privée | Présente, correspond au certificat, accessible au compte Syracuse selon les droits prévus ; ne pas l’exporter vers l’agent |

Confirmer ces empreintes depuis le serveur ou une source administrative indépendante : les copies publiques précédemment obtenues par HTTP ne sont pas une attestation d’authenticité. Comparer des empreintes **DER du certificat**, pas le hash du fichier PEM. Contrôler la chaîne avec les certificats publics de l’autorité et les outils approuvés ; ne pas installer une CA inconnue dans Windows pour faire disparaître une erreur. La vérification des signatures seule ne démontre ni la confiance ni la révocation.

Utiliser `sage`, pas l’IP ni `sage.local` avec le SAN constaté. Si le certificat/chaîne/clé n’est pas utilisable : arrêter ici et soumettre une demande séparée au responsable PKI ; aucun certificat auto-signé improvisé.

## Changement après autorisation uniquement

Sur la page Syracuse **Hôtes / Hosts**, représentation `host`, hôte `sage`, tableau **Connexions / Connections** :

| Champ | Changement autorisé à prévoir |
|---|---|
| Ligne HTTP existante 8124 | Conserver port, état et paramètres |
| Nouvelle ligne Port | 8443 |
| Active | Oui pendant la fenêtre autorisée |
| SSL | Oui |
| Server certificate | sage, seulement après la validation ci-dessus |
| Client authentication / Client certificate | Selon la politique approuvée ; ne pas désactiver une exigence mTLS. Si mTLS imposé, arrêter pour préparer le client adéquat |
| Autres paramètres de l’hôte | Aucun changement : processus, runtimes, tags et répartition inchangés |

Enregistrer uniquement pendant la fenêtre. Observer le rechargement et le retour du service, sans lancer des redémarrages supplémentaires à répétition. La conservation de 8124 évite de modifier les URL existantes, mais ne garantit pas l’absence d’interruption : Syracuse est partagé avec la production.

## Recette après changement

1. Sur le serveur, constater le listener 8443, le retour opérationnel de Syracuse et de 8124 ; vérifier les accès applicatifs de référence avec le responsable exploitation.
2. Depuis 208, valider une connexion TLS vers `sage:8443` avec vérification normale du nom et de la chaîne, TLS 1.2 minimum selon la politique approuvée, sans verify=False/-k. Enregistrer version TLS, certificat présenté et SHA-256 ; comparer aux éléments authentifiés. Aucune redirection vers HTTP admise.
3. Sur l’agent, configurer seulement après accord l’URL HTTPS, le bundle public vérifié si requis, l’identité AIAGT et l’alias retenu. Garder **SAGE_WRITES_ENABLED=false**. Le connecteur prend déjà en charge SAGE_SOAP_CA_BUNDLE ; aucune installation de CA globale nécessaire par défaut.
4. Charger le WSDL HTTPS et vérifier que le connecteur cible aussi l’endpoint SOAP HTTPS, puis getDescription/read sous AIAGT : V12/TEST, ITM/ITF, USER=AIAGT. Une réponse HTTP 200 seule ne vaut pas succès métier.
5. Faire les tests positifs et négatifs du document ADMIN-01-AIAGT-TEST.md. La confirmation de la configuration de C reste distincte de son exercice réel.
6. Si un filtrage source fait partie de l’autorisation : 208 doit passer ; vérifier le refus depuis un poste de test autorisé non admis. Aucun résultat négatif revendiqué sans ce contrôle ou preuve d’exploitation équivalente.
7. Vérifier les sessions et intégrations existantes avec l’exploitation ; relever les seuls événements utiles et masquer Authorization, cookies et secrets.

Arrêter la recette si confiance, nom, identité, dossier, droits ou fonctionnement existant sont incorrects. Ne pas revenir automatiquement à HTTP pour une écriture et ne pas ouvrir plus largement le réseau pour réussir le test.

## Retour arrière

Déclencheurs : indisponibilité persistante, régression d’un accès existant, certificat non conforme ou périmètre d’accès incorrect. L’opérateur applique le retour arrière autorisé dans la fenêtre :

1. Garder/désactiver les écritures de l’agent et arrêter toute demande d’exécution ; aucune compensation métier.
2. Désactiver/retirer seulement la nouvelle connexion 8443 ou rétablir l’export préalable selon la procédure d’exploitation. Prévoir un nouveau rechargement. Conserver la ligne 8124 et les certificats préexistants.
3. Rétablir seulement les paramètres agent sauvegardés, écritures toujours désactivées ; ne pas restaurer un secret exposé. Annuler uniquement la nouvelle règle réseau si elle avait fait l’objet d’un accord et d’un identifiant précis.
4. Confirmer le fonctionnement initial avec l’exploitation ; conserver les traces et l’horaire. Aucune succession de redémarrages ou modification générale des certificats.

**Périmètre d’accord AT-HTTPS à confirmer :** hôte sage, ajout 8443/SSL/certificat validé, conservation 8124, impact partagé et fenêtre de rechargement acceptés, opérateur et retour arrière identifiés. Les changements de certificat ou de filtrage non explicitement listés restent hors accord. Aucune création d’article autorisée par cet accord.

## Passage au test réel unique

Après AIAGT et HTTPS validés, renseigner les preuves réelles et leurs empreintes dans une politique datée limitée à TEST ; ne pas activer le fichier exemple inactif. L’activation technique des écritures demande un accord distinct si elle n’est pas incluse explicitement dans un accord ultérieur.

Préparer alors un nouveau code absent, sa désignation, sa catégorie, ses unités et les champs conditionnels revus ; présenter XML, dossier, clé, UUID/digest de préparation et durée d’approbation. Demander **un accord métier spécifique**. Après cet accord seulement : une tentative FastAPI → SOAP save ; conserver statut/messages, read et comparaison, SELECT SQL paramétré TEST et affichage React. Si réponse ambiguë : read/SELECT seulement, aucun retry automatique. Une création article-site serait une autre opération, non incluse dans cet essai ITM unique.
