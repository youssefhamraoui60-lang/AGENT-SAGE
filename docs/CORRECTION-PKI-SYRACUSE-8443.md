# Correction PKI de la connexion Syracuse existante 8443

Actualisation : le contrôle CRL est maintenant implémenté dans le connecteur 208 et attend les fichiers publics de production approuvés ; aucune collecte automatique sans endpoints approuvés. Le document opérationnel final est [ACTIONS-EXACTES-VM200.md](../logs/ACTIONS-EXACTES-VM200.md). Les mentions de chantier client ci-dessous décrivent le stade de préparation antérieur.

Procédure préparée le 24/10/2026. **Aucune étape de changement ci-dessous exécutée.** L'autorisation couvre les corrections locales sur 208 ; la PKI et tout changement actif sur 200 nécessitent un accord distinct et un créneau Europe/Paris.

## Décision PKI préalable — sans changement Syracuse

Transmettre au responsable PKI les deux empreintes DER et le rapport RAPPORT-ANALYSE-X509-SAGE.md. Faire choisir une chaîne organisationnelle approuvée et conforme. La feuille actuelle est sans AKI, la CA sans SKI ; un simple import de la CA actuelle ne suffit pas. Préférer une CA conforme existante à une reconstruction de la CA Sage partagée. Ne pas régénérer les certificats internes Syracuse/runtime ni remplacer globalement sagex3.

Faire fournir par la PKI, après une demande CSR selon son processus :

| Paramètre | Valeur / exigence |
|---|---|
| Destination | HTTPS Syracuse sur sage:8443 uniquement |
| Sujet | CN=sage, autres attributs selon politique PKI |
| SAN | DNS:sage ; un FQDN supplémentaire seulement après validation du DNS et besoin réel |
| Basic Constraints feuille | CA:FALSE |
| KU / EKU | Pour RSA : digitalSignature, keyEncipherment suivant politique ; EKU serverAuth |
| AKI feuille | Identifie la clé de l'émetteur ; cohérent avec son SKI |
| SKI des CA | Présent, contraintes CA/KeyUsage/pathLen conformes ; chaîne complète |
| Révocation | CDP et/ou OCSP opérationnels suivant politique ; publication, signature, fraîcheur, accessibilité depuis 208 vérifiées |
| Validité | Période approuvée ; pas de prolongation arbitraire jusqu'en 2036 |
| Clé privée | Générée et conservée dans le périmètre autorisé du serveur/gestionnaire PKI ; jamais transférée dans le projet agent ou le chat |

Les commandes de génération/émission dépendent de la PKI réelle et du lieu de conservation de la clé : ne pas inventer un nom de modèle AD CS, un serveur CA ou une URL CRL. Obtenir ces paramètres de l'administrateur. Un certificat contenant seulement un nom court peut être refusé par une CA publique ; utiliser la PKI interne approuvée ou convenir d'un FQDN et d'une migration explicite des URL.

Vérifier les fichiers **publics** reçus : certutil -dump, SHA-256 DER, correspondance sujet/SAN/usages/AKI/SKI, signatures, chaîne et révocation. Vérifier séparément la correspondance clé/certificat dans le périmètre sécurisé Syracuse. Ne pas importer une racine en confiance avant l'approbation PKI. La vérification stricte et le contrôle de révocation doivent réussir sans dérogation.

## Sauvegardes avant intervention sur 200

1. En RDP, consulter l'hôte sage et la ligne active 8443 dans Administration → Serveurs → Hôtes. Noter tous les champs actuels : Active, SSL, certificat serveur, authentification client, certificat client/CA éventuels ; conserver 8124 intégralement.
2. Identifier les consommateurs de l'hôte et le responsable d'exploitation ; fixer créneau, durée maximale d'indisponibilité et critères d'abandon. L'enregistrement d'une connexion active ou le changement de ses certificats peut redémarrer Syracuse : [documentation Hôtes Sage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_host.html).
3. Sauvegarder les exports de paramètres et la configuration réelle via le mécanisme existant ; le script sage_rdp_backup.ps1 peut copier des fichiers explicitement sélectionnés avec ACL et empreintes. Il ne remplace pas une sauvegarde Syracuse/MongoDB et des clés utilisable hors interface. Exiger une procédure d'exploitation de récupération testée si l'interface devient inaccessible.
4. Conserver la référence de l'ancien certificat et de sa clé dans le stockage sécurisé de l'exploitation ; ne pas supprimer ni écraser l'ancien objet. Ne pas joindre de sauvegardes contenant des secrets aux rapports.
5. Ne pas modifier pare-feu, ports, compte Windows du service, connexions internes, compte administrateur ou pool partagé dans cette intervention.

