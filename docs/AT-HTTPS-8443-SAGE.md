# Demande ciblée AT-HTTPS-8443-SAGE

**Statut : à autoriser.** L’autorisation générale reçue le 24/10/2026 exclut explicitement les interventions susceptibles d’interrompre la production. AT-AIAGT est déjà autorisée ; aucune nouvelle autorisation générale de ce compte n’est demandée.

## Intervention proposée

Sur l’hôte Syracuse existant `sage` / 192.168.9.200 : ajouter une connexion **8443, Active=Oui, SSL=Oui**, utilisant le certificat existant **sage**, uniquement après validation de sa chaîne, de son usage, de sa clé et de ses empreintes par l’administrateur. Conserver la connexion HTTP **8124 inchangée**. URL agent après validation : **https://sage:8443**.

Aucune installation de logiciel ; aucun remplacement, suppression ou renouvellement de certificat ; aucun changement SQL Server, runtime X3, pare-feu, TrustedHosts, processus Web Services ou autre port inclus dans cet accord. Toute ACL nécessaire doit être identifiée et approuvée séparément. Une incompatibilité du certificat arrête l’intervention : elle n’autorise pas à le remplacer.

## Impact exact connu

L’enregistrement d’une connexion active peut provoquer un rechargement/redémarrage Syracuse. Tous les utilisateurs et intégrations desservis par cet hôte, y compris les dossiers de production, peuvent être momentanément interrompus. La durée n’a pas été mesurée et n’est pas garantie ; l’opérateur doit dimensionner la fenêtre. Aucun redémarrage de SQL Server ou du runtime V12 n’est proposé.

## Conditions et recette

- Administrateur Sage/système disposant d’un accès sécurisé au serveur 200. Les essais avec l’identité actuelle n’ont pas établi cet accès : WinRM refuse l’authentification et DCOM chiffré retourne 0x80070005. Aucun affaiblissement du client n’est proposé.
- Sauvegarde et export des paramètres existants, disponibilité locale de 8443 vérifiée avant changement, certificats publics authentifiés indépendamment, restrictions AIAGT examinées. Ne pas exporter de clé privée dans le projet agent.
- Après changement : listener 8443, TLS vérifiant nom `sage` et chaîne, WSDL et endpoint SOAP en HTTPS, getDescription/read sous AIAGT dans V12/TEST, contrôle des droits puis vérification des accès existants 8124 avec l’exploitation.
- Écritures agent désactivées pendant cette recette. Aucun save, modify ou delete inclus. L’activation technique ultérieure restera limitée à TEST et ne remplacera pas l’approbation d’une création précise.

## Retour arrière dans la même fenêtre

Garder les écritures désactivées ; retirer/désactiver seulement la connexion ajoutée ou restaurer les paramètres sauvegardés selon la procédure d’exploitation. Un second rechargement peut être nécessaire. Conserver 8124 et les certificats préexistants, vérifier les accès initiaux ; aucune compensation métier ni repli HTTP pour écrire.

Procédure complète : [ADMIN-02-MAINTENANCE-HTTPS-SYRACUSE.md](ADMIN-02-MAINTENANCE-HTTPS-SYRACUSE.md).

## Validation à fournir

Confirmer l’accord pour le périmètre ci-dessus, **la date et le créneau en Europe/Paris**, ainsi que l’administrateur qui dispose de l’accès au serveur et appliquera l’intervention. L’administrateur peut préparer AIAGT dès maintenant selon [ADMIN-01](ADMIN-01-AIAGT-TEST.md), depuis sa console locale autorisée ; aucun nouveau secret ne doit être transmis dans le chat ou en HTTP réseau.
