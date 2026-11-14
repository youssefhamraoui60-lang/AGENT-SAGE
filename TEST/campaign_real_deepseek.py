"""One real, read-only Darija semantic probe; no Sage connector or draft write."""
import sys,json,asyncio,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import conversation_analysis as semantic,ai_provider
original=ai_provider.complete;calls=[]
async def observed(*a,**kw):
    start=time.monotonic();result=await original(*a,**kw)
    calls.append({'provider':result.get('provider'),'model':result.get('model'),'seconds':round(time.monotonic()-start,3),'usage':result.get('usage'),'estimated_cost_usd':str(ai_provider.estimate(result.get('model'),result.get('usage') or {}))})
    return result
async def main():
    ai_provider.complete=observed
    text='Salam bghit nzid fournisseur jdid smitou NORD FOURNITURES, kayn f Tanger, SARL AU. ICE mazal ma3ndich daba.'
    result=await semantic.analyse(text,{'partners':[],'articles':[]},[])
    facts={f['field']:f['value'] for f in result.get('analysis',{}).get('extracted',[])}
    checks={'cloud_used':result.get('provider')=='deepseek','validated':result.get('status')=='validated','intent':result.get('analysis',{}).get('intent')=='CREATE_SUPPLIER','name':facts.get('nom')=='NORD FOURNITURES','city':facts.get('ville')=='Tanger','legal_form':facts.get('forme_juridique')=='SARL AU','unknown_ice':'ice' in result.get('analysis',{}).get('unknowns',[])}
    artifact={'status':'PASS' if all(checks.values()) else 'FAIL','text':text,'checks':checks,'analysis':result,'calls':calls,'sage_writes':0}
    (ROOT/'TEST/campaign-real-deepseek.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':artifact['status'],'checks':checks,'calls':calls,'sage_writes':0},ensure_ascii=True))
    return 0 if artifact['status']=='PASS' else 1
raise SystemExit(asyncio.run(main()))
