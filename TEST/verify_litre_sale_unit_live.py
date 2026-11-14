"""Real DeepSeek exact litre lookup and preservation of declared sale units."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client
messages=[
 'Créer article LITRE UNIT REGRESSION, catégorie GEN, unité de stock UN, site 202, fournisseur F007, code comptable BETON.',
 'le unter UN dans le vent L LA COFSSION EST 1000',
 'OUI MAIS POUR LE VENT litre',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as c:
 account=authenticate_test_client(c);c.headers['X-Chat-CSRF']=account['csrf']
 r=c.post('/api/v1/chat/conversations');r.raise_for_status();s=r.json();identifier=None
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+s['id']+'/analysis-jobs'
  r=c.post(path,json={'content':message,'revision':s['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];started=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline, no resubmission')
   time.sleep(1);r=c.get(path+'/'+job);r.raise_for_status();v=r.json()
  s=v['conversation'];a=s['state']['articles'][0]
  entry={'message':message,'reply':s['messages'][-1]['content'],'stock_unit':a.get('unite'),'sale_unit':a.get('unite_vente'),'coefficient':a.get('coefficient_vente_declare'),'status':a['operation']['status'],'principal':a.get('fournisseur_principal'),'provider':s['state'].get('tool_orchestration',{}).get('provider')}
  report['steps'].append(entry)
  Path(__file__).with_name('litre-sale-unit-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and not a.get('approved') and (not identifier or identifier==a['id']);identifier=a['id']
  assert a['unite']=='UN' and not entry['principal']
  if index>=1:assert a['unite_vente']=='L' and a['coefficient_vente_declare']=='1000'
  assert 'Appel non validé' not in entry['reply']
 print('PASS: stock UN, sale L, coefficient 1000 preserved; optional principal at 202; no Sage writes.',flush=True)
