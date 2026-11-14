"""Real local Qwen extraction only. No SQL, SOAP, or Sage writes."""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_model as model,conversation_chat as chat,chat_performance as perf

CASES=[
 'Bonjour, merci de créer un fournisseur :\nDROGUERIE PALMERAIE\nICE : 001850814000094\nIF : 20734927\nRC : 10909',
 'Créer un fournisseur : NOM : DROGUERIE PALMERAIE ICE : 001850814000094 IF : 20734927 RC : 10909 Activation : OUI Catégorie : FR Pays : MA Devise : MAD',
 'Bonjour, merci de créer un fournisseur : NOM : FOURNISSEUR SYNTHETIQUE ALPHA ICE : 001850814000094 IF : 20734927 RC : 10909',
]

async def main():
 results=[]
 for message in CASES:
  token=model.FORCE_AI.set(True);metrics={};mt=perf.CURRENT.set(metrics);started=time.perf_counter()
  result={'message':message,'real_qwen':True,'sage_writes':0}
  try:
   delta,trace=await model.extract(message,{'articles':[]},[])
   result['delta']=delta.model_dump(exclude_unset=True)
   state=chat.merge({'articles':[]},delta,message);p=state.get('partners',[{}])[0]
   name='FOURNISSEUR SYNTHETIQUE ALPHA' if 'SYNTHETIQUE' in message else 'DROGUERIE PALMERAIE'
   passed=all(p.get(k)==v for k,v in {'nom':name,'ice':'001850814000094','identifiant_fiscal':'20734927','rc':'10909'}.items()) and not p.get('code') and not p.get('code_comptable')
   if 'Activation' in message:passed=passed and p.get('statut','').casefold() in ('actif','oui')
   result.update(passed=passed,delta=delta.model_dump(exclude_unset=True),trace=trace,rejected_values=state.get('rejected_values',[]))
  except Exception as exc:
   result.update(passed=False,error_type=type(exc).__name__)
   if hasattr(exc,'errors'):result['validation_errors']=[{'loc':e['loc'],'type':e['type']} for e in exc.errors()]
  finally:model.FORCE_AI.reset(token);perf.CURRENT.reset(mt)
  result.update(seconds=round(time.perf_counter()-started,3),metrics=metrics);results.append(result)
  (ROOT/'tests/ai-evaluation/reports/supplier-activation-real-qwen.json').write_text(json.dumps({'mode':'REAL_QWEN_EXTRACTION_NO_ERP_WRITES','results':results},ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'case':len(results),'passed':result['passed'],'seconds':result['seconds']}),flush=True)
 return 0 if all(x['passed'] for x in results) else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
