"""Forced real Ollama extraction; no SQL, SOAP or Sage write."""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_model as model,conversation_chat as chat,chat_performance as perf

CASES=["Je veux créer l'article CPJ345 Y45 dans le système, catégorie NEG, TVA 10.",
       "je veux créer l'articles CPJ345 Y45 dasn le systéme avce la catigorier NEG et le TVA 10",
       "Créer un article CPJ345 Y45, catégorie NEG, unité UN, site 201, TVA 10"]

async def main():
 results=[]
 for message in CASES:
  token=model.FORCE_AI.set(True);metrics={};mt=perf.CURRENT.set(metrics);started=time.perf_counter()
  result={'message':message,'real_qwen':True,'sage_writes':0}
  try:
   delta,trace=await model.extract(message,{'articles':[]},[])
   state=chat.merge({'articles':[]},delta,message);articles=state.get('articles',[]);a=articles[0] if len(articles)==1 else {}
   expected={'designation':'CPJ345 Y45','categorie':'NEG','taux_tva':'10','unite':'UN' if 'unité UN' in message else None}
   passed=all(a.get(k)==v for k,v in expected.items()) and a.get('gestion_stock') is None and trace.get('real_model_called') is True
   result.update(passed=passed,expected=expected,delta=delta.model_dump(exclude_unset=True),trace=trace,rejected_values=state.get('rejected_values',[]))
  except Exception as exc:result.update(passed=False,error_type=type(exc).__name__)
  finally:model.FORCE_AI.reset(token);perf.CURRENT.reset(mt)
  result.update(seconds=round(time.perf_counter()-started,3),metrics=metrics);results.append(result)
  (ROOT/'tests/ai-evaluation/reports/cpj345-real-qwen.json').write_text(json.dumps({'mode':'REAL_QWEN_EXTRACTION_NO_ERP_WRITES','results':results},ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'case':len(results),'passed':result['passed'],'seconds':result['seconds']}),flush=True)
 return 0 if all(x['passed'] for x in results) else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
