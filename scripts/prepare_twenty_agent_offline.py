"""Replay the proposed real-20 lot through the actual agent, with no ERP calls."""
from pathlib import Path
import json,sys,datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_offline_regression
from app.services import chat_fast_extract,conversation_chat as chat
from app.services.chat_model import Delta


def main():
    source=sorted((ROOT/'tests/ai-evaluation/real-20').glob('preparation-*/preparation.json'))[-1]
    prepared=json.loads(source.read_text(encoding='utf-8-sig'));rows=[]
    for item in prepared['Items']:
        state={'articles':[],'pending':[]};turns=[]
        messages=[f"Créer un article {item['Designation']}, catégorie {item['Category']}, unité {item['StockUnit']}, site {item['Site']}.",
                  f"Code article {item['Code']}.",
                  f"Code fournisseur {item['SupplierCode']}." if item['SupplierCode'] else 'Sans fournisseur.']
        for message in messages:
            extracted=chat_fast_extract.extract(message,state)
            if not extracted:raise ValueError('offline_agent_route_not_available: '+repr(message))
            delta,provenance=extracted
            state=chat.merge(state,delta,message)
            turns.append({'message':message,'delta':delta.model_dump(exclude_unset=True),'provenance':provenance})
        a=state['articles'][0]
        comparisons={field:a.get(field)==item[key] for field,key in [('designation','Designation'),('code_article','Code'),('categorie','Category'),('unite','StockUnit'),('site','Site')]}
        comparisons['supplier']=a.get('code_fournisseur')==item['SupplierCode'] if item['SupplierCode'] else a.get('supplier_intent')=='none'
        if not all(comparisons.values()):raise ValueError('agent_preparation_mismatch')
        rows.append({'code':item['Code'],'turns':turns,'draft':a,'comparisons':comparisons,
                     'category_stock_default':item['StockManagement'],'stock_default_not_implicitly_modified':True})
    result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'real_model_called':False,
            'route':'actual_agent_deterministic_extractor_and_merger','sql_calls':0,'soap_calls':0,
            'real_creations':0,'items':rows}
    target=source.parent/'agent-preparation.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'prepared_through_agent':len(rows),'all_compared':True,'file':str(target),'real_creations':0}))


if __name__=='__main__':main()
