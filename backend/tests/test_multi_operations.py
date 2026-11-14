"""AHMNDE incident, dependency drafts and recovery; no ERP writes."""
import asyncio
from copy import deepcopy
import os
from uuid import uuid4
import httpx
import pytest
from pydantic import ValidationError
from app.services import conversation_chat as chat,chat_fast_extract as fast,chat_multi_operations as multi,chat_model as model,chat_jobs,business_store as db
from app.schemas.conversation_entities import PartnerPatch

TEXT="je veuxc réer la articles et le founiseur mon forniseur c'est AHMNDE Forme juridique SARL AU Capital 100 000 DH Année de création 2018 RC 129251 (Rabat) ICE 002033808000048 prer créer le articles Africa EV Mobility Expo etreffirzncer avce le forniseur que tu a crééer le uniter de articles est UN LE TVA 10 le articles dois non gérer on stok et dans le site de fréer géniro 202"
MULTILINE="je veuxc réer la articles et le founiseur  mon forniseur c'est AHMNDE Forme juridique\nSARL AU\nCapital\n100 000 DH\nAnnée de création\n2018 (8 ans)\nRC\n129251 (Rabat)\nICE\n002033808000048 prer créer le articles Africa EV Mobility Expo etreffirzncer avce le forniseur que tu a crééer   le uniter de articles est UN LE TVA 10 le articles dois non gérer on stok et dans le site de fréer géniro 202"
FACTS={'nom':'AHMNDE','forme_juridique':'SARL AU','capital':'100 000 DH','annee_creation':'2018','rc':'129251','ville_rc':'Rabat','ice':'002033808000048'}


@pytest.mark.parametrize('text',[TEXT,MULTILINE])
def test_exact_incident_all_facts_are_retained(text):
    delta,provenance=fast.extract(text,{'articles':[]})
    assert not provenance['real_model_called']
    state=chat.merge({'articles':[]},delta,text)
    assert len(state['articles'])==len(state['partners'])==1
    p=state['partners'][0]
    assert {k:p[k] for k in FACTS}==FACTS
    a=state['articles'][0]
    assert (a['designation'],a['unite'],a['site'],a['gestion_stock'],a['taux_tva'],a['fournisseur_nom'])==('Africa EV Mobility Expo','UN','202','1','10','AHMNDE')
    assert a['categorie'] is None and a['code_tva'] is None and a['code_fournisseur'] is None
    assert not p.get('code')


def twenty_text():
    return 'Créer un fournisseur AHMNDE, forme juridique SARL AU, capital 100 000 DH ; créer les 20 articles suivants, unité UN :\n'+'\n'.join(f'{i}. Expo mobilité {i}, site {"201" if i%2 else "202"}' for i in range(1,21))


def test_twenty_articles_keep_all_sites_without_supplier_duplication():
    text=twenty_text();delta,_=fast.extract(text,{'articles':[]})
    state=chat.merge({'articles':[]},delta,text)
    assert len(state['articles'])==20 and len(state['partners'])==1
    assert [a['site'] for a in state['articles']]==['201' if i%2 else '202' for i in range(1,21)]
    assert all(a['unite']=='UN' and a['fournisseur_nom']=='AHMNDE' and not a['categorie'] for a in state['articles'])
    delta,_=fast.extract('Pour article 20 : site 209',state)
    after=chat.merge(state,delta,'Pour article 20 : site 209')
    assert after['articles'][19]['site']=='209'
    assert [a['site'] for a in after['articles'][:19]]==[a['site'] for a in state['articles'][:19]]


def test_schema_bounds_and_ice_initial_zeros():
    assert PartnerPatch(**FACTS).ice=='002033808000048'
    with pytest.raises(ValidationError):PartnerPatch(ice='00203380800004')
    with pytest.raises(ValidationError):model.Delta(intent='new',articles=[{'designation':'X'}]*21)
    assert model.Patch(index=20).index==20


def test_supplier_association_correction_does_not_invent_a_new_master():
    delta,_=fast.extract(TEXT,{'articles':[]});state=chat.merge({'articles':[]},delta,TEXT)
    state=multi.plan(state)
    text='fournisseur Nouveau Partenaire'
    delta,_=fast.extract(text,state);after=chat.merge(state,delta,text);after=multi.plan(after)
    assert after['articles'][0]['fournisseur_nom']=='Nouveau Partenaire'
    assert after['partners'][0]['nom']=='AHMNDE' and len(after['partners'])==1
    assert not after['articles'][0].get('supplier_dependency')


