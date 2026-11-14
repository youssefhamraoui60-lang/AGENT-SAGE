# Correction minimale du certificat SQL — serveur Sage 192.168.9.200

**19 octobre 2026 — diagnostic et préparation seulement.** Aucun certificat/paramètre/service/compte/pare-feu modifié, aucun logiciel installé, aucune écriture SQL ou SOAP exécutée. L’autorisation reçue ne couvre que les vérifications de lecture et le plan.

## 1. Configuration réellement constatée

| Information | Source et résultat |
|---|---|
| Instance/port | Browser UDP 1434 annonce SAGE/SAGEX3, version 16.0.1000.6, TCP 1433 ; connexion TCP réussie |
| Nom DNS | Resolve-DnsName sage retourne une réponse A sage.local = 192.168.9.200 ; PTR de l’IP retourne sage. Cela ne valide pas à lui seul le FQDN système ni les alias employés par tous les clients |
| Certificat présenté sur 1433 | CN=SSL_Self_Signed_Fallback, même émetteur, aucun SAN, SHA256 **8A6717D1AB82E4279CC0895DE89E119880FE13ADAF39F0B56AB47AD64B2657F7** |
| Dates certificat | 14/10/2026 23:22:54 UTC → 14/10/2056 23:22:54 UTC |
| Observation TLS | PRELOGIN TDS et message Certificate observés, sans LOGIN7, aucun identifiant SQL ni batch transmis. Aucun certificat accepté comme digne de confiance |
| Force Encryption/Force Strict Encryption | **Non lus**, ne pas les déduire de la réponse PRELOGIN : le client avait lui-même demandé le chiffrement |
| Association locale Certificate dans SQL Configuration Manager/registre | **Non lue**, l’observation réseau prouve le certificat en cours de présentation, pas la valeur configurée |
| Certificats locaux réutilisables | **Non inventoriés actuellement**. La sortie utilisateur antérieure LocalMachine/My était vide, instantané historique seulement |
| Dépendances Sage et sessions SQL | **Non inventoriées** : pas de session système ni de session SQL authentifiée |

Sources locales : logs/sql-server-discovery.json ; logs/sql-tls-presented-certificate.json. Les annonces Browser sont non authentifiées ; elles ne remplacent pas SELECT SERVERPROPERTY après validation TLS.

## 2. Accès au serveur réellement essayé

TCP WinRM 5985 joignable ; 5986 non établi dans ce contrôle. `Get-CimInstance -ComputerName sage -ClassName Win32_OperatingSystem -OperationTimeoutSec 5` avec l’identité Windows actuelle échoue : le client exige Kerberos ou un transport/configuration de confiance adéquat. Preuve : logs/sql-server-remote-system-access.json.

**Aucun TrustedHosts ajouté, aucun Basic/non chiffré activé, aucune configuration WinRM changée et aucun identifiant SQL utilisé comme identifiant Windows.** L’adresse connue et le droit de diagnostiquer ne fournissent pas un accès système administrateur.

Inventaire local préparé : [inspect_sql_server_host_readonly.ps1](../scripts/inspect_sql_server_host_readonly.ps1). À exécuter uniquement dans une session autorisée sur 192.168.9.200, ou via un canal existant déjà authentifié si fourni. Il consulte le registre de l’instance, service/compte SQL, ports, dépendances Windows déclarées, métadonnées publiques des certificats et overrides Schannel, sans toucher aux clés privées. Il est vérifié syntaxiquement mais pas exécuté sur Sage.

## 3. Vérifications encore nécessaires avant choisir un certificat

1. Confirmer l’instance ID local, le compte de service MSSQL$SAGEX3, la valeur Certificate (empreinte Windows généralement SHA1), ForceEncryption/ForceStrictEncryption et les ports effectifs. Ne pas confondre cette empreinte de liaison avec le SHA256 de contrôle.
2. Inventorier LocalMachine/My et les éventuels certificats du compte service dans un accès autorisé. Vérifier dates, SAN, EKU serveur TLS, clé privée accessible au compte SQL, algorithme/fournisseur/KeySpec compatibles avec **la version exacte installée**. HasPrivateKey=True ne suffit pas.
3. Examiner le message de chargement du certificat dans SQL ERRORLOG, uniquement un extrait nettoyé autour du dernier démarrage ; aucun dump complet de journal ou de configuration sensible. Une valeur registre peut ne pas être chargée par le processus avant redémarrage.
4. Faire confirmer le nom système/FQDN et les noms réellement utilisés par les applications. Ne pas faire du PTR une source unique. Vérifier notamment sage et sage.local ; ajouter l’IP au SAN seulement si les consommateurs doivent réellement l’utiliser.
5. Inventorier la PKI existante : une CA interne nommée sagex3 et un certificat Syracuse sage ont été observés par HTTP, **pas approuvés hors bande**. Le certificat Syracuse observé couvre sage seulement ; ne pas supposer qu’il convient au FQDN, au fournisseur de clé SQL ou au compte service. Ne pas exporter sa clé ni l’affecter à SQL sans revue et accord.

