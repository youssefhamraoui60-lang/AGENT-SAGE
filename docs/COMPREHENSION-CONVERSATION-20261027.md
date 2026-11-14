# Compréhension conversationnelle : corrections et preuve

Le fichier joint signalait deux défauts : la suppression d'un fournisseur n'était
pas représentable comme une omission de champ dans le delta du modèle, et le site
202 était marqué en erreur métier à cause d'une restriction d'écriture au site 201.

Le contrôleur reconnaît désormais un retrait explicite (« pas de forniseur »,
« sans fournisseur », « retire le fournisseur »), le distingue d'une question et
retire nom/code/propositions fournisseur et référence provisoire dérivée. Le choix
est affiché « Sans fournisseur », sans nouvelle question sur son code. Le contexte
article/catégorie/unité/site reste conservé. Une désignation ciblant le deuxième
article ne modifie que celui-ci. Un article déjà exécuté reste immuable.

Les catégories et unités trouvées sont annoncées comme vérifiées dans TEST.
Le lecteur de sites rejoint COMPANY pour afficher le vrai rattachement société.
Le site 202 est bien Frais généraux / société 20 OULD BOUAZZA ; aucune correspondance
SOB ou OB vers une société n'est inventée. Le rattachement présenté provient de SQL.
Les détails financiers historiques ne sont plus répétés sans demande financière.

La validité métier d'un site est séparée des limites du parcours d'écriture.
Ces limites restent explicites : les nouveaux articles MFB en M2 / site 202 ne sont
pas autorisés par le parcours de test NEG/UN/site201 existant. Aucune permission
générale ni nouvelle autorisation d'écriture n'a été ajoutée par cette correction.

Validation : 80 tests automatisés réussis ; tests complémentaires d'affichage du
choix Sans fournisseur réussis. Reprise réelle des trois messages via HTTP, modèle
local et SQL TEST : PASS, deux articles distincts et conservés, fournisseur supprimé,
NEG/M2 vérifiés et site 202 retrouvé. Aucun bouton d'approbation/exécution appelé.
Rapports : logs/conversation-understanding-tests.xml et
logs/conversation-understanding-real-replay.json.

Actualiser /sage/ avec Ctrl+F5 puis poursuivre la conversation existante. Les réponses
déjà enregistrées restent dans l'historique ; la prochaine correction utilise les
nouvelles règles. La qualité générale du modèle n'est pas certifiée par ces seuls
scénarios : les demandes ambiguës restent à clarifier et aucune écriture n'est déduite
d'une simple confirmation conversationnelle.
