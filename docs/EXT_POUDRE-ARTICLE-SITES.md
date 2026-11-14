# EXT_POUDRE : fiches article-site distinctes du maître

La demande « créer cet article dans les article-site 202 et 201 » passait dans le
parseur de modification du maître, déjà exécuté. La protection d'immutabilité levait
attempted_article_is_immutable_readback_only. Cette protection reste en place pour
les champs du maître ; la demande article-site est désormais un parcours enfant
distinct, capturé avant l'analyse du modèle.

Périmètre : EXT_POUDRE existant et confirmé, dossier TEST, société 20 OULD BOUAZZA,
sites 201 / 202 / 209 réellement relus dans FACILITY/COMPANY. Le site 301 et toute
autre société sont exclus. « Tous » développe uniquement les sites de ce périmètre.

La sélection ne déclenche aucun SAVE. Le chat propose Préparer les fiches article-site,
affiche les XML WS_AR_SITE, puis exige l'approbation des sites et le clic Exécuter.
L'approbation lie propriétaire de session, plans/digest, sélection et expiration de
15 minutes. Le statut executing est commité avant les appels SOAP. Chaque site
possède son propre marqueur permanent CreateNew. Une fiche existante est relue et
ignorée en écriture. Après une incertitude, les sites suivants ne sont pas tentés.

Le transport PowerShell et la politique HTTPS Windows TEST approuvée sont réutilisés.
La description doit confirmer V12/TEST, WS_AR_SITE, objet ITF. Le parent est relu et
les valeurs NEG/UN/gestion stock sont vérifiées. Aucun SAVE WS_ARTICLE n'est envoyé.
Chaque SAVE WS_AR_SITE est suivi immédiatement d'un READ des deux clés et des champs.

Vérification réelle sans écriture : getDescription et READ des sites 201 / 202,
fiches absentes, XML préparés (logs/EXT_POUDRE-sites-readonly.json). Le SAVE de ces
fiches n'est pas encore validé en réel : Sage peut refuser une règle conditionnelle.
Tests isolés du parcours web et tests PowerShell avec transport simulé réussis.

Pour reprendre : Ctrl+F5, rouvrir la conversation d'EXT_POUDRE, envoyer « Créer les
fiches article-site 201 et 202 ». Préparer, relire, approuver la sélection puis
exécuter. L'article maître et sa preuve de création restent conservés.

Correction complémentaire : un import local de run_in_threadpool dans send rendait
ce nom local à toute la fonction et provoquait UnboundLocalError avant capture.
Cet import redondant est supprimé. Un test de régression appelle désormais la
vraie route messages/stream avec la phrase exacte de l'utilisateur, dans une base
locale isolée, et vérifie l'absence d'appel au modèle et de modification du maître.
Six tests passent (logs/article-sites-stream-regression.xml).

La conversation existante a été reprise en préparation uniquement : sélection
201/202, deux plans relus depuis SOAP, statut prepared. Aucun SAVE envoyé.
Preuve : logs/EXT_POUDRE-sites-web-prepared.json. Après actualisation, l'utilisateur
peut directement relire puis approuver les sites dans la conversation existante.