Les exigences de certificat SQL dépendent de la version/fournisseur ; pour cette instance annoncée SQL 2022, vérifier particulièrement l’usage d’échange de clés, le fournisseur pris en charge et les droits de lecture du compte SQL. [Exigences Microsoft](https://learn.microsoft.com/mt-mt/sql/database-engine/configure-windows/certificate-requirements?view=sql-server-ver16).

## 4. Dépendances et risques de production

À inventorier avant arrêt : Sage X3 runtime V12 et ses connexions x3v12, traitements batch/imports, SQL Agent/jobs, reporting/intégrations, sauvegardes, outils administrateurs et autres bases/consommateurs de **la même instance**. Les services nommés V12, SQLAgent$SAGEX3 et Syracuse ont été vus dans les sorties utilisateur ; leurs relations effectives SQL ne sont pas toutes prouvées. Syracuse utilise aussi ses propres composants : ne pas conclure qu’une dépendance Windows déclarée représente toute la chaîne métier.

Le DBA peut consulter, avec un compte autorisé, les sessions/programmes/hôtes actifs et les jobs en cours de façon limitée ; le compte agent db_datareader n’est pas présumé autorisé aux vues serveur. Aucun changement de permission pour obtenir ces données n’est proposé ici. Les chaînes de connexion relevées doivent être nettoyées avant partage ; préférer une liste de noms d’hôtes/clients/pilotes.

Un redémarrage SQL coupe les connexions de l’instance entière, pas seulement TEST. Risques : interruption des sessions Sage, traitements en cours en échec/rollback, délais de récupération, reconnections impossibles avec un ancien client, ou démarrage SQL impossible si la clé/certificat est inaccessible. Ne pas promettre zéro interruption ni compatibilité Sage simplement à partir du nom du produit.

## 5. Solution minimale proposée — pas d’auto-signé arbitraire

**Réutiliser un certificat existant seulement s’il satisfait tous les critères et si son usage SQL est approuvé.** À défaut, demander à l’autorité interne déjà administrée un certificat dédié SQL, sans créer de nouvelle CA ou certificat auto-signé ad hoc.

Profil à faire approuver : identité du serveur/FQDN réel, SAN sage et sage.local si ces deux noms sont effectivement employés, autres alias réellement nécessaires seulement ; EKU Server Authentication, validité et algorithmes conformes, clé/fournisseur/KeySpec compatibles SQL 2022 et droits minimaux pour le compte de service. Le nom DNS de la connexion agent doit être présent dans le SAN.

La CA et la chaîne sont confirmées hors bande. Distribuer **seulement les certificats CA publics vérifiés** aux consommateurs qui en ont besoin. La clé privée reste sur le serveur sous ACL restreinte ; aucune clé ou PFX dans le chat ou le dépôt. Ne pas réutiliser le certificat fallback comme CA de confiance générale.

### Changements exacts, à autoriser après inventaire

| ID | Changement prévu | Ce qui reste inchangé |
|---|---|---|
| C1 | Si aucun certificat utilisable : émission par la PKI existante, installation certificat/clé SQL dédiés dans le magasin approprié ; sinon réutilisation approuvée | Aucun remplacement du certificat Syracuse, aucune nouvelle CA arbitraire |
| C2 | Donner au **compte exact du service SQL** la lecture de la seule clé sélectionnée, sans permission large | Compte SQL et comptes administrateurs non modifiés, autres ACL intactes |
| C3 | Sélectionner ce certificat pour SAGEX3 avec SQL Server Configuration Manager existant et relever la nouvelle association | Port 1433, protocoles, pare-feu et Force Encryption/Force Strict Encryption conservés à leurs valeurs initiales |
| C4 | Faire confiance à la chaîne publique vérifiée sur les clients concernés après revue ; agent configuré Encrypt=True/TrustServerCertificate=False avec nom DNS couvert | Aucun contournement de certificat, aucun secret dans React |
| C5 | **Un redémarrage planifié de MSSQL$SAGEX3**, avec procédure applicative et durée arrêt/reprise approuvées | Pas de redémarrage Windows/Syracuse/service Sage automatique, pas de Restart-Service -Force global |

Le modèle d’autorisation final doit contenir l’empreinte du **certificat choisi**, SAN, compte service, état initial sauvegardé, fenêtre, responsables et consommateurs testés. Ces informations ne sont pas encore disponibles : **la liste ci-dessus est un périmètre proposé, pas un ordre d’exécution complet ni une autorisation acquise**.

## 6. Redémarrage : oui, à planifier

Pour charger le nouveau certificat SQL de manière prise en charge, prévoir un redémarrage du service SQL Server. Il n’est pas nécessaire de changer Force Encryption pour exiger une connexion chiffrée côté agent ; laisser cette option inchangée évite une extension de portée à tous les clients. Les étapes et risques de droits de clé sont documentés par [Microsoft](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/configure-sql-server-encryption?view=sql-server-ver16).

Si **aucune interruption de l’instance** n’est acceptable, ne pas appliquer la correction serveur maintenant. La piste cliente de comparaison exacte du certificat, après confirmation indépendante et approbation, reste une option séparée sans modification serveur ; ce n’est pas la correction CA/DNS demandée ici et elle n’est pas activée.

## 7. Sauvegarde avant toute modification autorisée

- Faire confirmer par le DBA des sauvegardes existantes récentes/restaurables et la couverture des journaux selon la politique ; ne pas lancer une sauvegarde lourde en production sans plan et autorisation. Le changement TLS ne modifie pas les tables, mais la fenêtre d’arrêt doit être maîtrisée.
- Capturer/exporter en emplacement administrateur protégé les seuls paramètres d’instance concernés : instance ID, association Certificate, présence/absence et valeur exacte des options de chiffrement/ports, état/compte/dépendances de service. Une valeur absente doit être distinguée d’une valeur 0.
- Conserver les empreintes/publics et ACL précédents. Ne pas exporter systématiquement une clé privée partagée ; si une sauvegarde de clé est nécessaire, suivre la politique PKI avec stockage chiffré et accès contrôlé.
- Relever les connexions clients/pilotes, chaîne de confiance et état applicatif de référence ; prévoir l’accès console administrateur/Configuration Manager nécessaire si SQL ne redémarre pas.
- Ne pas confondre ce certificat TLS avec les certificats TDE ou de chiffrement de sauvegarde en base. Aucun CREATE CERTIFICATE T-SQL ni modification de clés TDE.

## 8. Retour arrière ciblé

1. Si un contrôle préalable échoue, ne pas changer la liaison et ne pas redémarrer.
2. Si démarrage ou recette échoue après bascule, suspendre la reprise des utilisateurs et restaurer via le moyen administrateur approuvé l’association **initiale exacte** et uniquement les permissions/paramètres modifiés. Si elle était absente, rétablir l’absence ; ne pas choisir arbitrairement une empreinte de fallback qui n’existait pas en configuration.
3. Redémarrer de nouveau **la seule instance SAGEX3** dans la fenêtre prévue. C’est une deuxième interruption possible, à inclure dans la durée et l’accord.
4. Contrôler l’état SQL et les consommateurs habituels. Revenir au comportement antérieur ne constitue pas une validation de sécurité ; les nouvelles lectures agent restent désactivées si TLS n’est pas validé.
5. Conserver les journaux/preuves ; ne pas supprimer l’ancien certificat ni la clé partagée, ne pas révoquer une CA, ne pas désactiver la vérification du certificat en activant TrustServerCertificate pour masquer l’erreur. Un fallback peut être régénéré au redémarrage : un éventuel pin doit être revérifié, jamais réappris automatiquement.

## 9. Recette après correction autorisée

1. Relever le certificat effectivement présenté après redémarrage : empreinte attendue, SAN, dates et chaîne. Confirmer le journal de chargement SQL par un accès administrateur.
2. Tester une vraie connexion agent avec nom couvert, chiffrement obligatoire et TrustServerCertificate=False ; mauvais nom ou CA non approuvée doit être refusé. Ne pas faire une modification négative sur le serveur de production pour ce test.
3. Confirmer instance/base/login par SELECT, puis rôle db_datareader et droits cumulés. Pour la session test, examiner encrypt_option si le compte possède déjà le droit nécessaire, sinon faire vérifier par le DBA, sans élargir les permissions du compte agent.
4. SELECT paramétrés bornés sur les métadonnées TEST puis une fiche ITMMASTER/ITMFACILIT ; comparer aux valeurs SOAP et aux traductions, sans DML.
5. Faire valider par les responsables Sage la connexion d’un poste, lecture fiche, fonctionnement des pools/runtime, jobs/reporting et intégrations habituellement actifs. Pas de création/modification métier de production comme recette implicite.
6. Observer erreurs de connexion/reprise et performances pendant une période convenue. Ne pas déclarer la compatibilité Sage validée tant que ces consommateurs n’ont pas été testés.

## 10. Décision demandée à ce stade

Le diagnostic distant est terminé ; il reste à obtenir l’inventaire local via un accès Windows autorisé ou un export administrateur. **Ne pas approuver encore un remplacement avec un certificat non choisi.** Après revue de ces pièces, présenter une demande technique distincte pour C1–C5, avec empreinte finale, ACL, fenêtre et retour arrière. Aucune création SOAP ou écriture SQL n’est incluse dans ce futur accord technique.
