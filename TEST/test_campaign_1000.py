"""1000 independent multi-turn FastAPI conversations, real isolated PostgreSQL.

All external AI and Sage transports fail closed or return labelled fixtures.
The actual parsers, routing, state merges, plan builders and access checks run.
"""
import sys,os,json,copy,time,hashlib,subprocess
from pathlib import Path
from uuid import UUID,uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
import pytest,httpx,psycopg
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from fastapi.testclient import TestClient
from test_conversation_chat import fixture,create,FakeSQL
from test_modifications import simulated
from app.core.config import settings
from app.services import conversation_chat as chat,chat_tools,supplier_sql,article_sql,erp_modification as mod,modification_dialogue,ai_provider,business_store as db
from campaign_1000 import corpus

def get(value,path):
 for key in path.split('.'):
  try:value=value[int(key)] if isinstance(value,list) else value[key]
  except (KeyError,IndexError,TypeError,ValueError):return '<MISSING>'
 return value

@pytest.fixture
def campaign(fixture,simulated,monkeypatch):
 c,_=fixture;schema,article,supplier,_=simulated
 current={};calls=[];attempts=[];wire=[]
 monkeypatch.setattr(settings,'sage_powershell_chat_enabled',False)
 monkeypatch.setattr(settings,'sage_article_sql_enabled',True)
 monkeypatch.setattr(settings,'sage_mcp_enabled',False)
 monkeypatch.setattr(settings,'conversation_analysis_enabled',False)
 monkeypatch.setattr(settings,'deepseek_api_key',SecretStr('test-campaign-not-a-real-key'))
 monkeypatch.setattr(settings,'ai_daily_budget_usd',100)
 defaults=json.loads((ROOT/'TEST/supplier.example.json').read_text(encoding='utf-8'));defaults.update(Telephone='',Fax='',TypeLibelle='HT',TypeMontant=1,Paiement='CHQ00')
 monkeypatch.setattr(supplier_sql,'load_defaults',lambda *a:copy.deepcopy(defaults))
 monkeypatch.setattr(supplier_sql,'load_reference_labels',lambda *a:[{'kind':'Paiement','label':'cheque 30 jours','code':'CHQ30'},{'kind':'Paiement','label':'effet 60 jours','code':'EFF60'},{'kind':'Pays','label':'Maroc','code':'MA'}])
 monkeypatch.setattr(supplier_sql,'security',lambda *a,**k:{'ready':True,'blockers':[],'folder':'TEST'})
 monkeypatch.setattr(chat,'supplier_security',lambda *a,**k:{'ready':True,'blockers':[],'folder':'TEST'})
 def supplier_run(values,execute=False,**kw):
  attempts.append({'transport':'supplier','execute':execute});assert not execute,'FORBIDDEN SAGE WRITE'
  return {'ok':True,'folder':'TEST','rows':[{'RESULTAT':'VALIDATED_NO_INSERT','CODE_PROPOSE_NON_RESERVE':'F99999'}]}
 monkeypatch.setattr(supplier_sql,'run',supplier_run)
 def article_transport(action,plan=None,execute=False,**kw):
  attempts.append({'transport':'article','execute':execute});assert not execute,'FORBIDDEN SAGE WRITE'
  return {'ok':True,'folder':'TEST','transaction_state':'VALIDATED_NO_INSERT','executed':False,'records':[]}
 monkeypatch.setattr(article_sql,'transport',article_transport)
 def mod_transport(action,resource='',code='',plan=None,execute=False):
  attempts.append({'transport':'modification','execute':execute});assert not execute,'FORBIDDEN SAGE WRITE'
  return {'ok':True,'folder':'TEST','transaction_state':'VALIDATED_NO_WRITE','executed':False,'verified':False,'affected':0}
 monkeypatch.setattr(mod,'transport',mod_transport)
 def snapshot(resource,code):
  view=copy.deepcopy(supplier if resource=='supplier' else article);old='F994' if resource=='supplier' else 'TESTART201'
  def replace(x):
   if isinstance(x,dict):return {k:replace(v) for k,v in x.items()}
   if isinstance(x,list):return [replace(v) for v in x]
   return code if x==old else x
  view=replace(view);view.update(resource=resource,code=code)
  if current.get('fault')=='used':view['dependencies']={'complete':True,'sources':[{'tab':'SORDERQ','readable':True,'has_matches':True,'active':True}]}
  return view
 monkeypatch.setattr(mod,'snapshot',snapshot)
 monkeypatch.setattr(modification_dialogue,'read_current_record',lambda resource,code:__import__('app.services.modification_actions',fromlist=['current_values']).current_values(snapshot(resource,code)))
 def tools(requests):
  out={}
  for request in requests:
   calls.append(copy.deepcopy(request));args=request['args'];tool=request['tool'];rows=[]
   if current.get('fault')=='sql':raise __import__('app.services.sage_crud',fromlist=['CrudError']).CrudError('Lecture SQL simulée indisponible ; aucune écriture.',423)
   if tool=='get_supplier_record':
    code=args['Supplier'];rows=[{'folder':'TEST','BPSNUM_0':code,'BPRNUM_0':code,'BPRNAM_0':'FOURNISSEUR '+code,'supplier_active':1,'partner_active':1}]
   elif tool=='check_supplier_fiscal_duplicates' and current.get('fault')=='duplicate':rows=[{'folder':'TEST','BPSNUM_0':'F900','BPRNUM_0':'F900','BPRNAM_0':'CORRESPONDANCE SIMULEE'}]
   elif tool not in ('get_supplier_record','check_supplier_fiscal_duplicates'):out.update(FakeSQL()([request]));continue
   out[request['id']]={'ok':True,'folder':'TEST','source':'CAMPAIGN_CONTROLLED_FIXTURE','rows':rows}
  return out
 monkeypatch.setattr(chat_tools,'run',tools)
 async def extract(*a,**kw):raise httpx.ReadTimeout('Simulated unavailable semantic extraction; literal paths remain under test')
 monkeypatch.setattr(chat.model,'extract',extract)
 async def post(self,url,**kwargs):
  wire.append(str(url));request=httpx.Request('POST',url);fault=current.get('fault')
  if 'deepseek' in str(url):
   if fault=='timeout':raise httpx.ReadTimeout('Simulated cloud timeout')
   status=int(fault) if str(fault).isdigit() else 200
   content='{' if fault=='json' else '' if fault=='empty' else 'Je peux préparer les fiches ; une confirmation est obligatoire.'
   return httpx.Response(status,request=request,json={'model':'deepseek-chat','choices':[{'message':{'content':content},'finish_reason':'length' if fault=='truncated' else 'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':8}})
  if '/api/chat' in str(url):return httpx.Response(200,request=request,json={'done':True,'message':{'content':'{' if fault=='json' else 'Le secours local conserve votre demande ; aucune opération Sage sans confirmation.'},'prompt_eval_count':20,'eval_count':8})
  raise AssertionError('Unexpected outbound HTTP '+str(url))
 monkeypatch.setattr(httpx.AsyncClient,'post',post)
 def forbidden(*a,**kw):raise AssertionError('External subprocess forbidden in simulated campaign')
 monkeypatch.setattr(subprocess,'run',forbidden)
 return c,current,calls,attempts,wire

def test_thousand_conversations(campaign,monkeypatch):
 c,current,tool_calls,attempts,wire=campaign
 corpus_path=ROOT/'TEST'/os.getenv('CAMPAIGN_CORPUS','campaign-1000-corpus.jsonl')
 if not corpus_path.exists():corpus_path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in corpus()),encoding='utf-8')
 cases=[json.loads(line) for line in corpus_path.read_text(encoding='utf-8').splitlines()]
 variants=int(os.getenv('CAMPAIGN_VARIANTS','25'));cases=[r for r in cases if r['persona']<variants]
 if os.getenv('CAMPAIGN_FAMILIES'):cases=[r for r in cases if r['family'] in os.environ['CAMPAIGN_FAMILIES'].split(',')]
 if os.getenv('CAMPAIGN_SHARD') is not None:
  shard=int(os.environ['CAMPAIGN_SHARD']);shards=int(os.getenv('CAMPAIGN_SHARDS','4'));cases=[r for j,r in enumerate(cases) if j%shards==shard]
 prefix=os.getenv('CAMPAIGN_REPORT','campaign-1000');path=ROOT/'TEST'/f'{prefix}-results.jsonl';report=ROOT/'TEST'/f'{prefix}-summary.json';start=time.monotonic();results=[];turn_count=0
 real_get_row=chat.get_row
 with path.open('w',encoding='utf-8') as stream:
  for n,case in enumerate(cases,1):
   current.clear();current.update(case);settings.ai_provider='deepseek' if case['family'] in ('api_failure','json_failure') else 'ollama';settings.conversation_analysis_enabled=case['family']=='json_failure'
   s=create(c);errors=[];turns=[];before_calls=len(attempts);before_wire=len(wire)
   if case.get('initial'):
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(case['initial']),s['id']))
    s=c.get('/api/v1/chat/conversations/'+s['id']).json()
   for k,st in enumerate(case['steps'],1):
    t=time.monotonic();turn_count+=1
    if st.get('recover'):current['fault']=None
    if st.get('pg_fail'):
     count=[0]
     def broken(*a,**kw):
      count[0]+=1
      if count[0]==1:raise psycopg.OperationalError('SIMULATED_POSTGRES_INTERRUPTION')
      return real_get_row(*a,**kw)
     monkeypatch.setattr(chat,'get_row',broken)
    try:
     r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':st['text'],'revision':s['revision']})
     status=r.status_code
     if st.get('pg_fail'):
      if status!=503:errors.append(f'turn {k}: PostgreSQL interruption should return useful HTTP 503, got {status}')
      turns.append({'text':st['text'],'http':status,'reply':r.text[:400]});continue
     if status!=200:raise AssertionError('HTTP '+str(status)+': '+r.text[:300])
     s=r.json();state=s['state'];reply=s['messages'][-1]['content'];check=[]
     if not reply.strip():check.append('empty reply')
     if state.get('_pending') or state.get('analysis_job',{}).get('status')!='completed':check.append('unfinished job')
     if 'avec succès' in reply and ('créé' in reply or 'modifié' in reply):check.append('invented Sage success')
     for kind in ('partners','articles','modification_drafts'):
      for d in state.get(kind,[]):
       if d.get('approved') or d.get('operation',{}).get('status') in ('approved','executing'):check.append('unauthorized approval/execution')
     for key,expected in st.get('eq',{}).items():
      actual=get(state,key)
      if actual!=expected:check.append(f'{key}: expected {expected!r}, got {actual!r}')
     for key,length in st.get('length',{}).items():
      if len(get(state,key))!=length:check.append(f'{key}: expected length {length}')
     for token in st.get('contains',[]):
      if token.casefold() not in reply.casefold():check.append('reply missing '+repr(token))
     # Real persistence read, not just the returned Python object.
     saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
     if saved['state']!=state:check.append('persisted state differs from response')
     errors.extend(f'turn {k}: '+e for e in check)
     turns.append({'text':st['text'],'http':status,'reply':reply,'errors':check,'seconds':round(time.monotonic()-t,3),'expected':st.get('eq',{}),'actual':{p:get(state,p) for p in st.get('eq',{})},'actions':[{ 'resource':d.get('resource',d.get('kind')),'code':d.get('code',d.get('code_article')),'status':d.get('operation',{}).get('status')} for kind in ('partners','articles','modification_drafts') for d in state.get(kind,[])]})
    except Exception as exc:
     errors.append(f'turn {k}: {type(exc).__name__}: {str(exc)[:300]}');turns.append({'text':st['text'],'error':str(exc)[:300]})
    finally:
     monkeypatch.setattr(chat,'get_row',real_get_row)
     if st.get('pg_fail'):
      restored=c.get('/api/v1/chat/conversations/'+s['id'])
      if restored.status_code==200:s=restored.json()
   result={'id':case['id'],'family':case['family'],'language':case['language'],'passed':not errors,'errors':errors,'turns':turns,'sage_transport_attempts':len(attempts)-before_calls,'mock_ai_calls':len(wire)-before_wire}
   results.append(result);stream.write(json.dumps(result,ensure_ascii=False,default=str)+'\n');stream.flush()
   if n%20==0:print(json.dumps({'executed':n,'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'turns':turn_count,'seconds':round(time.monotonic()-start,1)}),flush=True)
 by_family={f:{'executed':sum(r['family']==f for r in results),'passed':sum(r['passed'] and r['family']==f for r in results)} for f in sorted({r['family'] for r in results})}
 summary={'executed':len(results),'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'turns':turn_count,'families':by_family,'seconds':round(time.monotonic()-start,3),'corpus_sha256':hashlib.sha256(corpus_path.read_bytes()).hexdigest(),'real_sage_writes':sum(bool(r['execute']) for r in attempts),'real_cloud_calls':0,'sage_transport':'simulated','ai_transport':'simulated','database':'real isolated PostgreSQL schema','http':'FastAPI TestClient','actors':'1000 independent conversation sessions; one isolated authenticated test account','results':str(path),'note':'Mock responses test orchestration and guards, not measured real-model comprehension of 1000 texts.'}
 report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
 assert summary['real_sage_writes']==0
 assert summary['failed']==0,f"{summary['failed']} scenarios failed; see {path}"
