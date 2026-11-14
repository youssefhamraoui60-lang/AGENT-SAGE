# Modern Foam : reprise de la conversation jointe

Corrections ciblées : « ouipas de fronseur » est une suppression explicite du
fournisseur ; « Site déclaré 202 » renseigne le site sans modèle ; un « oui » quand
le site manque demande un code clairement au lieu de répéter tout le tableau.

Périmètre web limité ajouté : MFB-A-XPS-40 / Modern foam boards A XPS 4 CM et
MFB-B-XPS-40 / Modern foam boards B XPS 4 CM, NEG, unités M2 identiques, sans
fournisseur ni réglage explicite de stock, site 202 société 20 OULD BOUAZZA, TEST.
L'existence catégorie/unité/site/société et les doublons sont vérifiés avant SAVE.
Aucune règle générale de catégorie ni autorisation publique n'est modifiée.

Les deux articles ont été préparés réellement par PowerShell SOAP et SQL, sans SAVE :
logs/modern-foam-M2-site202-preparation.json. La catégorie conserve ses valeurs par
défaut non explicitement modifiées. Les unités M2 sont celles demandées, avec
coefficients 1 entre unités identiques. La validation métier finale appartient à Sage.

Après Ctrl+F5, reprendre les brouillons existants : confirmer celui qui ne l'est
pas encore, préparer chaque création, relire les XML, cocher puis approuver et
exécuter chaque article séparément. Chaque approbation lie le contenu, le propriétaire,
le site, l'expiration et l'opération. Un seul SAVE par code, suivi de READ et SELECT.
Aucun SAVE n'a été envoyé pendant cette correction ; leur création réelle n'est
pas revendiquée comme déjà réussie.

Le site 202 est ici un périmètre de contrôle du maître article. Les fiches
article-site ne sont pas créées implicitement ; le parcours WS_AR_SITE actuel reste
distinct et limité à EXT_POUDRE. Les autres écritures publiques restent HTTP 423.
