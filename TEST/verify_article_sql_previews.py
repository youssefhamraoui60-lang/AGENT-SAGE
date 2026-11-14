"""Real TEST connection: previews only. Never invoke execute=True."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import article_sql as sql

def run():
    audit=sql.catalog('AVNS');results=[]
    category={'id':'read-only-preview','code':'QAT01','designation':'Categorie controle lecture seule','nom_court':'CONTROLE','modele':'GEN','gestion_stock':1,'achete':2,'vendu':2,'fabrique':1,'livrable':2,'sous_traite':1,'receptionne':2,'unite':'UN','code_comptable':'STD','taxe':'T20'}
    plans=[sql.category_plan(category,audit)]
    base={'code_article':'SQLPREVIEW201','designation':'Controle preparation sans creation','categorie':'AVNS','requested_sites':['201'],'fournisseurs':[{'code':'F994'}]}
    plans.append(sql.article_plan(base,audit))
    plans.append(sql.article_plan({**base,'code_article':'SQLPREVIEW202','requested_sites':['202'],'fournisseurs':[{'code':p} for p in ('F994','F468','F354','F007')]},audit))
    plans.append(sql.article_plan({**base,'code_article':'SQLPREVIEW203','categorie':'AVT','gestion_stock':'2','vendu':'1','requested_sites':['201','202'],'fournisseurs':[],'supplier_intent':'none'},sql.catalog('AVT',2)))
    for plan in plans:
        result=sql.transport('plan',plan,False)
        assert result.get('ok') and result.get('transaction_state')=='VALIDATED_NO_INSERT' and result.get('executed') is False,result
        assert len(result['records'])==len(plan['nodes']) and all(r['inserted']==0 for r in result['records'])
        results.append(result)
    negative=[]
    existing=copy.deepcopy(plans[1]);existing['code']='TESTART201'
    changed=copy.deepcopy(plans[1]);changed['nodes'][0]['source_hash']='0'*64
    duplicate=copy.deepcopy(plans[1]);duplicate['nodes'][-2]['overrides']['ITMREFBPS_0']=audit['supplier_models'][0]['fields']['ITMREFBPS_0']
    for name,plan,number in [('existing_article',existing,50205),('changed_model',changed,50217),('unique_provider_reference',duplicate,50220)]:
        result=sql.transport('plan',plan,False)
        assert result.get('ok') is False and result.get('sql_error_number')==number,result
        assert result.get('transaction_state')=='ROLLBACK' and result.get('executed') is False
        negative.append({'case':name,**result})
    report={'sage_writes':0,'permission_changes':0,'previews':results,'negative_cases':negative}
    (ROOT/'TEST/article-sql-real-preview-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','previews':len(results),'negative_cases':len(negative),'sage_writes':0}))

if __name__=='__main__':run()
