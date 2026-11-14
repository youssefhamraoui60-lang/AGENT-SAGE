"""Real loopback FastAPI/Qwen/SQL latency, cold model vs warm; never Sage writes."""
import argparse,asyncio,json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
INPUTS={1:'Crée un article Ciment CPJ35, catégorie NEG, unité SAC, pour le site 201.',
2:"Bonjour, j'ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR.",
10:'Créer les 10 articles suivants, site 201 :\n'+'\n'.join(f'{i}. Panneau performance {i}, catégorie {"AR" if i%2 else "NEG"}, unité {"M2" if i%2 else "UN"}.' for i in range(1,11))}
async def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--stream',action='store_true');args=p.parse_args()
 result={'label':args.label,'sage_writes':0,'sql_data':'REAL_TEST_SELECT','cold_definition':'Ollama model unloaded; Windows disk cache not flushed','cases':[]}
 file=ROOT/'logs'/('chat-performance-'+args.label+'.json')
 async with httpx.AsyncClient(timeout=600,trust_env=False,headers={'Origin':'http://127.0.0.1:8000'}) as client:
  session=await client.post('http://127.0.0.1:8000/api/v1/chat/session');session.raise_for_status();client.headers['X-Chat-CSRF']=session.json()['csrf']
  for count,text in INPUTS.items():
   for mode in ['cold','warm']:
    case={'articles':count,'mode':mode,'status':'RUNNING'}
    try:
     if mode=='cold':
      models=(await client.get('http://127.0.0.1:11434/api/tags')).json()['models'];name=next(m['name'] for m in models if m['name'].startswith('qwen2.5:7b'))
      unload=await client.post('http://127.0.0.1:11434/api/generate',json={'model':name,'keep_alive':0});unload.raise_for_status()
     c=(await client.post('http://127.0.0.1:8000/api/v1/chat/conversations')).json();start=time.perf_counter();first=None;useful=None;value=None;events=[]
     suffix='/messages/stream' if args.stream else '/messages'
     async with client.stream('POST',f"http://127.0.0.1:8000/api/v1/chat/conversations/{c['id']}"+suffix,json={'content':text,'revision':c['revision']}) as response:
      response.raise_for_status()
      if args.stream:
       async for line in response.aiter_lines():
        if not line.startswith('data: '):continue
        event=json.loads(line[6:]);now=(time.perf_counter()-start)*1000
        if first is None:first=now
        events.append({'event':event['event'],'at_ms':round(now,3)})
        if event['event'] in ['understanding','text'] and useful is None:useful=now
        if event['event']=='result':value=event['data']
        if event['event']=='error':raise ValueError(event['data'])
      else:
       chunks=[]
       async for chunk in response.aiter_bytes():
        if first is None:first=(time.perf_counter()-start)*1000
        chunks.append(chunk)
       value=json.loads(b''.join(chunks));useful=first
     case.update(http_total_ms=round((time.perf_counter()-start)*1000,3),first_response_ms=round(first,3),first_useful_ms=round(useful,3),events=events)
     assert len(value['state']['articles'])==count,('article_count',len(value['state']['articles']))
     case.update(status='PASS',performance=value.get('performance'),conversation_id=value['id'])
     last=[m for m in value['messages'] if m['role']=='assistant'][-1]
     case['model_provenance']=last['payload'].get('provenance');case['drafts']=value['state']['articles']
    except Exception as e:case.update(status='FAILED',error_type=type(e).__name__,error=str(e)[:400])
    result['cases'].append(case);file.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(args.label,count,mode,case['status'],case.get('http_total_ms'),case.get('error',''),flush=True)
if __name__=='__main__':asyncio.run(main())
