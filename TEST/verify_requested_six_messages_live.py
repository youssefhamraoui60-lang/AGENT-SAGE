"""Replay reported session as read/draft requests, never approves any Sage write."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client

MESSAGES=[
 'Merci de créer les articles suivants : Polo/U/FG/MIDO PUB MAROC S.A.R.L Casquette/U/FG/MIDO PUB MAROC S.A.R.L Gilet/U/FG/MIDO PUB MAROC S.A.R.L Blouse/U/FG/MIDO PUB MAROC S.A.R.L T-shirt/U/FG/MIDO PUB MAROC S.A.R.L Ensemble veste et pantalon /U/FG/MIDO PUB MAROC S.A.R.L',
 'Bonsoir Merci de créer cet article : DRENTEX 400 * 3M*2M/ RLX / AR/ SOPREMA',
 'Bonsoir, Merci de bien vouloir modifier toutes les unités des articles Technoseal en Rlx. Je vous remercie par avance pour votre retour. Cordialement,',
 'MERCI DE CREER CET ARTICLE : POLYSTYRENE 60*60*25/ UNITE/ AR / fournisseur : ISONIMA',
 'Merci de créer le fournisseur suivant : DELTA BUREAU ICE : 000102081000068 IF : 01007203 TEL : 05 22 09 00 01',
 'BONJOUR MERCI DE CREER CET ARTICLE : TELEPHONE PORTABLE / ALLO FOURNI/ UNITE',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as client:
 account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
 r=client.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json();report['conversation_id']=session['id']
 for i,message in enumerate(MESSAGES):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=client.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();value=r.json();job=value['job']['id'];started=time.monotonic()
  while value['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline, no resubmission')
   time.sleep(1);r=client.get(path+'/'+job);r.raise_for_status();value=r.json()
  session=value['conversation'];state=session['state'];orchestration=state.get('tool_orchestration') or {}
  entry={'step':i+1,'message':message,'status':value['job']['status'],'provider':orchestration.get('provider'),'reply':session['messages'][-1]['content'],
         'articles':[{k:a.get(k) for k in ('id','designation','categorie','categorie_libelle','unite','fournisseur_nom')} for a in state.get('articles',[])],
         'suppliers':[{k:p.get(k) for k in ('id','nom','ice','identifiant_fiscal','telephone')} for p in state.get('partners',[])],
         'diagnostics':orchestration,'context':state.get('operation_context')}
  report['steps'].append(entry)
  Path(__file__).with_name('requested-six-messages-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({k:entry[k] for k in ('step','status','provider','reply','articles','suppliers')},ensure_ascii=True),flush=True)
  assert not any(item.get('approved') for key in ('partners','articles','modification_drafts') for item in state.get(key,[]))
  assert value['job']['status']=='completed' and orchestration.get('provider')=='deepseek'
  assert 'services IA' not in entry['reply']
  if i==0:
   assert [a['designation'] for a in state['articles']]==['Polo','Casquette','Gilet','Blouse','T-shirt','Ensemble veste et pantalon']
   assert all(a['unite']=='UN' and a['categorie']=='FG' for a in state['articles'])
  if i==1:assert state['articles'][-1]['designation']=='DRENTEX 400 * 3M*2M'
  if i==2:
   assert state['batch_modification_requests'][0]['query']=='Technoseal'
   assert state['batch_modification_requests'][0]['unit']=='RLX'
   assert all(a['unite']=='UN' for a in state['articles'][:6])
  if i==3:assert state['articles'][-1]['unite']=='UN'
  if i==4:
   p=state['partners'][0]
   assert p['nom']=='DELTA BUREAU' and p['identifiant_fiscal']=='01007203' and p['telephone']=='05 22 09 00 01'
  if i==5:
   assert len(state['articles'])==9
   assert state['articles'][-1]['designation']=='TELEPHONE PORTABLE' and state['articles'][-1]['fournisseur_nom']=='ALLO FOURNI' and state['articles'][-1]['unite']=='UN'
   assert not session['messages'][-1]['payload'].get('supplier_snapshots')
 r=client.get('/api/v1/chat/conversations/'+session['id']+'/operation-state.json');r.raise_for_status()
 Path(__file__).with_name('requested-six-messages-state.json').write_text(r.text,encoding='utf-8')