@pytest.mark.parametrize('text',['fournisseur facultatif','fournisseur optionnel'])
def test_optional_supplier_is_not_a_new_supplier_name(text):
    delta,_=fast.extract(TEXT,{'articles':[]});state=chat.merge({'articles':[]},delta,TEXT)
    delta,_=fast.extract(text,state);after=chat.merge(state,delta,text)
    assert after['articles'][0]['fournisseur_nom']=='AHMNDE'
    assert after['supplier_requirement']=='optional'


@pytest.mark.parametrize('existing,available,status',[(False,True,'absent_draft_only'),(True,True,'existing_requires_selection'),(False,False,'lookup_pending')])
def test_supplier_resolution_is_evidence_based_and_never_creation(existing,available,status):
    delta,_=fast.extract(TEXT,{'articles':[]});state=chat.merge({'articles':[]},delta,TEXT)
    rows=[{'BPSNUM_0':'F234','BPRNAM_0':'AHMNDE'}] if existing else []
    for p in state['partners']:p['checks']={'tools':{'name':{'ok':available,'rows':rows}},'creation_ready':False}
    state=multi.plan(state)
    assert state['partners'][0]['resolution']['status']==status
    assert state['articles'][0]['supplier_dependency']['status']==status
    assert state['operation_plan']['sage_writes']==0 and not state['operation_plan']['approval_granted']
    assert state['operation_plan']['operations'][1]['missing_fields']==['categorie']
    assert not state['articles'][0]['code_fournisseur']


from test_conversation_chat import fixture,create,send,FakeSQL
from test_sage_article_sites import workflow
integration=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Isolated local PostgreSQL only')


def literal_model(monkeypatch):
    calls=[]
    async def extract(text,state,*args):
        calls.append(text)
        result=fast.extract(text,state)
        assert result is not None,'Test input requires a controlled literal route'
        return result
    monkeypatch.setattr(chat.model,'extract',extract)
    return calls


