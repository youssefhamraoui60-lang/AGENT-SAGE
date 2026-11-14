"""Real TEST/DeepSeek conversation; analysis only, no approval or Sage write."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client

messages=['Créer article ESSAI FOURNISSEURS MULTIPLES, catégorie GEN, unité UN, site 201, code comptable BETON.', 'Recherchez le fournisseur Cimat et proposez les correspondances à rattacher à cet article.', 'les deux']
base='http://127.0.0.1:8000';report={'sage_writes':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as client:
 account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
 r=client.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json()
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=client.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];started=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline; no resubmission')
   time.sleep(1);r=client.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];a=session['state']['articles'][0];reply=session['messages'][-1]['content']
  entry={'message':message,'reply':reply,'suppliers':a.get('fournisseurs'),'status':a.get('operation',{}).get('status'),'provider':session['state'].get('tool_orchestration',{}).get('provider')}
  report['steps'].append(entry);Path(__file__).with_name('both-suppliers-conversation-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and not a.get('approved')
  if index==1:assert 'F007' in reply and 'F552' in reply and '?' in reply
  if index==2:assert {p['code'] for p in a['fournisseurs']}=={'F007','F552'}
 print('PASS: both verified candidates retained on one draft; no Sage write.',flush=True)
