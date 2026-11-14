"""Real Qwen extraction + real SQL previews, never physical Sage insertion."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_model as model,conversation_chat as chat,article_sql_dialogue as dialogue

async def main():
    cases=[
      ('fr',"Nous avons besoin de l'article CARTON VERIFICATION. Code article: QWART201, catégorie: AVNS, unité: UN, site 201, fournisseurs F994 et F007. Il est acheté et vendu, non géré en stock.",'CARTON VERIFICATION','AVNS','1',['F994','F007']),
      ('darija',"Salam, bghit nzid article smitou CARTON DAR, code article: QWART203, categorie: AVT, unite: UN, sites 201 et 202. Had article mstocki, kanchriwh, ma kaytba3ch, sans fournisseur.",'CARTON DAR','AVT','2',[])]
    results=[]
    for language,text,name,category,stock,providers in cases:
        state={'articles':[],'partners':[],'supplier_target':'TEST'};token=model.FORCE_AI.set(True)
        try:
            delta,provenance=await model.extract(text,state,[],[])
            changed=chat.merge(state,delta,text);reply=dialogue.prepare_state(changed,text,state)
            a=changed['articles'][0]
            passed=(a['designation']==name and a['categorie']==category and a['gestion_stock']==stock and [p['code'] for p in a.get('fournisseurs') or []]==providers and a.get('operation',{}).get('status')=='prepared')
            result={'language':language,'passed':passed,'real_model_called':provenance['real_model_called'],'seconds':provenance['seconds'],'designation':a.get('designation'),'category':a.get('categorie'),'stock':a.get('gestion_stock'),'providers':a.get('fournisseurs'),'status':a.get('operation',{}).get('status'),'message':reply,'extracted_delta':delta.model_dump(exclude_none=True,exclude_unset=True),'sage_writes':0}
        except Exception as exc:result={'language':language,'passed':False,'error_type':type(exc).__name__,'sage_writes':0}
        finally:model.FORCE_AI.reset(token)
        results.append(result);print(json.dumps(result,ensure_ascii=True),flush=True)
    (ROOT/'TEST/article-qwen-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['passed'] for r in results)

if __name__=='__main__':asyncio.run(main())
