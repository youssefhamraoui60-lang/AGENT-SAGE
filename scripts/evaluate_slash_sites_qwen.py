"""Real forced Qwen extraction only; never calls SQL or Sage."""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_model as model,conversation_chat as chat,chat_performance as perf
TEXT="Bonjour,\nMerci de créer ce nouvel article dans Sage X3 :\n\n**PEINTURE ACRYLIQUE BLANCHE 20 KG / UN / Catégorie : NEG / TVA : 20 % / Site : 201  et 209/ Article non géré en stock.\n\nMerci de proposer un code article et de vérifier qu'il n'existe pas déjà.\n\nCordialement."

async def main():
 results=[]
 for text in (TEXT,TEXT.replace('**','').replace('201  et 209','209 et 201')):
  t=model.FORCE_AI.set(True);metrics={};mt=perf.CURRENT.set(metrics);started=time.perf_counter();r={'message':text,'sage_writes':0,'real_qwen':True}
  try:
   d,trace=await model.extract(text,{'articles':[]},[]);s=chat.merge({'articles':[]},d,text);a=s['articles'][0] if len(s['articles'])==1 else {}
   sites=['209','201'] if '209 et 201' in text else ['201','209']
   expected={'designation':'PEINTURE ACRYLIQUE BLANCHE 20 KG','categorie':'NEG','unite':'UN','site':sites[0],'requested_sites':sites,'gestion_stock':'1','taux_tva':'20','accounting_category':None}
   r.update(passed=all(a.get(k)==v for k,v in expected.items()) and trace['real_model_called'],delta=d.model_dump(exclude_unset=True),trace=trace,actual={k:a.get(k) for k in expected})
  except Exception as e:
   r.update(passed=False,error_type=type(e).__name__)
   if hasattr(e,'errors'):r['validation_errors']=e.errors()
  finally:model.FORCE_AI.reset(t);perf.CURRENT.reset(mt)
  r.update(seconds=round(time.perf_counter()-started,3),metrics=metrics);results.append(r)
  (ROOT/'tests/ai-evaluation/reports/slash-sites-real-qwen.json').write_text(json.dumps({'mode':'REAL_QWEN_NO_SAGE_WRITE','results':results},ensure_ascii=False,indent=2,default=str),encoding='utf8')
  print(json.dumps({'case':len(results),'passed':r['passed'],'seconds':r['seconds']}),flush=True)
 return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
