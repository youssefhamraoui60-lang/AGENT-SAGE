"""Build reviewable immutable preparation evidence; no network and no SAVE."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_soap import parse_xml
from app.services.sage_gateway import RESOURCES,build_xml,digest
from app.schemas.sage_crud import Preparation


def main():
    source=sorted((ROOT/'tests/ai-evaluation/real-20').glob('preparation-*/preparation.json'))[-1]
    report=json.loads(source.read_text(encoding='utf-8-sig'))
    directory=source.parent
    description=parse_xml((directory/'WS_AR_SITE-description.xml').read_bytes())
    if any(description.get(k)!=v for k,v in {'FOL':'TEST','SOL':'V12','PNA':'WS_AR_SITE','OBJ':'ITF'}.items()):
        raise ValueError('site_description_not_TEST')
    for row in report['Items']:
        if any(r.get('AnyInsert')==1 or r.get('AnyUpdate')==1 or r.get('AnyDelete')==1 for r in report.get('SqlTablePermissions',[])):
            row['Blockers'].append('SQL_READER_HAS_TABLE_WRITE_PERMISSIONS_REQUIRES_REVIEW')
        fields=[{'group':'ITF0_1','name':'TCLCOD','value':row['Category']},
                {'group':'ITF0_1','name':'STU','value':row['StockUnit']},
                {'group':'ITF1_1','name':'STOMGTCOD','value':row['StockManagement']}]
        payload=Preparation(action='create',keys={'ITMREF':row['Code'],'STOFCY':row['Site']},fields=fields)
        xml=build_xml(description,RESOURCES['article-sites'],payload)
        (directory/(row['Code']+'-article-site-NOT-SENT.xml')).write_text(xml,encoding='utf8')
        row['ProposedArticleSite']={'payload':payload.model_dump(),'xml_sha256':hashlib.sha256(xml.encode()).hexdigest(),
                                    'published_input_checks':True,'business_rules_verified':False,'sent':False}
        row['ArticleSiteDependency']='Parent article must be created and read back before site preparation/execution'
        if row.get('ArticlePlan'):
            row['ArticlePayloadMatchesExpectedStock']=row['StockManagement']=='1' or row['CategoryReference']['STOMGTCOD_0']==2
    manifest={'folder':'TEST','approved':False,'save_attempts':0,'source':source.name,'prepared_at':report['At'],
              'items':report['Items'],'security_or_connector_change_approved':False}
    (directory/'review-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    checksum=digest(manifest)
    (directory/'review-manifest.sha256').write_text(checksum+'\n',encoding='ascii')
    lines=['# Rapport des 20 créations réelles — préparation, aucune création exécutée','',
           'État : **0 article et 0 fiche article-site créés par cette recette**. Aucune approbation des données exactes reçue.',
           '',f'Lectures réelles réalisées le {report["At"]}. Dossier vérifié : TEST / solution V12.',
           '',f'Preuves : `{directory.relative_to(ROOT).as_posix()}`.',
           f'Empreinte du manifeste complet à relire : `{checksum}`. Les données sont proposées, non approuvées.', '',
           '| Test | Code article | Catégorie | Site | Création article | Création article-site | Relecture |',
           '|---|---|---|---|---|---|---|']
    for row in report['Items']:
        before=row.get('BeforeArticle',{});site=row.get('BeforeSite',{})
        read='Absences confirmées par SOAP READ' if before.get('Exists') is False and site.get('Exists') is False else 'À vérifier'
        lines.append(f'| {row["Test"]:02} | {row["Code"]} | {row["Category"]} | {row["Site"]} | Non tentée | Non tentée | {read} |')
    lines+=['','## Données exactes proposées','',
            '| Code | Désignation | Stock / achat / vente | Gestion stock | Fournisseur | Statut article proposé |',
            '|---|---|---|---|---|---|']
    for row in report['Items']:
        lines.append(f'| {row["Code"]} | {row["Designation"]} | {row["StockUnit"]} / {row["PurchaseUnit"]} / {row["SalesUnit"]} | {row["StockManagement"]} | {row["SupplierCode"] or "Sans fournisseur (à valider selon catégorie)"} | {row["Status"]} |')
    lines+=['','## Vérifications et réserves','',
            '- Les 20 codes et les 20 couples article/site ont fait l’objet de READ réels. Les XML restent NOT-SENT.',
            '- Catégories NEG et CADP issues de TEST.ITMCATEG ; unités UN/M2 issues de TEST.TABUNIT. Les sites proviennent de TEST.FACILITY.',
            '- Gestion de stock issue de la catégorie : 1 non géré, 2 géré. NEG/M2 est une proposition fondée sur des comparables, pas une règle métier certifiée.',
            '- Fournisseur F1025 recherché dans TEST.BPSUPPLIER ; sa pertinence pour chaque test et la facultativité du fournisseur restent à valider.',
            '- Contrôle SQL : droits DML au niveau schéma et tables présents dans preparation.json ; aucun droit modifié.',
            '- **Blocage confirmé :** le contrôle des tables TEST révèle des droits INSERT/UPDATE pour le lecteur SQL. Le compte ne peut pas être certifié lecture seule sur la base du seul contrôle de schéma. Aucune écriture SQL effectuée ; correction des droits soumise à approbation distincte.',
            '- Les XML article-site sont validés contre les champs publiés. Cette validation ne certifie pas les règles conditionnelles Sage.',
            '- La préparation article utilise le module existant. La création par le chat reste limitée à ses périmètres actuels.',
            '- Le connecteur de création article-site reste limité à EXT_POUDRE. Aucun élargissement appliqué.',
            '- Les contrôles de certificats, révocation, comptes et permissions restent inchangés.', '',
            '## Approbations nécessaires avant toute écriture','',
            '1. Validation métier des données exactes du manifeste : catégories, unités, stocks, fournisseurs facultatifs et paramètres hérités.',
            '2. Approbation distincte d’une adaptation bornée des connecteurs pour ces seuls 20 codes et leurs sites ; aucune activation globale.',
            '3. Confirmation explicite du lot final et de son empreinte après revue des XML et des corrections éventuelles.',
            '', '## Procédure après approbation','',
            'Relire disponibilité et descriptions ; préparer un article ; consommer son approbation à usage unique ; SAVE article ; READ et comparaison des champs ; préparer puis SAVE article-site ; READ et comparaison des deux fiches. Arrêter en cas d’incertitude et réconcilier uniquement par lecture. Aucun renvoi automatique.',
            '', '## Robustesse','',
            'Les cas d’erreur doivent être exercés en simulation avant recette. Les cas réels destructifs ne sont pas déclenchés pour provoquer une panne. La réussite finale exige 20 paires effectivement présentes et comparées ; elle n’est pas atteinte à ce stade.', '']
    target=ROOT/'tests/ai-evaluation/RAPPORT-20-CREATIONS-REELLES.md'
    target.write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'report':str(target),'manifest_sha256':checksum,'prepared':len(report['Items']),'real_creations':0}))


if __name__=='__main__':main()
