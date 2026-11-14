# EXT_POUDRE : préparation web corrigée, aucun SAVE automatique

Le blocage `test_article_code_required` venait de la limitation initiale aux codes
TEST. Une exception de préparation/exécution après confirmation humaine est
désormais strictement liée au brouillon suivant : EXT_POUDRE, Extincteur à poudre,
NEG, UN, site 201 explicitement déclaré, fournisseur F1025 / CHAOUIA PROTECT,
gestion stock 1 (Non géré). Aucun autre code hors TEST ni fournisseur n'est ouvert.

La préparation réelle SOAP a confirmé la publication des champs et l'absence de
doublon. Le XML contient ITM0_1.XBPS=F1025, ITM2_1.STOMGTCOD=1 et une ligne de
table standard ITP_1.BPSNUM=F1025. Aucune référence fournisseur n'est inventée : la
référence interne provisoire du chat n'est pas copiée dans ITMREFBPS.

La relecture SOAP compare aussi la ligne fournisseur. Le SELECT SQL après une
future création vérifiera ITMMASTER.STOMGTCOD_0 et le lien TEST.ITMBPS, en plus
des six champs déjà comparés. Les magasins/fournisseurs/catégories existants ne
sont pas modifiés. Aucune fiche article-site n'est créée.

Pour reprendre la conversation : Ctrl+F5, rouvrir le brouillon, confirmer F1025 si
nécessaire, puis Préparer la création. Relire le XML, cocher l'autorisation,
Approuver puis Exécuter seulement pour autoriser une création réelle dans TEST.
Une tentative unique par code est conservée sur disque. Aucun retry automatique.

La préparation est réussie ; la création de cette combinaison n'est pas encore
testée en réel. Sage peut encore refuser une règle conditionnelle lors du SAVE.
Preuve sans écriture : logs/EXT_POUDRE-real-preparation.json.
