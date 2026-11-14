"""Bulk: real FastAPI/isolated PG; AI outage simulated; Sage fully simulated.

No claimed real-provider comprehension score. Eligible confirmations run on a
separate fork, then restore the simulated ERP store. Original turns stay read-only.
"""
import os,json,copy,time,re
from pathlib import Path
from uuid import uuid4
from psycopg.types.json import Jsonb
from test_campaign_1000 import campaign,fixture,simulated
from test_conversation_chat import create
from three_supplier_corpora import cases
from app.services import supplier_sql as sql,chat_tools,business_store as db
from app.core.config import settings

ROOT=Path(__file__).resolve().parent
def lower(value):
 import unicodedata
 return ''.join(c for c in unicodedata.normalize('NFD',str(value).casefold()) if not unicodedata.combining(c))
def active(state):return [p for p in state.get('partners',[]) if p.get('operation',{}).get('status') not in ('cancelled','succeeded','failed','ambiguous','unverified')]

def test_all_supplied_messages_and_confirmation_forks(campaign,monkeypatch):
 c,current,reads,attempts,_=campaign;settings.ai_provider='ollama'
 shard=int(os.getenv('CORPUS_SHARD','0'));shards=int(os.getenv('CORPUS_SHARDS','1'));prefix=os.getenv('CORPUS_REPORT','three-corpora-baseline')
 (ROOT/f'{prefix}-{shard}-scope.json').write_text(json.dumps({'schema':settings.business_schema,'simulated_sage':True,'real_ai_calls':0}),encoding='utf-8')
 data=[x for i,x in enumerate(cases()) if i%shards==shard];limit=int(os.getenv('CORPUS_LIMIT','100000'));data=data[:limit]
 ledger=[];sequence=[900000000];fork_results=[];rows_out=[];started=time.monotonic()
 refs=[{'kind':'Paiement','label':method+' '+('Comptant' if day==0 else str(day)+' Jours'),'code':code+('00' if day==0 else str(day))} for method,code in [('Chèque','CHQ'),('Effet','EFF'),('Virement','VIR')] for day in (0,30,60,90,120)]
 refs += [{'kind':'Paiement','label':'Espèce','code':'ESP00'},{'kind':'Pays','label':'Maroc','code':'MA'}]
 monkeypatch.setattr(sql,'load_reference_labels',lambda *a:copy.deepcopy(refs))
 original_tools=chat_tools.run
 def tools(requests):
  out=original_tools(requests)
  for request in requests:
   args=request['args'];tool=request['tool'];found=[]
   if tool in ('search_suppliers','search_supplier_candidates'):
    name=lower(args.get('Label','')).replace('%','').strip()
    if name and any(part in name for part in ('cimat','cymat','monde')):
     found=[{'BPSNUM_0':'F007','BPRNAM_0':'CIMAT','BPRNUM_0':'F007'},{'BPSNUM_0':'F552','BPRNAM_0':'CIMAT BETON','BPRNUM_0':'F552'}] if 'monde' not in name else [{'BPSNUM_0':'F10012','BPRNAM_0':"MONDE FIL D'ACIER",'BPRNUM_0':'F10012'}]
    out[request['id']]={'ok':True,'folder':'TEST','rows':found,'source':'SIMULATED_SAGE_FIXTURE'}
  return out
 monkeypatch.setattr(chat_tools,'run',tools)
 def run(values,execute=False,**kwargs):
  # All calls intercepted before a real SQL transport. No shell/network access.
  attempts.append({'execute':execute,'SIMULATED':True});duplicate=values.get('Nom','').upper()=='AUTOR AUTO SARL AU' or any(r.get('ICE') and r['ICE']==values.get('ICE') for r in ledger)
  if duplicate:return {'ok':False,'folder':'TEST','sql_error_number':50109,'duplicate_warnings':[{'code':'F1099','name':'AUTOR AUTO SARL AU'}],'diagnostics':[{'duplicate_code':'F1099','duplicate_name':'AUTOR AUTO SARL AU'}]}
  if not execute:return {'ok':True,'folder':'TEST','rows':[{'RESULTAT':'VALIDATED_NO_INSERT','CODE_PROPOSE_NON_RESERVE':'F'+str(sequence[0]+1)}]}
  sequence[0]+=1;code='F'+str(sequence[0]);ledger.append(copy.deepcopy(values))
  row={column:values[key] for key,column in sql.READBACK.items()};row.update(ADRESSE2=values.get('Adresse2',''),ADRESSE3=values.get('Adresse3',''),CODE_FOURNISSEUR=code,partner_active=2,supplier_active=2)
  return {'ok':True,'folder':'TEST','executed':True,'rows':[row],'SIMULATED':True}
 monkeypatch.setattr(sql,'run',run)
 def confirmation_fork(snapshot,case_id):
  candidates=[p for p in active(snapshot) if p.get('operation',{}).get('status')=='prepared']
  if not candidates or snapshot.get('supplier_creation_hold'):return None
  before=copy.deepcopy(ledger);fork=create(c);forkstate=copy.deepcopy(snapshot)
  with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(forkstate),fork['id']))
  fork=c.get('/api/v1/chat/conversations/'+fork['id']).json();p=candidates[0];action=[]
  try:
   for step in ('approve','execute'):
    r=c.post('/api/v1/chat/conversations/'+fork['id']+'/partners/'+p['id']+'/'+step,json={'revision':fork['revision'],'confirm':True,'confirm_draft_only_fields':True})
    action.append({'step':step,'http':r.status_code})
    if r.status_code!=200:return {'case':case_id,'passed':False,'SIMULATED':True,'actions':action,'error':r.text[:200]}
    fork=r.json()
   created=next(x for x in fork['state']['partners'] if x['id']==p['id']);op=created['operation'];code=op.get('record_keys',{}).get('BPSNUM')
   return {'case':case_id,'passed':op.get('status')=='succeeded' and bool(re.fullmatch('F[0-9]+',code or '')),'SIMULATED':True,'code':code,'reply':fork['messages'][-1]['content'],'actions':action}
  finally:ledger[:]=before
 output=ROOT/f'{prefix}-{shard}.jsonl'
 with output.open('w',encoding='utf-8') as stream:
  for case in data:
   ledger.clear();s=create(c);turns=[];errors=[];tested_fork=False;history_text='';current.clear();case_start=time.monotonic()
   for k,st in enumerate(case['steps'],1):
    start=time.monotonic();before=copy.deepcopy(s['state']);before_reads=len(reads);history_text+='\n'+st['text'];r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':st['text'],'revision':s['revision']});checks=[]
    if r.status_code!=200:
     checks.append('http_'+str(r.status_code))
     # React reloads the persisted revision after a failed request. The API
     # driver must do the same; otherwise one failure fabricates 20 stale-409s.
     restored=c.get('/api/v1/chat/conversations/'+s['id'])
     if restored.status_code==200:s=restored.json()
     turns.append({'turn':k,**st,'http':r.status_code,'reply':r.text[:500],'errors':checks,'state':s['state']});errors.extend(f'{k}:{e}' for e in checks);continue
    s=r.json();state=s['state'];reply=s['messages'][-1]['content'];present=active(state);previous=active(before);kind=st.get('type') or '';n=lower(st['text'])
    if not reply.strip() or state.get('_pending') or state.get('analysis_job',{}).get('status')!='completed':checks.append('unfinished_or_empty')
    if lower(reply).startswith('appel non valide'):checks.append('generic_tool_error')
    if any(p.get('approved') or p.get('operation',{}).get('status') in ('approved','executing','succeeded') for key in ('partners','articles','modification_drafts') for p in state.get(key,[])):checks.append('original_conversation_unauthorized_write')
    if kind=='create' and not present:checks.append('creation_not_understood')
    if kind=='correct' and len(previous)==1 and len(present)>1 and not re.search(r'\b(?:ajoute|autre|trois)\b',n):checks.append('correction_created_extra_supplier')
    if kind=='lookup' and len(reads)==before_reads and not state.get('tool_read_results') and not state.get('supplier_tasks',{}).get('control',{}):checks.append('requested_lookup_not_instrumented')
    if kind=='cancel' and 'creation' in n and not re.search(r'\b(?:premier|deuxieme|troisieme)\b',n) and present:checks.append('creation_not_cancelled')
    if kind in ('delete','suppression') and not re.search(r'pas|refus|impossible|interdit|non|desactiv|brouillon|annul',lower(reply)):checks.append('delete_not_explained_or_refused')
    if kind=='modify' and not state.get('modification_drafts') and not state.get('supplier_tasks',{}).get('control'):checks.append('modification_not_understood')
    if kind=='summary' and previous and not any(lower(p.get('nom','')) in lower(reply) for p in previous if p.get('nom')):checks.append('summary_missing_suppliers')
    # Exact primary names from uppercase literals, independently of app parsing.
    declared=re.findall(r'\b([A-Z][A-Z0-9 ]{3,}? TEST(?: [0-9]{3})?)\b',st['text'])
    if declared and (kind=='create' or case['dataset']=='emails' and kind in ('creation_simple','creation_multiple','creation_incomplete')):
     for name in declared:
      if not any(lower(p.get('nom',''))==lower(name) for p in present):checks.append('declared_name_not_preserved:'+name)
    if case['dataset']=='mixed' and case['theme']=='ICE et création dupliquée puis recherche':
     if 2<=k<=12 and len(present)!=1:checks.append('expected_one_draft')
     if 3<=k<=12 and present and lower(present[0].get('ville',''))!='berrechid':checks.append('city_not_preserved')
     if k==6:
      ice=re.search(r'[0-9]{15}',st['text']).group(0)
      if not present or present[0].get('ice')!=ice:checks.append('corrected_ice_not_preserved')
     if k>=13 and present:checks.append('cancelled_creation_resurrected')
    saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
    if any(saved['state'].get(key)!=state.get(key) for key in ('partners','articles','modification_drafts')):checks.append('business_state_not_persisted')
    if not tested_fork:
     proof=confirmation_fork(state,case['id'])
     if proof:
      tested_fork=True;fork_results.append(proof)
      if not proof['passed']:checks.append('confirmation_fork_failed')
    turns.append({'turn':k,**st,'http':r.status_code,'reply':reply,'errors':checks,'seconds':round(time.monotonic()-start,3),'state':state});errors.extend(f'{k}:{e}' for e in checks)
   item={'id':case['id'],'dataset':case['dataset'],'theme':case['theme'],'passed':not errors,'errors':errors,'turns':turns,'confirmation_tested':tested_fork,'SIMULATED_SAGE':True,'AI':'simulated outage; actual deterministic fallback','seconds':round(time.monotonic()-case_start,2)}
   stream.write(json.dumps(item,ensure_ascii=False,default=str)+'\n');stream.flush();rows_out.append(item)
   if len(rows_out)%5==0:print(json.dumps({'shard':shard,'sessions':len(rows_out),'messages':sum(len(x['turns']) for x in rows_out),'failed':sum(not x['passed'] for x in rows_out)},ensure_ascii=False),flush=True)
 summary={'cases':len(rows_out),'messages':sum(len(x['turns']) for x in rows_out),'passed':sum(x['passed'] for x in rows_out),'failed':sum(not x['passed'] for x in rows_out),'confirmation_forks':fork_results,'real_sage_writes':0,'real_ai_calls':0,'seconds':round(time.monotonic()-started,2),'scope':'simulated Sage/AI outage; real backend and isolated PostgreSQL'}
 (ROOT/f'{prefix}-{shard}-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k!='confirmation_forks'}),flush=True)
 assert summary['messages']==sum(len(x['steps']) for x in data)
 assert not any(e.get('execute') and not e.get('SIMULATED') for e in attempts)
