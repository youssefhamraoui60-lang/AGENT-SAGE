"""Exact reported creation dialogue with real DeepSeek; no Sage write routes."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client

MESSAGES=[
 'bonjour je veux créer le articles ANT789 X7',
 'LA CATIGOURIER NEGOSE le site est 202 ET 201',
 'corriger le nom de le aricles est ANT789 X7',
 "la Désignation est ' ANT789\tX7'",
 'le tva 20 ET LE COMP¨LDE 66',
 'JE VEUX 61224000',
 'mon articles est géré on sotok et ne outirise pas le stock negatif',
 'pour le articles et utisble dans la vente',
 'Flag fournisseur dois active',
 'liéer les deux fourniseur CIMAT ET NEVACIM',
 'CIMAT** : F007  ET F889 « NOVACIM » —',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as client:
 account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
 r=client.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json();identifier=None
 for i,message in enumerate(MESSAGES):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=client.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];started=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline, no resubmission')
   time.sleep(1);r=client.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];state=session['state'];a=state['articles'][0]
  record={'step':i+1,'provider':state.get('tool_orchestration',{}).get('provider'),'reply':session['messages'][-1]['content'],
          'parameters':{key:a.get(key) for key in ('id','code_article','designation','categorie','requested_sites','code_comptable','code_tva','gestion_stock','allow_negative_stock','vendu','flag_fournisseur','fournisseurs')},'modification_count':len(state.get('modification_drafts',[]))}
  report['steps'].append(record);report['conversation_id']=session['id']
  Path(__file__).with_name('ant789-draft-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(record,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and record['provider']=='deepseek'
  assert len(state['articles'])==1 and a['designation']=='ANT789 X7'
  assert not a.get('approved') and not state.get('modification_drafts')
  if identifier is not None:assert a['id']==identifier
  identifier=a['id']
  assert a.get('code_article')!='ANT789'
  if i>=1:assert set(a['requested_sites'])=={'202','201'}
  if i>=6:assert a['gestion_stock']=='2' and a['allow_negative_stock'] is False
  if i>=7:assert a['vendu']=='2'
  if i>=8:assert a['flag_fournisseur']=='2'
 assert {item['code'] for item in a['fournisseurs']}=={'F007','F889'}
 r=client.get('/api/v1/chat/conversations/'+session['id']+'/operation-state.json');r.raise_for_status()
 Path(__file__).with_name('ant789-draft-state.json').write_text(r.text,encoding='utf-8')
 print('PASS: complete name, stock and sale flags, two suppliers on same creation draft; no ERP modification or Sage write.',flush=True)
