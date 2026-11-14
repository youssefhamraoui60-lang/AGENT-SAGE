"""Real HTTP/provider/PG/Sage campaign. Explicit TEST writes on owned fixtures only.

Corpus turns are never approvals. Controlled write probes have separate
conversations, exact parameter allowlists and independent SQL readback.
No permissions, triggers, source documents or existing Sage rows are changed.
"""
import argparse,concurrent.futures,copy,hashlib,json,re,secrets,threading,time
from pathlib import Path
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'article-100-session-campaign'
LOCK=threading.Lock()
CLIENT_LOCAL=threading.local()
CLIENT_POOL=[]
STOP_EVENT=threading.Event()

def budget_exhausted(enabled):
    if not enabled:return False
    if STOP_EVENT.is_set():return True
    from app.services import business_store as db
    with db.connection() as conn:
        row=conn.execute("SELECT used_usd FROM chat_ai_budget WHERE day=(now() AT TIME ZONE 'UTC')::date").fetchone()
    if row and float(row['used_usd'])>=.45:STOP_EVENT.set()
    return STOP_EVENT.is_set()

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    for attempt in range(20):
        try:temporary.replace(path);break
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05*(attempt+1))

class Client:
    def __init__(self,base,tag,index,credentials=None):
        self.base=base+'/api/v1/chat'
        self.client=httpx.Client(timeout=httpx.Timeout(180,connect=10),headers={'Origin':base})
        auth=self.post('/auth/login',credentials) if credentials else self.post('/auth/register',{'email':f'article-campaign-{tag}-{index}-{uuid4().hex[:6]}@example.test','display_name':'Campagne articles TEST','password':secrets.token_urlsafe(32)})
        self.owner=auth['user']['id'];self.client.headers['X-Chat-CSRF']=auth['csrf']
    def post(self,path,body):
        r=self.client.post(self.base+path,json=body)
        if r.status_code>=400:raise RuntimeError(f'HTTP {r.status_code}: '+r.text[:700])
        return r.json()
    def get(self,cid):
        r=self.client.get(self.base+'/conversations/'+cid);r.raise_for_status();return r.json()
    def new(self):
        s=self.post('/conversations',{'discussion_mode':'general'})
        assert s.get('folder',s['state'].get('supplier_target','TEST'))=='TEST'
        return s
    def send(self,s,text):
        result=self.post('/conversations/'+s['id']+'/messages',{'content':text,'revision':s['revision']})
        assert result['state'].get('supplier_target','TEST')=='TEST'
        return result
    def act(self,s,kind,identifier,step,confirm=False):
        assert s['state'].get('supplier_target','TEST')=='TEST'
        return self.post(f'/conversations/{s["id"]}/{kind}/{identifier}/{step}',{'revision':s['revision'],'confirm':confirm})

def checks(source,number,s,reply):
    state=s['state'];items=state.get('articles',[]);errors=[]
    if not reply.strip():errors.append('empty_reply')
    if state.get('_pending'):errors.append('pending_after_response')
    if state.get('supplier_target','TEST')!='TEST':errors.append('folder_leak')
    if any(a.get('operation',{}).get('status') in ('executing','succeeded') for a in items):errors.append('unauthorized_corpus_write')
    if len({a.get('id') for a in items})!=len(items):errors.append('duplicate_draft_identity')
    if re.search(r"extraction.{0,8}(?:abouti|interromp)|reprendre l.analyse|appel non valid",reply,re.I):errors.append('technical_dead_end')
    if re.search(r'\bservices? IA\b.{0,80}(?:indisponible|ne permet|impossible)',reply,re.I):errors.append('unresolved_provider_outage')
    if number==1 and items:errors.append('greeting_created_draft')
    if number in (2,3,4):
        if len(items)!=1:errors.append('expected_one_draft')
        else:
            if number>=3 and items[0].get('designation')!=source['article_de_depart']:errors.append('corrected_designation_lost')
            message=source['messages'][1]['utilisateur'];site=re.search(r'\bsite\s+(\d{3})\b',message)
            if site and site[1] not in (items[0].get('requested_sites') or [items[0].get('site')]):errors.append('site_lost')
    if number==10 and any('tax_rate' in d.get('changes',{}) for d in state.get('modification_drafts',[])):errors.append('tax_question_became_update')
    if number in (13,17) and source['scenario']=='correction_category' and len(items)!=1:errors.append('correction_created_second_draft')
    return errors

