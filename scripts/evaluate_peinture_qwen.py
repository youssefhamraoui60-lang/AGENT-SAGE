"""Real local Qwen, forced narrow extraction; no Sage/SQL call."""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from app.services import chat_model as model,conversation_chat as chat,chat_performance as perf
from test_peinture_creation import SHORT,EXACT

async def main():
 results=[]
 for text in [SHORT,EXACT]:
  token=model.FORCE_AI.set(True);metrics={};mt=perf.CURRENT.set(metrics);started=time.perf_counter()
  r={'message':text,'real_qwen':True,'sage_writes':0}
  try:
   delta,trace=await model.extract(text,{'articles':[]},[]);state=chat.merge({'articles':[]},delta,text)
   a=state['articles'][0] if len(state.get('articles',[]))==1 else {}
   expected={'designation':'PEINTURE ACRYLIQUE BLANCHE 20 KG','categorie':'NEG','unite':'UN','site':'201','taux_tva':'20','gestion_stock':'1'}
   r.update(passed=all(a.get(k)==v for k,v in expected.items()) and trace['real_model_called'],delta=delta.model_dump(exclude_unset=True),trace=trace)
  except Exception as exc:r.update(passed=False,error_type=type(exc).__name__)
  finally:model.FORCE_AI.reset(token);perf.CURRENT.reset(mt)
  r.update(seconds=round(time.perf_counter()-started,3),metrics=metrics);results.append(r)
  (ROOT/'tests/ai-evaluation/reports/peinture-real-qwen.json').write_text(json.dumps({'mode':'REAL_QWEN_NO_SAGE_WRITE','results':results},ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'case':len(results),'passed':r['passed'],'seconds':r['seconds']}),flush=True)
 return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
