"""Real DeepSeek and TEST creation previews; never approve or execute."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client
messages=[
 'Créer un article REGLE FOURNISSEUR ESSAI, catégorie GEN, unité M3, site 201, code comptable BETON.',
 'Rattache les trois fournisseurs F007 CIMAT, F552 CIMAT BETON et F889 NOVACIM, sans fournisseur principal.',
 'fournisseur principal : F007 (CIMAT',
]
base='http://127.0.0.1:8000';report={'sage_write_routes_called':0,'steps':[]}
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as c:
 account=authenticate_test_client(c);c.headers['X-Chat-CSRF']=account['csrf']
 r=c.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json();identifier=None
 for index,message in enumerate(messages):
  path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
  r=c.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())});r.raise_for_status();v=r.json();job=v['job']['id'];started=time.monotonic()
  while v['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
   if time.monotonic()-started>210:raise RuntimeError('Observation deadline, no resubmission')
   time.sleep(1);r=c.get(path+'/'+job);r.raise_for_status();v=r.json()
  session=v['conversation'];s=session['state'];a=s['articles'][0];op=a['operation']
  entry={'step':index+1,'reply':session['messages'][-1]['content'],'provider':s.get('tool_orchestration',{}).get('provider'),'status':op['status'],'flag':a.get('flag_fournisseur'),'principal':a.get('fournisseur_principal') or (op.get('summary') or {}).get('principal'),'suppliers':a.get('fournisseurs'),'preview':op.get('preview')}
  report['steps'].append(entry)
  Path(__file__).with_name('supplier-sale-rule-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(entry,ensure_ascii=True),flush=True)
  assert v['job']['status']=='completed' and entry['provider']=='deepseek' and not a.get('approved')
  assert not identifier or identifier==a['id'];identifier=a['id']
  assert a['flag_fournisseur']=='2'
  if index==0:assert op['status']=='blocked' and 'au moins un fournisseur' in op['message']
  else:
   assert op['status']=='prepared' and not op['preview']['executed']
   assert {p['code'] for p in a['fournisseurs']}=={'F007','F552','F889'}
  if index==1:assert not entry['principal']
  if index==2:assert entry['principal']=='F007'
 print('PASS: supplier mandatory for sales, flag automatic, principal optional or explicit, real previews only.',flush=True)