## Modification graphique — uniquement pendant la fenêtre approuvée

1. Administration → Certificats → Certificats des autorités de certification : ajouter **uniquement les objets de la chaîne approuvée**, sous de nouveaux identifiants autorisés, sans supprimer ni modifier les anciennes CA. Cette déclaration applicative ne remplace pas une décision de confiance client.
2. Administration → Certificats → Certificats : créer un **nouvel objet non interne**, candidat `sage_https_pki` si ce nom est libre. Nom en minuscules ; description HTTPS sage 8443 ; Server/Hôte **sage** pour éviter une distribution globale ; importer le certificat PEM, associer ses CA exactes. Fournir la clé correspondante et sa phrase secrète dans l'interface sécurisée selon le processus approuvé. Jamais dans une commande, un journal ou le projet 208. Les objets Internal ne sont pas éditables : ne pas forcer leur modification. [Champs officiels Sage](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/administration-reference_certificates.html).
3. Vérifier les contrôles de cohérence et la présence de clé de ce nouvel objet avant affectation ; si le processus ne permet pas un import conforme, arrêter et consulter l'administrateur Sage, sans toucher aux fichiers internes à l'aveugle.
4. Administration → Serveurs → Hôtes → sage → Connexions : **modifier la ligne 8443 existante**, conserver Active/SSL et les autres valeurs approuvées, affecter uniquement le nouveau certificat serveur. Ne pas ajouter une deuxième ligne 8443 ; ne pas modifier 8124.
5. Conserver l'authentification client TLS existante. Standard Syracuse pour AIAGT est une authentification applicative distincte de mTLS ; si mTLS est requis, préparer un certificat client approuvé séparément, ne pas décocher pour réussir.
6. Enregistrer pendant le créneau seulement, observer le rechargement attendu, ne pas enchaîner des redémarrages manuels. Ne pas redémarrer SQL Server ni le runtime X3.

## Vérifications après intervention

Sur 200, confirmer Syracuse et ses accès historiques avec l'exploitation. Sur 208, je pourrai exécuter sans secret en ligne de commande :

```powershell
curl.exe -4 -v --connect-timeout 5 --max-time 15 https://sage:8443/
curl.exe -4 -v --cacert C:\AGENT-SAGE-X3\certs\ca.cacrt --connect-timeout 5 --max-time 15 https://sage:8443/
```

Le chemin de bundle devra désigner **la nouvelle chaîne authentifiée** ; ne pas écraser ca.cacrt avec un fichier inconnu. Le premier test utilise la confiance Windows et sa révocation ; le second explicite le bundle. Un code HTTP de redirection ou authentification peut être normal après TLS, mais ne prouve pas SOAP. Aucun -k, aucune désactivation de révocation, aucun changement VERIFY_X509_STRICT.

Valider aussi avec Python strict : nom sage, dates, chaîne, usages, empreinte authentifiée. Requests ne contrôle pas automatiquement la révocation : le contrôle CRL/OCSP du transport reste un chantier à valider avec PKI (CRL signées actualisées et refus fermé, ou validation Windows approuvée). Ne pas assimiler un handshake Python à une validation de révocation.

Après ces contrôles, sous AIAGT : WSDL HTTPS, getDescription WS_ARTICLE/WS_FOURNIS/WS_AR_SITE (V12/TEST, utilisateur métier attendu), read CPJ35, query articles limité, consultation fournisseurs/articles-sites sur clés réellement connues. Vérifier FastAPI et React, absence de secrets et maintien HTTP 423. Aucune écriture incluse.

## Retour arrière dans la fenêtre

En cas d'échec TLS, indisponibilité ou régression : maintenir les écritures désactivées ; réaffecter **uniquement la ligne 8443** à son ancienne référence de certificat et aux paramètres sauvegardés ; accepter le rechargement prévu dans l'accord. Si l'interface est inaccessible, utiliser la procédure de récupération exploitation prévalidée, pas une édition MongoDB improvisée. Conserver 8124 et les certificats/CA historiques. Vérifier tous les consommateurs initiaux ; l'ancien certificat restaure l'état antérieur, mais **ne rend pas les écritures agent sûres**. Aucun repli HTTP pour écrire.

Un import de confiance éventuellement autorisé sur 208 doit avoir son empreinte et son magasin consignés, pour retirer seulement l'ajout concerné si nécessaire. Ne jamais supprimer des racines existantes partagées ni restaurer un ancien secret exposé.