def controlled_writes(client,session_id,tag,out):
    from app.services import erp_modification as modification
    code='CX'+tag[:6].upper()+session_id[-3:]
    designation='CXTEST '+tag[:6].upper()+' '+session_id[-3:]
    record={'folder':'TEST','code':code,'designation':designation,'status':'not_attempted','authorization':'Explicit user authorization for controlled TEST writes'}
    save(out/'write-intent.json',record)
    s=client.new();record['conversation_id']=s['id']
    text=f'Prépare un article de test. Code article : {code}, désignation : {designation}, catégorie AVNS, unité UN, site 201, non géré en stock, acheté et vendu, sans fournisseur. Affiche la fiche avant confirmation.'
    s=client.send(s,text);record['creation_reply']=s['messages'][-1]['content']
    items=[a for a in s['state'].get('articles',[]) if a.get('code_article')==code]
    if len(items)!=1:record.update(status='blocked',reason='Agent did not prepare the exact controlled article');save(out/'real-writes.json',record);return record
    a=items[0]
    assert a.get('designation')==designation and a.get('categorie')=='AVNS'
    assert (a.get('requested_sites') or [a.get('site')])==['201']
    assert not a.get('fournisseurs') and not a.get('code_fournisseur') and not a.get('fournisseur_principal')
    if a.get('operation',{}).get('status')!='prepared':
        s=client.act(s,'articles',a['id'],'prepare');a=next(x for x in s['state']['articles'] if x['id']==a['id'])
    plan=a['operation'].get('plan',{})
    assert plan.get('folder')=='TEST' and plan.get('code')==code
    assert plan.get('summary',{}).get('designation')==designation
    assert {n['table'] for n in plan['nodes']} <= {'ITMMASTER','ITMFACILIT','ITMSALES','ATEXTRA'}
    assert all(n['overrides'].get('ITMREF_0',code)==code for n in plan['nodes'])
    assert a['operation']['status']=='prepared'
    record['reviewed_creation']=copy.deepcopy(a['operation']);record['status']='reviewed'
    save(out/'real-writes.json',record)
    s=client.act(s,'articles',a['id'],'approve',True)
    # Write intent is journalled BEFORE execute. A transport error never retries.
    record['status']='creation_attempted';save(out/'real-writes.json',record)
    s=client.act(s,'articles',a['id'],'execute',True)
    created=next(x for x in s['state']['articles'] if x['id']==a['id'])
    record['creation']=created.get('operation');save(out/'real-writes.json',record)
    if created.get('operation',{}).get('status')!='succeeded':record['status']='creation_unconfirmed';save(out/'real-writes.json',record);return record
    view=modification.snapshot('article',code)
    rows=view.get('articles',[])
    assert len(rows)==1 and rows[0]['ITMREF_0'].strip()==code and rows[0]['ITMDES1_0'].strip()==designation
    assert {r['STOFCY_0'].strip() for r in view['sites']}=={'201'}
    record['creation_readback']={'code':code,'designation':rows[0]['ITMDES1_0'],'sites':['201'],'source_hash':rows[0]['source_hash']}
    record['status']='creation_verified';save(out/'real-writes.json',record)
    s=client.send(s,f'Pour cet article de test {code}, prépare uniquement l’ajout du site 202. Ne change pas la fiche principale et attends la confirmation.')
    ds=[d for d in s['state'].get('modification_drafts',[]) if d.get('resource')=='article' and d.get('code')==code and d.get('changes')=={'add_sites':['202']}]
    if len(ds)!=1:record.update(status='modification_not_prepared',modification_reply=s['messages'][-1]['content']);save(out/'real-writes.json',record);return record
    d=ds[0];record['modification']=copy.deepcopy(d);save(out/'real-writes.json',record)
    if d.get('operation',{}).get('status')!='prepared':record['status']='modification_blocked';save(out/'real-writes.json',record);return record
    nodes=d['operation']['plan']['nodes']
    assert nodes and all(n['kind']=='insert' and n['table']=='ITMFACILIT' and n['keys']=={'ITMREF_0':code,'STOFCY_0':'202'} for n in nodes)
    s=client.act(s,'modifications',d['id'],'approve',True)
    record['status']='modification_attempted';save(out/'real-writes.json',record)
    s=client.act(s,'modifications',d['id'],'execute',True)
    modified=next(x for x in s['state']['modification_drafts'] if x['id']==d['id'])
    record['modification']=modified
    view=modification.snapshot('article',code)
    sites={r['STOFCY_0'].strip() for r in view['sites']}
    record['modification_readback']={'code':code,'sites':sorted(sites)}
    record['status']='verified' if modified['operation']['status']=='succeeded' and sites=={'201','202'} else 'modification_unconfirmed'
    save(out/'real-writes.json',record);return record

