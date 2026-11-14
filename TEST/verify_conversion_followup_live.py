"""Existing TEST article, real DeepSeek then literal follow-ups. No approval."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client
messages=[
 'Je veux modifier les unités de l’article existant NEG_CAF_778XT8_3XLL.',
 'unités dois m2 et le vente dois RLX',
 'le cofission est 1000 POUR UN VERe RLX',
 'conversion 1000',
 '1M2 = 1000 UN',
 '1 UN = 1000 RLX',
 '1 UN = 1000 M2',
 'corrige : 1 UN = 1000 M2',
 'je veux corriger la UN de mon articele',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as c:
 account=authenticate_test_client(c);c.headers['X-Chat-CSRF']=account['csrf']
 r=c.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json();draft_id=None
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs';started=time.monotonic()
  r=c.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id']
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline; no resubmission')
   time.sleep(1);r=c.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];s=session['state'];d=(s.get('modification_drafts') or [{'id':None,'changes':{},'operation':{'status':'not_prepared'}}])[-1]
  entry={'step':index+1,'message':message,'reply':session['messages'][-1]['content'],'elapsed_seconds':round(time.monotonic()-started,2),'provider':s.get('tool_orchestration',{}).get('provider'),'draft_id':d['id'],'changes':d['changes'],'conversions':d.get('unit_conversion_requests',[]),'status':d['operation']['status']}
  report['steps'].append(entry)
  Path(__file__).with_name('conversion-followup-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and not d.get('approved')
  if index==0:continue
  assert len(s['modification_drafts'])==1
  assert not draft_id or draft_id==d['id'];draft_id=d['id']
  if index>=1:assert d['changes']['stock_unit']=='M2' and d['changes']['sale_unit']['code']=='RLX'
  if index in (2,3):
   conversion=d['unit_conversion_requests'][-1]
   assert (conversion['coefficient'],conversion['source_unit'],conversion['target_unit'])==('1000','UN','RLX')
   assert '1 RLX = 1000 UN' in entry['reply'] and '1 UN = 1000 RLX' in entry['reply']
  if index==4:assert d['unit_conversion_requests'][-1]['status']=='declared_equivalence' and 'blocage est technique' in entry['reply']
  if index==5:assert 'reste à préciser' not in entry['reply']
  if index==6:assert d['unit_conversion_conflicts'] and 'contredit' in entry['reply']
  if index==7:assert not d['unit_conversion_conflicts'] and 'blocage est technique' in entry['reply']
  if index==8:assert 'stock UN' in entry['reply']
  assert 'Appel non validé' not in entry['reply']
 r=c.get('/api/v1/chat/conversations/'+session['id']+'/operation-state.json');r.raise_for_status()
 assert r.json()['operations'][-1]['unit_conversion_requests'][-1]['status']=='declared_equivalence'
 print('PASS: same target, both units, coefficient persisted, explicit direction question, JSON export; no Sage writes.',flush=True)
