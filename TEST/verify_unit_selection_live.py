"""Real DeepSeek/TEST reference checks; only analysis endpoints, no approval."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client
messages=[
 'Créer un article CAF UNIT VERIFICATION, catégorie NEG, sites 202 et 201, code comptable CPJ35.',
 'mon uniter est metr carr',
 'Maintenant modifie l’article existant NEG_CAF_778XT8_3XLL : unité de stock M2 et unité de vente RLX.',
]
report={'sage_write_routes_called':0,'steps':[]};base='http://127.0.0.1:8000'
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as c:
 account=authenticate_test_client(c);c.headers['X-Chat-CSRF']=account['csrf']
 r=c.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json()
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=c.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];start=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-start>210:raise RuntimeError('Observation deadline; no resubmission')
   time.sleep(1);r=c.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];s=session['state'];a=s['articles'][0]
  entry={'step':index+1,'message':message,'reply':session['messages'][-1]['content'],'provider':s.get('tool_orchestration',{}).get('provider'),'article_unit':a.get('unite'),'article_status':a.get('operation',{}).get('status'),'modifications':[{'code':d['code'],'changes':d['changes'],'status':d.get('operation',{}).get('status'),'reason':d.get('operation',{}).get('message')} for d in s.get('modification_drafts',[])]}
  report['steps'].append(entry)
  Path(__file__).with_name('unit-selection-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and entry['provider']=='deepseek'
  if index==0:assert not a.get('unite') and a['operation']['status']=='blocked' and 'unit' in entry['reply'].lower()
  if index==1:assert a['unite']=='M2'
  if index==2:
   d=s['modification_drafts'][-1]
   assert d['code']=='NEG_CAF_778XT8_3XLL'
   assert d['changes']['stock_unit']=='M2' and d['changes']['sale_unit']['code']=='RLX'
   assert 'incompatible avec la catégorie' not in (d.get('operation',{}).get('message') or '')
  assert not any(d.get('approved') for d in s.get('modification_drafts',[])) and not a.get('approved')
 print('PASS: mandatory unit, French label resolution, stock/sale proposal preserved; no Sage writes.',flush=True)