def run_session(source,args,index):
    out=OUT/args.run/source['id'];out.mkdir(parents=True,exist_ok=True)
    result={'id':source['id'],'scenario':source['scenario'],'turns':[],'mode':'real_backend_real_provider_real_reads','sage_corpus_writes':0}
    if budget_exhausted(args.budget_stop):
        result['stopped']='additional_budget_limit';save(out/'conversation.json',result);return result
    if args.auth_pool:
        if not getattr(CLIENT_LOCAL,'client',None):
            from article_campaign_accounts import load
            credentials=load()
            with LOCK:credential_index=len(CLIENT_POOL)%len(credentials)
            CLIENT_LOCAL.client=Client(args.base,args.run,index,credentials[credential_index])
            with LOCK:CLIENT_POOL.append(CLIENT_LOCAL.client)
        client=CLIENT_LOCAL.client
    else:client=Client(args.base,args.run,index)
    s=client.new();result.update(conversation_id=s['id'],owner_id=client.owner)
    for message in source['messages']:
        if budget_exhausted(args.budget_stop):result['stopped']='additional_budget_limit';break
        start=time.monotonic();turn={'number':message['numero'],'text':message['utilisateur'],'expected':message['attendu'],'checks':message.get('controles',[])}
        try:
            s=client.send(s,message['utilisateur']);reply=s['messages'][-1]['content']
            turn.update(reply=reply,state=s['state'],errors=checks(source,message['numero'],s,reply),provider=s['state'].get('tool_orchestration',{}).get('provider'))
        except Exception as exc:
            turn.update(errors=['request_failed'],error=type(exc).__name__+': '+str(exc)[:800])
            try:s=client.get(s['id'])
            except Exception:pass
        turn['seconds']=round(time.monotonic()-start,3);result['turns'].append(turn)
        save(out/'conversation.json',result)
        with LOCK:print(json.dumps({'session':source['id'],'turn':turn['number'],'errors':turn['errors'],'seconds':turn['seconds']},ensure_ascii=False),flush=True)
    if args.real_writes and len(result['turns'])==24 and not budget_exhausted(args.budget_stop):
        try:result['real_writes']=controlled_writes(client,source['id'],args.run,out)
        except Exception as exc:result['real_writes']={'status':'stopped_no_retry','error':type(exc).__name__+': '+str(exc)[:800]}
    result['completed']=len(result['turns'])==24;result['failed_turns']=sum(bool(t['errors']) for t in result['turns'])
    save(out/'conversation.json',result)
    if not args.auth_pool:client.client.close()
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8000');p.add_argument('--workers',type=int,default=4);p.add_argument('--limit',type=int,default=100);p.add_argument('--only');p.add_argument('--run',default=uuid4().hex[:8]);p.add_argument('--real-writes',action='store_true');p.add_argument('--auth-pool',action='store_true');p.add_argument('--budget-stop',action='store_true');args=p.parse_args()
    if args.real_writes:
        import os
        if os.environ.get('RUN_REAL_TEST_WRITES')!='USER_AUTHORIZED_TEST_ONLY':raise SystemExit('Explicit TEST write guard required')
    data=json.loads((OUT/'source.json').read_text(encoding='utf-8'));sources=[s for s in data['sessions'] if not args.only or s['id'] in args.only.split(',')][:args.limit]
    assert all(s['environment']=='TEST' and len(s['messages'])==24 for s in sources)
    run=OUT/args.run
    if (run/'run.json').exists():raise SystemExit('Run already exists: review recorded attempts before any replay')
    run.mkdir(parents=True,exist_ok=True)
    save(run/'run.json',{'run':args.run,'sources':[s['id'] for s in sources],'workers':args.workers,'real_writes':args.real_writes,'source_sha256':hashlib.sha256((OUT/'source.json').read_bytes()).hexdigest()})
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run_session,s,args,i):s for i,s in enumerate(sources)}
        for future in concurrent.futures.as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append({'id':futures[future]['id'],'fatal_error':type(exc).__name__+': '+str(exc)[:600],'turns':[]})
            summary={'sessions_finished':len(results),'messages_executed':sum(len(r['turns']) for r in results),'failed_turns':sum(r.get('failed_turns',0) for r in results),'real_writes':{r['id']:r.get('real_writes',{}).get('status') for r in results},'fatal_errors':[r for r in results if r.get('fatal_error')]}
            save(run/'summary.json',summary)
    print(json.dumps(summary),flush=True)
    for client in CLIENT_POOL:client.client.close()

if __name__=='__main__':main()
