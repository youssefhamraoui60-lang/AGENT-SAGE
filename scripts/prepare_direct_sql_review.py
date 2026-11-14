"""Offline review artifacts only. Never connects to SQL or executes DML."""
import csv,json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/'logs/SQL-ISOLATED-PREREQUISITES.json').read_text(encoding='utf-8-sig'))
s=json.loads((ROOT/'logs/four-creation-sql-discovery.json').read_text(encoding='utf-8-sig'))
assert r['status']=='READ_ONLY_COMPLETED' and s['status']=='PASS'
folder=ROOT/'sql/direct-test-review';folder.mkdir(parents=True,exist_ok=True)
columns=r['results']['creation_columns']
known={
 'ITMMASTER':{'ITMREF_0':'AITEST001','ITMDES1_0':'ARTICLE TEST CREATION API SAGE X3','TCLCOD_0':'NEG','STU_0':'UN','PUU_0':'UN','SAU_0':'UN','PUUSTUCOE_0':1,'SAUSTUCOE_0':1},
 'ITMFACILIT':{'ITMREF_0':'AITEST001','STOFCY_0':'201'},
 'ITMSALES':{'ITMREF_0':'AITEST001'},
 'BPSUPPLIER':{'BPSNUM_0':'F_AITEST01','BSGCOD_0':'FR'},
 'BPCUSTOMER':{'BPCNUM_0':'C_AITEST01','BCGCOD_0':'CL'},
}
def automatic(c):
 return bool(c['is_identity'] or c['is_computed'] or c['generated_always_type'] or c['data_type'] in ('timestamp','rowversion'))
matrix=[]
for c in columns:
 c=dict(c);t=c['table_name'];n=c['column_name']
 c['proposed_value']=known.get(t,{}).get(n,'')
 c['status']='SQL_GENERATED' if automatic(c) else 'PROPOSED_NOT_BUSINESS_VALIDATED' if n in known.get(t,{}) else 'DEFAULT_TO_REVIEW' if c['default_object_id'] else 'UNRESOLVED'
 matrix.append(c)