@integration
def test_persist_before_extract_and_checkpoint_before_sql(fixture,monkeypatch):
    c,_=fixture;s=create(c);events=[]
    # Literal routing can bypass the model. Observe the parser actually used,
    # while retaining the same persistence-before-extraction assertion.
    from app.services import supplier_chat_flow
    real_supplier_extract=supplier_chat_flow.extract
    def supplier_extract(text,state,*args):
        with db.connection() as conn:
            row=conn.execute('SELECT content FROM chat_messages WHERE conversation_id=%s ORDER BY id DESC LIMIT 1',(s['id'],)).fetchone()
            assert row['content']==TEXT
        events.append('original_persisted')
        return real_supplier_extract(text,state,*args)
    monkeypatch.setattr(supplier_chat_flow,'extract',supplier_extract)
    async def extract(text,state,*args):
        with db.connection() as conn:
            row=conn.execute('SELECT content FROM chat_messages WHERE conversation_id=%s ORDER BY id DESC LIMIT 1',(s['id'],)).fetchone()
            assert row['content']==TEXT
        events.append('original_persisted');return fast.extract(text,state)
    def sql(calls):
        with db.connection() as conn:
            value=conn.execute('SELECT state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['state']
            assert value['partners'][0]['ice']==FACTS['ice'] and value['articles'][0]['site']=='202'
            assert value['analysis_job']['checkpoint']=='extracted'
        events.append('checkpoint_persisted');return FakeSQL()(calls)
    monkeypatch.setattr(chat.model,'extract',extract);monkeypatch.setattr(chat.tools,'run',sql)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':TEXT,'revision':s['revision']})
    assert r.status_code==200,r.text
    assert events[0]=='original_persisted' and 'checkpoint_persisted' in events
    state=r.json()['state'];assert state['operation_plan']['sage_writes']==0
    assert not any(q['field']=='site' for q in state['pending'])


@integration
def test_twenty_articles_through_api(fixture,monkeypatch):
    c,_=fixture;s=create(c);literal_model(monkeypatch)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':twenty_text(),'revision':s['revision']})
    assert r.status_code==200,r.text
    state=r.json()['state'];assert len(state['articles'])==20 and len(state['partners'])==1
    assert len(state['operation_plan']['operations'])==41


@integration
@pytest.mark.parametrize('failure',[httpx.ReadTimeout('simulated'),ValueError('invalid_model_json')])
def test_extraction_failure_keeps_original_and_precise_stage(fixture,monkeypatch,failure):
    c,_=fixture;s=create(c)
    async def extract(*args):raise failure
    monkeypatch.setattr(chat.model,'extract',extract)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':TEXT,'revision':s['revision']})
    assert r.status_code in (502,504)
    state=c.get('/api/v1/chat/conversations/'+s['id']).json()
    assert sum(m['content']==TEXT for m in state['messages'])==1
    assert not state['state'].get('_pending')
    assert state['state']['analysis_job']['failed_phase']=='extracting'
    assert state['state']['articles']==[]


@integration
@pytest.mark.parametrize('failure_mode',['exception','incomplete','interruption'])
def test_verification_failure_resume_preserves_entities_no_second_extract(fixture,monkeypatch,failure_mode):
    c,_=fixture;s=create(c);extracts=literal_model(monkeypatch)
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    def sql(calls):
        if failure_mode=='exception':raise OSError('simulated SQL disconnect')
        if failure_mode=='interruption':raise asyncio.CancelledError()
        return {call['id']:{'ok':False,'rows':[],'code':'sql_unavailable'} for call in calls}
    monkeypatch.setattr(chat.tools,'run',sql)
    async def scenario():
        try:await chat.send(owner,s['id'],TEXT,s['revision'])
        except (OSError,asyncio.CancelledError):pass
        before=chat.read(owner,s['id']);state=before['state'];job=state['analysis_job']
        assert len(state['articles'])==len(state['partners'])==1
        assert job['checkpoint']=='extracted' and not state.get('_pending')
        assert job['status'] in ('failed','interrupted','verification_incomplete')
        old_ids=[state['articles'][0]['id'],state['partners'][0]['id']]
        monkeypatch.setattr(chat.tools,'run',FakeSQL())
        await chat_jobs.resume(owner,s['id'],job['id'],before['revision'])
        task=chat_jobs.TASKS.get(job['id'])
        if task:await task
        result=chat.read(owner,s['id']);state=result['state']
        assert state['analysis_job']['status']=='completed'
        assert [state['articles'][0]['id'],state['partners'][0]['id']]==old_ids
        assert len(extracts)==1
        assert sum(m['content']==TEXT for m in result['messages'])==1
        assert state['articles'][0]['unite']=='UN' and state['partners'][0]['ice']==FACTS['ice']
    asyncio.run(scenario())


@integration
def test_background_job_idempotency_and_owner_boundaries(fixture,monkeypatch):
    c,_=fixture;s=create(c);extracts=literal_model(monkeypatch)
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    async def scenario():
        request=uuid4()
        value=await chat_jobs.submit(owner,s['id'],TEXT,s['revision'],request);job_id=value['job']['id']
        task=chat_jobs.TASKS.get(job_id)
        if task:await task
        value=await chat_jobs.submit(owner,s['id'],TEXT,s['revision'],request)
        assert value['job']['id']==job_id and value['job']['status']=='completed'
        assert len(extracts)==1
        with pytest.raises(chat.crud.CrudError):chat_jobs.status(uuid4(),s['id'],job_id)
        with pytest.raises(chat.crud.CrudError):await chat_jobs.resume(owner,s['id'],job_id,value['conversation']['revision'])
        with pytest.raises(chat.crud.CrudError):await chat_jobs.submit(owner,s['id'],TEXT+' changed',s['revision'],request)
    asyncio.run(scenario())


@integration
@pytest.mark.parametrize('mode,expected',[('csrf',403),('reader',403),('missing',404)])
def test_job_submit_keeps_auth_and_ownership(fixture,mode,expected):
    c,_=fixture;s=create(c)
    if mode=='csrf':c.headers['X-Chat-CSRF']='wrong'
    if mode=='reader':
        with db.connection() as conn:conn.execute("UPDATE chat_web_sessions SET role='reader'")
    identifier=str(uuid4()) if mode=='missing' else s['id']
    r=c.post('/api/v1/chat/conversations/'+identifier+'/analysis-jobs',json={'content':TEXT,'revision':s['revision'],'request_id':str(uuid4())})
    assert r.status_code==expected,r.text


@pytest.mark.parametrize('phase',['queue','connection','stream_idle','total'])
def test_timeout_errors_distinguish_phases(phase):
    from app.api.chat import error
    value=error(model.ExtractionTimeout(phase))
    assert value.status_code==504 and 'reprise' in value.detail


@integration
def test_site_and_supplier_corrections_preserve_legal_data(fixture,monkeypatch):
    c,_=fixture;s=create(c);literal_model(monkeypatch)
    url='/api/v1/chat/conversations/'+s['id']+'/messages'
    for text in [MULTILINE,'site 201','Pour le fournisseur 1 : nom AHMNDE Corrigé']:
        r=c.post(url,json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text
        s=r.json()
    a=s['state']['articles'][0];p=s['state']['partners'][0]
    assert a['site']=='201' and a['unite']=='UN'
    assert a['fournisseur_nom']==p['nom']=='AHMNDE Corrigé'
    assert p['ice']==FACTS['ice'] and p['forme_juridique']=='SARL AU'
    assert a['supplier_dependency']['name']=='AHMNDE Corrigé'


@pytest.mark.parametrize('exc,phase',[(httpx.ReadTimeout('test'),'stream_idle'),(httpx.ConnectTimeout('test'),'connection')])
def test_actual_model_timeout_classification(monkeypatch,exc,phase):
    async def request(*args):raise exc
    monkeypatch.setattr(model,'request_stream',request)
    token=model.FORCE_AI.set(True)
    try:
        with pytest.raises(model.ExtractionTimeout) as found:asyncio.run(model.extract('bonjour',{},[]))
        assert found.value.phase==phase
    finally:model.FORCE_AI.reset(token)


def test_total_model_budget_is_enforced_not_only_per_chunk(monkeypatch):
    async def request(*args):await asyncio.sleep(1)
    monkeypatch.setattr(model,'request_stream',request)
    monkeypatch.setattr(model.settings,'business_ai_timeout',0.02)
    token=model.FORCE_AI.set(True)
    try:
        with pytest.raises(model.ExtractionTimeout) as found:asyncio.run(model.extract('bonjour',{},[]))
        assert found.value.phase=='total'
    finally:model.FORCE_AI.reset(token)


@integration
def test_job_endpoint_preserves_existing_separate_article_site_capture(workflow):
    owner,s,parent,calls=workflow
    async def scenario():
        request=uuid4()
        value=await chat_jobs.submit(owner,s['id'],'créer les article-site 202 et 201',s['revision'],request)
        assert value['job']['status']=='completed'
        a=value['conversation']['state']['articles'][0]
        assert a['site_request']['sites']==['201','202'] and a['outcome']['confirmed']
        repeated=await chat_jobs.submit(owner,s['id'],'créer les article-site 202 et 201',s['revision'],request)
        assert repeated['job']['id']==value['job']['id'] and calls==[]
    asyncio.run(scenario())


@integration
def test_queued_request_can_resume_after_worker_was_not_started(fixture,monkeypatch):
    c,_=fixture;s=create(c);literal_model(monkeypatch)
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    job=chat.reserve_analysis(owner,s['id'],TEXT,s['revision'],uuid4())
    value=chat_jobs.status(owner,s['id'],job['id'])
    assert value['job']['resumable'] and not value['job']['worker_active']
    async def scenario():
        await chat_jobs.resume(owner,s['id'],job['id'],value['conversation']['revision'])
        task=chat_jobs.TASKS.get(job['id'])
        if task:await task
        result=chat.read(owner,s['id'])
        assert result['state']['analysis_job']['status']=='completed'
        assert len(result['state']['articles'])==len(result['state']['partners'])==1
        assert sum(m['content']==TEXT for m in result['messages'])==1
    asyncio.run(scenario())


@integration
def test_timeout_before_extraction_has_controlled_retry_without_duplicate_message(fixture,monkeypatch):
    c,_=fixture;s=create(c);attempts=[]
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    async def extract(text,state,*args):
        attempts.append(text)
        if len(attempts)==1:raise model.ExtractionTimeout('stream_idle')
        return fast.extract(text,state)
    monkeypatch.setattr(chat.model,'extract',extract)
    async def scenario():
        value=await chat_jobs.submit(owner,s['id'],TEXT,s['revision'],uuid4())
        job_id=value['job']['id'];task=chat_jobs.TASKS.get(job_id)
        if task:await task
        failed=chat_jobs.status(owner,s['id'],job_id)
        assert failed['job']['status']=='failed' and failed['job']['timeout_phase']=='stream_idle'
        await chat_jobs.resume(owner,s['id'],job_id,failed['conversation']['revision'])
        task=chat_jobs.TASKS.get(job_id)
        if task:await task
        result=chat.read(owner,s['id'])
        assert result['state']['analysis_job']['status']=='completed' and len(attempts)==2
        assert sum(m['content']==TEXT for m in result['messages'])==1
        assert len(result['state']['articles'])==len(result['state']['partners'])==1
    asyncio.run(scenario())


@integration
def test_double_submit_and_resume_while_worker_active_are_controlled(fixture,monkeypatch):
    c,_=fixture;s=create(c)
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    async def scenario():
        release=asyncio.Event();calls=[]
        async def extract(text,state,*args):
            calls.append(text);await release.wait();return fast.extract(text,state)
        monkeypatch.setattr(chat.model,'extract',extract)
        key=uuid4();value=await chat_jobs.submit(owner,s['id'],TEXT,s['revision'],key);job_id=value['job']['id']
        duplicate=await chat_jobs.submit(owner,s['id'],TEXT,s['revision'],key)
        assert duplicate['job']['id']==job_id and duplicate['job']['worker_active']
        with pytest.raises(chat.crud.CrudError):await chat_jobs.resume(owner,s['id'],job_id,duplicate['conversation']['revision'])
        task=chat_jobs.TASKS[job_id];release.set();await task
        assert len(calls)==1 and chat.read(owner,s['id'])['state']['analysis_job']['status']=='completed'
    asyncio.run(scenario())


def test_model_calls_are_serialized_per_event_loop(monkeypatch):
    active=0;maximum=0
    async def request(*args):
        nonlocal active,maximum
        active+=1;maximum=max(active,maximum)
        try:await asyncio.sleep(0.005)
        finally:active-=1
        return {'done':True,'message':{'content':'{"intent":"other"}'}},{}
    monkeypatch.setattr(model,'request_stream',request)
    async def scenario():
        token=model.FORCE_AI.set(True)
        try:await asyncio.gather(model.extract('bonjour',{},[]),model.extract('salut',{},[]))
        finally:model.FORCE_AI.reset(token)
    asyncio.run(scenario());assert maximum==1


@integration
def test_pg_outage_during_error_cleanup_leaves_recoverable_checkpoint(fixture,monkeypatch):
    import psycopg
    c,_=fixture;s=create(c);literal_model(monkeypatch)
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
    original=db.connection
    def unavailable():raise psycopg.OperationalError('simulated local memory outage')
    def broken_sql(calls):
        monkeypatch.setattr(db,'connection',unavailable)
        raise OSError('simulated external SQL failure')
    monkeypatch.setattr(chat.tools,'run',broken_sql)
    async def scenario():
        with pytest.raises(psycopg.OperationalError):await chat.send(owner,s['id'],TEXT,s['revision'])
        monkeypatch.setattr(db,'connection',original)
        value=chat.read(owner,s['id']);job=value['state']['analysis_job']
        assert job['checkpoint']=='extracted' and value['state'].get('_pending')
        observed=chat_jobs.status(owner,s['id'],job['id'])
        assert observed['job']['resumable'] and not observed['job']['worker_active']
        monkeypatch.setattr(chat.tools,'run',FakeSQL())
        await chat_jobs.resume(owner,s['id'],job['id'],value['revision'])
        task=chat_jobs.TASKS.get(job['id'])
        if task:await task
        assert chat.read(owner,s['id'])['state']['analysis_job']['status']=='completed'
    asyncio.run(scenario())
