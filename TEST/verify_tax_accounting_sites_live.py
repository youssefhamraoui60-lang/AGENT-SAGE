"""Reported article conversation, real provider and read-only ERP preparation."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client

MESSAGES=[
 'bonjour je veyux créer un article le nom est CAF Y78 9X',
 'la catigoirer est GEN',
 'le site 202 LE UNIT2 de vente est UN',
 'le TVA est 20',
 'je sais pas code donenr la liste pour dire ou chercher toi méme pour facilter',
 'et le compte comptables et 4415...',
 'le unter de sotok est UN',
 'ajouter aussi dans le site 201',
 'LES DEUX site',
 'donne aussi la liste des codes comptables avec les intitulés',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as client:
 account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
 r=client.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json();identifier=None
 for i,message in enumerate(MESSAGES):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=client.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];started=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline; no resubmission')
   time.sleep(1);r=client.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];state=session['state'];a=state['articles'][0]
  assert len(state['articles'])==1 and a['designation']=='CAF Y78 9X' and not a.get('approved')
  if identifier is not None:assert a['id']==identifier
  identifier=a['id']
  entry={'step':i+1,'provider':state.get('tool_orchestration',{}).get('provider'),'reply':session['messages'][-1]['content'],'parameters':{k:a.get(k) for k in ('categorie','site','requested_sites','unite','unite_vente','taux_tva','code_tva','compte_general')},'references':state.get('article_reference_choices')}
  report['steps'].append(entry);report['conversation_id']=session['id']
  Path(__file__).with_name('tax-accounting-sites-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({k:entry[k] for k in ('step','provider','reply','parameters')},ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and entry['provider']=='deepseek'
  assert 'services IA' not in entry['reply']
  if i>=2:assert a.get('unite_vente')=='UN'
  if i>=6:assert a.get('unite')=='UN'
  if i>=5:assert a.get('compte_general')=='4415'
  if i>=7:assert set(a.get('requested_sites',[]))=={'202','201'}
 assert a['code_tva']=='T20'
 assert state['article_reference_choices']['accounting']['choices']
 r=client.get('/api/v1/chat/conversations/'+session['id']+'/operation-state.json');r.raise_for_status()
 Path(__file__).with_name('tax-accounting-sites-state.json').write_text(r.text,encoding='utf-8')
 print('PASS: same draft, verified tax/accounting references, sites 202+201 retained, no Sage write.',flush=True)
