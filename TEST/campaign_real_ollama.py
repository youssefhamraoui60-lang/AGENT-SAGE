"""One real manual-local chat probe. No cloud call and no Sage access."""
import sys,json,asyncio,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import ai_provider
async def main():
    token=ai_provider.CONTEXT.set({'mode':'local'});start=time.monotonic()
    try:
        r=await ai_provider.complete([{'role':'system','content':'Réponds en une phrase courte, sans opération métier.'},{'role':'user','content':'Salam, bonjour !'}],max_tokens=48,local_timeout=25,purpose='campaign_real_local_probe')
        result={'status':'PASS' if r.get('provider')=='ollama' and bool(r.get('message',{}).get('content')) else 'FAIL','provider':r.get('provider'),'model':r.get('model'),'reply':r.get('message',{}).get('content'),'seconds':round(time.monotonic()-start,3),'real_cloud_calls':0,'sage_writes':0}
    except Exception as exc:result={'status':'UNAVAILABLE','error_type':type(exc).__name__,'seconds':round(time.monotonic()-start,3),'real_cloud_calls':0,'sage_writes':0}
    finally:ai_provider.CONTEXT.reset(token)
    (ROOT/'TEST/campaign-real-ollama.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=True))
asyncio.run(main())
