"""User confirmation is an equation; sole site 202 has no supplier requirement."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client
messages=[
 'Créer article EQUATION SITE202 VERIFICATION, catégorie GEN, unité de stock UN, unité de vente L, coefficient 1000, site 202, code comptable BETON.',
 '1 UN = 1000 L',
 "j’ai confirlmer 1 UN = 1000 L",
 '1 L = 1 UN = 1000 L',
 'Unité de stock est UN ET DE VENTe est UN',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as c:
 account=authenticate_test_client(c);c.headers['X-Chat-CSRF']=account['csrf']
 r=c.post('/api/v1/chat/conversations');r.raise_for_status();s=r.json();identifier=None
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+s['id']+'/analysis-jobs'
  r=c.post(path,json={'content':message,'revision':s['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];start=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-start>210:raise RuntimeError('Observation deadline; no resubmission')
   time.sleep(1);r=c.get(path+'/'+job);r.raise_for_status();v=r.json()
  s=v['conversation'];a=s['state']['articles'][0];op=a['operation']
  entry={'message':message,'reply':s['messages'][-1]['content'],'coefficient':a.get('coefficient_vente_declare'),'equation':a.get('conversion_vente_declaree'),'stock':a.get('unite'),'sale':a.get('unite_vente'),'sites':a.get('requested_sites'),'suppliers':a.get('fournisseurs'),'flag':a.get('flag_fournisseur'),'status':op['status']}
  report['steps'].append(entry)
  Path(__file__).with_name('creation-equation-site202-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and not a.get('approved') and (not identifier or identifier==a['id']);identifier=a['id']
  assert 'Appel non validé' not in entry['reply']
  if index in (1,2):
   assert a['coefficient_vente_declare']=='1000' and a['conversion_vente_declaree']['source_unit']=='UN'
   assert 'Le sens est connu' in entry['reply'] and 'Voulez-vous dire' not in entry['reply']
  if index==3:assert 'une seule égalité' in entry['reply'] and a['coefficient_vente_declare']=='1000'
  if index==4:
   assert op['status']=='prepared' and not op['preview']['executed']
   assert not a.get('fournisseurs') and a['flag_fournisseur']=='1' and not op['summary']['principal']
 print('PASS: equation does not loop; invalid chain rejected; sole 202 prepares without supplier; no Sage writes.',flush=True)