with (folder/'column-mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(matrix[0]));w.writeheader();w.writerows(matrix)
specs=[('01-article',['ITMMASTER','ITMSALES'],'ITMMASTER','ITMREF_0','AITEST001'),
 ('02-article-site',['ITMFACILIT'],'ITMFACILIT','ITMREF_0','AITEST001'),
 ('03-fournisseur',['BPARTNER','BPSUPPLIER'],'BPSUPPLIER','BPSNUM_0','F_AITEST01'),
 ('04-client',['BPARTNER','BPCUSTOMER'],'BPCUSTOMER','BPCNUM_0','C_AITEST01')]
def literal(v):return str(v) if isinstance(v,int) else "N'"+v.replace("'","''")+"'"
for filename,tables,main,key,code in specs:
 predicates=f'[{key}]=@Code'+(" AND [STOFCY_0]=N'201'" if main=='ITMFACILIT' else '')
 lines=['-- REVIEW ONLY / NON EXECUTABLE CREATION: unconditional THROW protects DML.',
        '-- Unknown values and table coverage require Sage specialist validation.',
        '-- No SELECT * clone, no zero/blank defaults invented, no trigger disabled.',
        'USE [x3v12];','SET NOCOUNT ON;','SET XACT_ABORT ON;','SET LOCK_TIMEOUT 3000;',
        "IF DB_NAME() <> N'x3v12' THROW 51000, 'Wrong database', 1;",
        "IF @@TRANCOUNT <> 0 THROW 51000, 'Run without an existing transaction', 1;",
        f'DECLARE @Code nvarchar(20)={literal(code)};',
        'BEGIN TRY','  BEGIN TRANSACTION;',
        f"  IF EXISTS(SELECT 1 FROM [TEST].[{main}] WITH(UPDLOCK,HOLDLOCK) WHERE {predicates})",
        "    THROW 51001, 'Duplicate key: no creation or update permitted', 1;"]
 if main in ('BPSUPPLIER','BPCUSTOMER'):
  lines += ["  IF EXISTS(SELECT 1 FROM [TEST].[BPARTNER] WITH(UPDLOCK,HOLDLOCK) WHERE BPRNUM_0=@Code)","    THROW 51002, 'Shared partner key already exists', 1;"]
 if main=='ITMFACILIT':
  lines += ["  IF NOT EXISTS(SELECT 1 FROM [TEST].[ITMMASTER] WITH(HOLDLOCK) WHERE ITMREF_0=@Code)","    THROW 51003, 'Parent article absent', 1;",
            "  IF NOT EXISTS(SELECT 1 FROM [TEST].[FACILITY] WHERE FCY_0=N'201')","    THROW 51004, 'Site absent', 1;"]
 lines += ["  THROW 51010, 'NOT VALIDATED: no Sage initialization or business integrity attestation', 1;",'',
           '/* INSERT PROTOTYPES ONLY. Do not uncomment before full review, including associated tables.']
 for table in tables:
  cols=[c for c in columns if c['table_name']==table and not automatic(c)]
  if not cols:lines += [f'-- {table}: metadata unavailable.'];continue
  lines += [f'-- Table coverage candidate: {table}; not an assertion that this is exhaustive.',
            f'INSERT INTO [TEST].[{table}] (',',\n'.join('  ['+c['column_name']+']' for c in cols),') VALUES (']
  vals=[]
  for c in cols:
   name=c['column_name']
   value=known.get(table,{}).get(name)
   vals.append('  '+(literal(value) if value is not None else '/* VALUE_UNVALIDATED */ @v_'+table+'_'+name))
  lines += [',\n'.join(vals),');']
 lines += ['-- Additional tables, translations, addresses, counters and business actions remain to review.','*/',
           f'  SELECT [{key}] FROM [TEST].[{main}] WHERE {predicates};',
           '  -- Verification must also compare every expected field and all dependent rows.',
           '  ROLLBACK TRANSACTION; -- review script never commits','END TRY','BEGIN CATCH',
           '  IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;','  THROW;','END CATCH;']
 (folder/(filename+'.sql')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
unresolved=Counter(c['table_name'] for c in matrix if c['status']=='UNRESOLVED' and not c['is_nullable'])
summary={'checked_at':r['checked_at'],'sql_writes':0,'absence':s['absence'],'not_ready_for_execution':True,'unresolved_non_nullable_by_table':dict(unresolved),'mapping_columns':len(matrix)}
(folder/'review-status.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
lines=['# Analyse SQL directe TEST — préparation sans écriture','',f"Constats SQL du {r['checked_at']} UTC.",'',
       'Aucune utilisation SOAP/sandbox ; aucune écriture dans x3v12, aucun service ou droit modifié. Scripts générés hors ligne seulement.','',
       '## Résultats','',
       '| Objet | Clé | Présence SQL | Préparation |','|---|---|---|---|',
       '| Article | AITEST001 | Absent | 01-article.sql, non validé |',
       '| Article-site | AITEST001 / 201 | Absent | 02-article-site.sql, parent absent |',
       '| Fournisseur | F_AITEST01 | Absent et clé BPARTNER absente | 03-fournisseur.sql, non validé |',
       '| Client | C_AITEST01 | Absent et clé BPARTNER absente | 04-client.sql, non validé |','',
       '20 articles et 30 associations article-site lus ; trois fournisseurs et trois clients lus. Tri ROWID décroissant : échantillon technique, pas preuve absolue de date de création.','',
       '## Métadonnées et valeurs','',
       f"{len(matrix)} colonnes décrites dans sql/direct-test-review/column-mapping.csv : types, taille SQL en octets, précision/échelle, nullabilité, identité, calcul, défaut SQL, valeur proposée et état de revue.",
       'Une colonne non nullable ne signifie pas une saisie utilisateur obligatoire. Les valeurs vides, zéros et dates sentinelles doivent avoir une justification métier, pas un remplissage automatique. Les valeurs des fiches existantes ne prouvent pas leur mécanisme d’initialisation.',
       'Le code comptable et le niveau de taxe ne sont pas inventés ; NEG/UN et FR/CL/MA/MAD sont des propositions, non une validation complète. Le mapping partagé BPARTNER doit distinguer fournisseur et client et être complété avec les adresses réellement nécessaires.','',
       'Colonnes non nullables restant sans valeur établie par table :','',
       '```json',json.dumps(dict(unresolved),indent=2),'```','',
       '## Relations et contrôles SQL observés','',
       'Clés uniques : ITMREF ; ITMREF+STOFCY ; BPSNUM ; BPCNUM ; BPRNUM. Dépendances applicatives : article-site→article/FACILITY ; tiers→BPARTNER/BPADDRESS ; catégories et unités→référentiels. ITMSALES existe pour l’article exemple TSTAI2610174D94B4, pas de ligne ITF/ITMBPS/ITMBPC trouvée pour cet exemple. Une présence ne prouve pas que toutes les fiches exigent ces mêmes lignes.',
       'Trigger visible : ITMMASTER_UPDTICK, actif, UPDATE seulement. Aucune contrainte CHECK retournée dans le périmètre interrogé. VIEW DEFINITION base=0 : visibilité limitée ; ne pas conclure à l’absence de tous les autres contrôles. Les métadonnées ne donnent pas accès à tous les traitements applicatifs.','',
       '## Scripts fournis et limites','',
       'Chaque script comprend cible x3v12/TEST fixe, contrôle des doublons avec verrouillage borné, transaction TRY/CATCH, contrôles de parent/site pour ITF, collision BPARTNER pour tiers et SELECT final. Les prototypes INSERT listent les colonnes physiques et les valeurs connues ; les autres portent VALUE_UNVALIDATED. Ils sont commentés, précédés d’un THROW inconditionnel, et aucun COMMIT n’est prévu. Ces fichiers ne sont pas des scripts de création prêts à exécuter ; aucun verrou n’a été pris par leur génération.','',
       'La transaction SQL ne remplace pas les validations Sage. Les prototypes ne traitent pas automatiquement : défauts de catégorie et paramètres société/site ; compteurs et maintien des références manuelles ; coefficients, taxes, comptabilité ; UUID/horodatages/auteur/tick ; textes traduits ; blocs adresses/contacts ; tables dépendantes conditionnelles ; droits applicatifs/codes d’accès ; actions objet, workflows, spécifiques locaux, audit et intégrations. La liste est un périmètre à examiner, pas une affirmation que chaque traitement est obligatoire pour chacun des quatre objets.','',
       '## Conditions avant une création directe réelle','',
       '1. Faire approuver par un spécialiste Sage le mapping complet pour la version, les activités et spécifiques de TEST, avec la liste exhaustive des tables/effets applicables.',
       '2. Obtenir une visibilité administrative en lecture des définitions pertinentes et du code objet/import, sans élargir automatiquement le compte agent.',
       '3. Justifier chaque initialisation ; définir la création atomique des dépendances, traductions et tiers, les contrôles de numérotation, les champs techniques et les refus métier.',
       '4. Valider la méthode hors tables actives de Sage, puis disposer de sauvegarde/restauration et d’une recette de cohérence acceptée. Aucun clonage ou sauvegarde serveur effectué ici.',
       '5. Seulement après intégrité et compatibilité établies, soumettre le script final et l’autorisation d’écriture précise. Une relecture SQL seule ne prouvera pas la conformité applicative ; vérifier ensuite GESITM/GESITF/GESBPS/GESBPC.',
       '', 'Statut des quatre créations : NON EXÉCUTÉES, intégrité applicative non établie. Aucun succès simulé présenté comme une fiche Sage créée.','',
       'Sources : [modèle ITMA et obligations conditionnelles](https://online-help.sagex3.com/erp/12/en-us/Content/OBJ/AOE_ITMA.htm), [imports objet et contrôles](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAOE.htm), [dictionnaire ITMMASTER](https://online-help.sagex3.com/erp/12/fr-fr/Content/MCD/ITMMASTER.htm).',
       'Preuves : logs/SQL-ISOLATED-PREREQUISITES.json (nom historique, SELECT TEST seulement), logs/four-creation-sql-discovery.json, logs/direct-sql-analysis-run.log et logs/direct-sql-absence-run.log.']
(ROOT/'logs/ANALYSE-SQL-DIRECTE-TEST.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
