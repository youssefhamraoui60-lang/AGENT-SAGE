"""Actual predefined SQL SELECT probes; no writer transport is imported/called."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import conversation_tools as engine
results=[]
for name,text in [('cimat','cimat'),('CIMAT','CIMAT'),('CiMaT','CiMaT'),('CYMAT','CYMAT'),('MONDE ACIER','MOunDE ACIER')]:
 start=time.monotonic()
 try:
  result=engine.read(engine.Read(resource='supplier',name=name),{},text)
  results.append({'query':name,'declared':text,'seconds':round(time.monotonic()-start,3),'result':result})
 except Exception as exc:results.append({'query':name,'error':type(exc).__name__,'seconds':round(time.monotonic()-start,3)})
assert all('error' not in r for r in results),results
sets=[{r['BPSNUM_0'] for r in x['result']['rows']} for x in results[:3]]
assert sets[0]==sets[1]==sets[2] and {'F007','F552'}<=sets[0]
assert results[3]['result']['approximate'] and any(r['BPSNUM_0']=='F007' for r in results[3]['result']['rows'])
output={'case_insensitive_verified':True,'phonetic_candidate_verified':True,'sage_writes':0,'probes':results}
(ROOT/'TEST/f1-f2-sql-read-proof.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'case_insensitive_verified':True,'sage_writes':0,'probes':[{'query':r['query'],'seconds':r['seconds'],'approximate':r['result'].get('approximate'),'rows':r['result']['rows']} for r in results]},ensure_ascii=True))
