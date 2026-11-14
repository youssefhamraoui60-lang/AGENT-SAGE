"""Prepare an inert data manifest and evidence-based report; no DB connection or DML."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tls = json.loads((ROOT / 'logs/sql-server-readonly-tests.json').read_text(encoding='utf-8-sig'))
prior = json.loads((ROOT / 'logs/four-creation-sql-discovery.json').read_text(encoding='utf-8-sig'))
records = [
    {'object': 'ITM', 'code': 'AITEST001', 'sage_table_reference': 'TEST.ITMMASTER',
     'proposed_values': {'ITMREF_0': 'AITEST001', 'ITMDES1_0': 'ARTICLE TEST CREATION API SAGE X3', 'TCLCOD_0': 'NEG', 'STU_0': 'UN', 'PUU_0': 'UN', 'SAU_0': 'UN'}},
    {'object': 'ITF', 'code': 'AITEST001', 'site': '201', 'sage_table_reference': 'TEST.ITMFACILIT',
     'proposed_values': {'ITMREF_0': 'AITEST001', 'STOFCY_0': '201'}, 'depends_on': 'ITM/AITEST001'},
    {'object': 'BPS', 'code': 'F_AITEST01', 'sage_table_reference': 'TEST.BPSUPPLIER',
     'proposed_values': {'BPSNUM_0': 'F_AITEST01', 'BSGCOD_0': 'FR'},
     'partner_values_to_map': {'legal_name': 'FOURNISSEUR TEST IA', 'country': 'MA', 'currency': 'MAD'}},
    {'object': 'BPC', 'code': 'C_AITEST01', 'sage_table_reference': 'TEST.BPCUSTOMER',
     'proposed_values': {'BPCNUM_0': 'C_AITEST01', 'BCGCOD_0': 'CL'},
     'partner_values_to_map': {'legal_name': 'CLIENT TEST IA', 'country': 'MA', 'currency': 'MAD'}},
]
manifest = {'checked_at': tls['checked_at'], 'kind': 'INERT_PREPARATION_NOT_EXECUTABLE',
            'records': records, 'insert_attempts': 0, 'independent_sql_test_database': None,
            'mandatory_business_fields_fully_verified': False,
            'tls_result': tls['status'], 'prior_metadata_at': prior.get('checked_at'),
            'current_duplicate_checks_executed': False}
(ROOT / 'logs/SQL-CREATION-SIMULATION-DATA.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Tests de création simulée SQL — état réel', '',
         f"Contrôle TLS : {tls['checked_at']} (UTC).", '',
         f"Connexion à sage:1433 / x3v12 : **{tls['status']}**, cause `{tls.get('error_category', 'non précisée')}`.",
         '`Encrypt=True;TrustServerCertificate=False` ; aucun repli automatique, aucune confiance ajoutée.', '',
         '## Résultats par objet', '',
         '| Objet | Code / site | INSERT simulé | Vérification actuelle Sage/SQL | Statut |',
         '|---|---|---|---|---|',
         '| Article | AITEST001 | Non exécuté | Non effectuée dans cette intervention | BLOQUÉ |',
         '| Article-site | AITEST001 / 201 | Non exécuté | Non effectuée dans cette intervention | BLOQUÉ |',
         '| Fournisseur | F_AITEST01 | Non exécuté | Non effectuée dans cette intervention | BLOQUÉ |',
         '| Client | C_AITEST01 | Non exécuté | Non effectuée dans cette intervention | BLOQUÉ |', '',
         'Aucune base SQL Server indépendante explicitement désignée avec un accès de test autorisé n’a été trouvée dans la configuration examinée. Aucun INSERT, CREATE DATABASE, CREATE TABLE, changement de droits ni appel SOAP d’écriture exécuté. Aucune insertion simulée n’est annoncée comme réussie.', '',
         '## Structures et absence : constats antérieurs seulement', '',
         f"Source : four-creation-sql-discovery.json du {prior.get('checked_at')}. Ces lectures précédentes utilisaient le mode TMS à chiffrement optionnel autorisé antérieurement ; elles ne prouvent ni une connexion TLS vérifiée ni l’absence actuelle des fiches.", '',
         'Les quatre clés et les clés partenaires étaient absentes lors de ce relevé. Les métadonnées étaient limitées aux tables sélectionnées du schéma TEST ; SELECT paramétrés et bornés.', '',
         '- Unicité : ITMMASTER.ITMREF_0 ; ITMFACILIT.ITMREF_0 + STOFCY_0 ; BPSUPPLIER.BPSNUM_0 ; BPCUSTOMER.BPCNUM_0 ; BPARTNER.BPRNUM_0.',
         '- Relations métier : article-site vers article et FACILITY ; fournisseur/client vers BPARTNER ; catégories et unités vers leurs référentiels. Aucune FK SQL déclarée retournée pour les quatre tables ciblées : cela ne supprime pas les relations applicatives.',
         '- NEG et UN, site 201, catégories FR/CL, pays MA et devise MAD étaient présents. Leur présence ne prouve pas les droits de création.',
         '- Les contraintes physiques SQL (nullabilité, longueur, index) ne décrivent pas toutes les obligations conditionnelles Sage. Les champs d’adresse et autres obligations des tiers restent à valider. Le manifeste n’est pas une ligne Sage complète.', '',
         '## Données préparées, sans requête INSERT', '',
         'Voir SQL-CREATION-SIMULATION-DATA.json. Les noms de tables indiquent uniquement la correspondance à analyser ; ils ne sont jamais une destination d’écriture. Les raisons sociales relèvent des données partenaires : leur répartition ne doit pas être inventée.', '',
         '## Actions exactes pour poursuivre', '',
         '1. Faire fournir par l’administrateur la chaîne et le nom DNS du certificat SQL validé. Le certificat fallback précédemment observé ne permet pas une simple importation sûre de confiance ; une éventuelle correction serveur requiert votre autorisation technique distincte. Aucun paramètre serveur changé ici.',
         '2. Désigner une base SQL Server de simulation indépendante : serveur, port, nom de base hors x3v12 et identifiant de test configuré localement. Confirmer explicitement l’autorisation de créer des tables de simulation et d’y insérer ces quatre jeux. Ne pas accorder de droits supplémentaires à agent_sage_x3 sur x3v12 ; ne pas publier de mot de passe dans le chat.',
         '3. Dans cette base seulement, créer un modèle de simulation distinct : articles, sites, article-sites avec FK, partenaires uniques, fournisseurs et clients. Tester paramètres, unicité et dépendance article/site. Une réussite ne validera pas les règles métier Sage et ne rendra aucune fiche visible dans Sage.', '',
         '## Créations réellement visibles dans Sage', '',
         '- ITM, ITF, BPS : connecteurs FastAPI vers SOAP save existants, après transport vérifié, compte technique TEST et droits/preuves valides, puis approbation distincte pour chaque opération.',
         '- BPC : publication objet BPC autorisée ou import métier BPC via un canal Sage validé. Le modèle BPC existe selon le relevé précédent, mais AOWSIMPORT y répondait Service web inexistant ; aucune nouvelle publication/configuration effectuée.',
         '- Après création article, rechercher d’abord une éventuelle génération automatique de l’article-site 201. Aucune seconde création si déjà présent. Une réponse ambiguë interdit la relance automatique.',
         '- Après chaque écriture autorisée : relecture métier et SELECT SQL, comparaison, puis contrôle dans TEST → GESITM, GESITF, GESBPS ou GESBPC. Les quatre fiches ne sont pas annoncées comme créées.', '',
         'Bilan de cette intervention : zéro écriture SQL/SOAP ; contrôle TLS exécuté et bloqué ; données préparées seulement.']
(ROOT / 'logs/TEST-CREATION-SQL-SIMULATION.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('Rapport et manifeste créés ; connexions par ce script=0 ; INSERT=0.')
