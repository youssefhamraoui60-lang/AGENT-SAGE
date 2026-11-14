# Dossier de décision technique — trois Web Services TEST

La dernière demande autorise diagnostics et préparation, **pas l’installation, les changements de configuration ni les écritures métier**. Aucun des changements ci-dessous n’est appliqué.

## Changements soumis à décision

| ID | Changement précis proposé | Risques / condition d’arrêt | Retour arrière |
|---|---|---|---|
| T1 | Installer un relais stunnel indépendant sur le serveur Sage 192.168.9.200, après inventaire local et validation du paquet. Écoute proposée 192.168.9.200:8443, amont exclusif 127.0.0.1:8124. Modèle config/stunnel-sage-test.NOT-APPLIED.conf. | Nouveau processus, ressources et logiciel à maintenir. Port libre et compatibilité OS non encore confirmés. Si une adaptation Syracuse est nécessaire, arrêter et demander une nouvelle décision. Aucun redémarrage Syracuse prévu. | Arrêter le seul PID/chemin du pilote ; conserver les journaux ; laisser 8124 et les services existants intacts. Pas d’arrêt global de stunnel. |
| T2 | Certificat dédié pour le relais, SAN sage ou FQDN approuvé ; chaîne et usage serveur vérifiés, clé exclusivement sur le serveur et ACL pour son compte système dédié. CA publique confirmée hors bande, bundle limité au client agent. | Mauvais nom, chaîne incomplète, expiration, clé mal protégée. Aucun export automatique de la clé Syracuse existante, aucun import global de confiance. | Retirer le certificat du seul relais et revenir au bundle précédent de l’agent. Ne pas révoquer une CA/certificat partagé. |
| T3 | Autoriser uniquement TCP de 192.168.9.208 vers 192.168.9.200:8443, règle proposée AGENT-SAGE-X3-TEST-TLS-8443. Vérifier les règles effectives larges avant lancement. | Une règle Allow limitée ne restreint pas une règle Allow existante plus large. Ne pas modifier des règles partagées sans décision supplémentaire. Aucun changement sortant présumé nécessaire. | Retirer uniquement la nouvelle règle si créée et identifiée ; aucune suppression de règle existante. |
| T4 | Créer une identité Syracuse et une identité X3 techniques sans rôle administrateur, accessibles au seul dossier TEST. Droits lecture/création ITM, BPS, ITF ; modification distincte après revue, pas suppression. Valider noms selon limites locales. | Droit trop large, accès indirect à un autre pool, consommateur existant affecté par changement d’identité. Vérifier profils/options, endpoint et restrictions ; aucun droit admin ajouté. | Désactiver uniquement les nouvelles identités après contrôle de leurs usages. Aucune suppression de données métier ni modification d’un compte partagé. |
| T5 | Affecter le compte au pool TEST après inventaire des consommateurs. Si POOL_AI_TEST est partagé, proposer séparément un pool TEST dédié plutôt que le modifier. | Recyclage de canaux et interruption possible du pool. Cette action n’est pas assimilée à une installation sans impact. L’alias exact doit être approuvé ; aucune création de pool automatique. | Rétablir l’association sauvegardée seulement dans le périmètre autorisé ; désactiver le nouveau pool s’il était dédié. Respecter la rotation des secrets, ne pas réintroduire un secret exposé. |
| T6 | Configurer le seul backend agent vers l’URL HTTPS validée, les nouveaux secrets locaux, bundle CA et preuves privées de droits/règles. Garder SAGE_WRITES_ENABLED=false pendant les tests de lecture. | Rechargement de FastAPI local et erreur TLS possible. Ne pas revenir automatiquement à HTTP pour écrire ; aucune confiance désactivée. | Restaurer les paramètres locaux sauvegardés, garder les écritures désactivées ; les lectures HTTP historiques, si conservées pour diagnostic, restent explicitement non sécurisées. |
| T7 | Après succès TLS, contrôle TEST et des six droits objet/action, demander la bascule locale d’activation des écritures ; les approbations unitaires restent obligatoires. | Une activation technique n’autorise aucun save/modify. Refus si droits/preuves expirés ou incohérents. | Désactiver le drapeau et recharger le seul backend ; aucune opération métier inverse automatique. |

## Ce qui manque pour appliquer un changement

Depuis la VM agent, aucun accès d’administration système autorisé au serveur Sage n’a été établi. Le port SSH 22 est non joignable. Le système et l’état local de 8443 doivent être confirmés **sur le serveur**, pas déduits d’un test TCP distant.

Un script d’inventaire Windows en lecture seule est prêt : [inspect_sage_tls_host.ps1](../scripts/inspect_sage_tls_host.ps1). Il refuse de s’exécuter si 192.168.9.200 n’est pas une adresse locale. Il ne lit ni mots de passe ni clés privées et ne change rien. L’administrateur peut le consulter, le copier et l’exécuter sur le serveur Sage s’il est Windows, sans désactiver une politique de sécurité pour le lancer. Ne pas l’exécuter sur l’agent. Si le serveur est Linux, fournir l’inventaire équivalent, pas exécuter ce script.

Les exports de droits métier et paramètres doivent également venir de l’administrateur Sage : identité effective, restrictions TEST/pools, GESITM/ITM, GESBPS/BPS, GESITF/ITF, options lecture/création/modification, site 201, catégories et numérotation. Une méthode CREATE publiée ne prouve pas ces droits.

## Critères d’acceptation avant une demande métier

1. Handshake TLS normal vérifiant chaîne, nom DNS et validité ; WSDL chargé via HTTPS sans redirection en clair ni verify=False.
2. getDescription et read des trois publications via le nouveau compte : V12/TEST, identité non administrateur et bons objets. Justificatifs des droits et règles conditionnelles vérifiés.
3. SAGE_WRITES_ENABLED reste false pendant ces contrôles. Après activation technique autorisée, absence/faux jeton/jeton expiré continuent à bloquer les écritures.
4. Préparer à nouveau les créations avec les libellés demandés, contrôler les codes absents et présenter UUID/digest/valeurs actuels. Aucun accord technique ne remplace l’accord métier.
5. C-ITM puis read ; C-BPS puis read, chacun avec son approbation. Rechercher ITF après création ITM : s’il existe automatiquement, ne pas envoyer save ; sinon préparer C-ITF avec un accord supplémentaire. Pour chaque opération, React → FastAPI → SOAP, read et comparaison, historique PostgreSQL et vérification GESITM/GESBPS/GESITF.
6. Préparer les trois modifications seulement après confirmation de l’existence des trois fiches, avec valeurs avant/après et trois nouveaux accords. Aucun retry automatique sur résultat ambigu.

Les détails opérationnels, certificats historiques et configurations candidates restent dans [le plan complet](ETAPE-4-ACTIONS-AVANT-ECRITURE.md). Les propositions devront être ajustées après l’inventaire ; elles ne sont pas une attestation de conformité déjà acquise.
