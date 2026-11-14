"""All cloud and local calls simulated. Real private PostgreSQL test schemas only."""
import sys,json,asyncio,copy
from pathlib import Path
from uuid import UUID,uuid4
from decimal import Decimal
import httpx,pytest
from pydantic import SecretStr
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from test_conversation_chat import fixture,create
from app.core.config import settings
from app.services import ai_provider as provider,conversation_chat as chat,chat_model as model,business_store as db,natural_dialogue
REAL_EXTRACT=model.extract

@pytest.fixture
def cloud(fixture,monkeypatch):
    # Transport/ledger contract tests isolate the pre-existing provider layer.
    monkeypatch.setattr(settings,'conversation_analysis_enabled',False)
    c,_=fixture
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(settings,'ai_fallback_provider','ollama')
    monkeypatch.setattr(settings,'deepseek_api_key',SecretStr('test-private-key-do-not-log'))
    monkeypatch.setattr(settings,'ai_daily_budget_usd',1)
    calls=[];response={'status':200,'text':'Bonjour, comment puis-je vous aider ?','model':'deepseek-flash','reason':'stop'}
    async def post(self,url,**kwargs):
        calls.append({'url':str(url),'payload':copy.deepcopy(kwargs.get('json'))})
        request=httpx.Request('POST',url)
        if 'api.deepseek.com' in str(url):
            if response.get('timeout'):raise httpx.ReadTimeout('simulated provider timeout')
            return httpx.Response(response['status'],request=request,json={'model':response['model'],'choices':[{'message':{'content':response['text']},'finish_reason':response['reason']}],'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':25}})
        if '/api/chat' in str(url):
            if response.get('local_failure'):raise httpx.ConnectError('simulated local failure')
            return httpx.Response(200,request=request,json={'done':True,'message':{'content':'Bonjour depuis Qwen local.'},'prompt_eval_count':20,'eval_count':10})
        raise AssertionError('Unexpected external network access')
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    return c,calls,response

def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
    assert r.status_code==200,r.text
    return r.json()

def test_real_chat_service_uses_cloud_and_saves_unverified_learning_turn(cloud):
    c,calls,response=cloud;s=send(c,create(c),'Bonjour')
    assert len(calls)==1 and 'deepseek' in calls[0]['url']
    assert s['messages'][-1]['content']==response['text']
    assert s['state']['ai_calls'][-1]['provider']=='deepseek'
    assert not s['state'].get('articles') and not s['state'].get('partners')
    assert 'test-private-key' not in json.dumps(s)
    with db.connection() as conn:
        rows=conn.execute('SELECT * FROM chat_ai_usage').fetchall()
        assert len(rows)==1 and rows[0]['input_tokens']==100 and rows[0]['output_tokens']==20
        assert rows[0]['estimated_cost_usd']>0
        assert conn.execute('SELECT count(*) AS n FROM learning_feedback').fetchone()['n']==0

@pytest.mark.parametrize('failure',[401,402,429,500,503,'timeout','empty','truncated'])
def test_cloud_failure_falls_back_once_without_losing_state(cloud,failure):
    c,calls,response=cloud
    if isinstance(failure,int):response['status']=failure
    elif failure=='timeout':response['timeout']=True
    elif failure=='empty':response['text']=''
    else:response['reason']='length'
    s=send(c,create(c),'Salam, kif dayr ?')
    assert s['messages'][-1]['content']=='Bonjour depuis Qwen local.'
    assert len(calls)==2 and '/api/chat' in calls[-1]['url']
    assert s['state']['ai_calls'][-1]['provider']=='ollama'
    assert s['state']['ai_calls'][-1]['fallback_reason']
    assert s['state']['analysis_job']['status']=='completed'

def test_manual_local_mode_is_private_and_survives_read(cloud):
    c,calls,_=cloud;s=create(c)
    s=c.post('/api/v1/chat/conversations/'+s['id']+'/ai-mode',json={'mode':'local','revision':s['revision']}).json()
    s=send(c,s,'Bonjour')
    assert len(calls)==1 and '/api/chat' in calls[0]['url']
    assert c.get('/api/v1/chat/conversations/'+s['id']).json()['state']['ai_mode']=='local'
    assert s['state']['ai_calls'][-1]['fallback_reason'] is None

def test_both_providers_down_end_job_and_preserve_draft(cloud):
    c,calls,response=cloud;s=create(c)
    with db.connection() as conn:
        owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
        row=chat.get_row(conn,owner,UUID(s['id']),True);row['state']['articles']=[{'id':str(uuid4()),'designation':'FOURNITURE BUREAU TEST','categorie':'AVNS','unite':'UN','site':'202'}];chat.save_conversation_context(conn,owner,UUID(s['id']),row['state'])
    response.update(timeout=True,local_failure=True);s=send(c,s,'Bonjour')
    assert s['state']['articles'][0]['categorie']=='AVNS' and s['state']['articles'][0]['site']=='202'
    assert s['state']['analysis_job']['status']=='completed' and not s['state'].get('_pending')
    assert 'conserv' in s['messages'][-1]['content']

def test_budget_disables_cloud_without_call_or_loss(cloud,monkeypatch):
    c,calls,_=cloud;monkeypatch.setattr(settings,'ai_daily_budget_usd',0)
    s=send(c,create(c),'Bonjour')
    assert len(calls)==1 and '/api/chat' in calls[0]['url']
    assert s['state']['ai_calls'][-1]['fallback_reason']=='BudgetExceeded'

def test_unknown_model_does_not_invent_cost():
    assert provider.estimate('unknown-future-model',{'prompt_tokens':100,'completion_tokens':10}) is None
    assert provider.estimate('deepseek-flash',{'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':25})==Decimal('0.00004665')

@pytest.mark.parametrize('message',['Bonjour','Salam, kif dayr ?','Explique-moi comment tu fonctionnes','merci','je veux manger'])
def test_natural_dialogue_does_not_require_json(message):assert natural_dialogue.eligible(message,{})

@pytest.mark.parametrize('message',["J'ai déjà donné le code AVNS",'Retiens que le paiement habituel est comptant','Quelles règles as-tu retenues ?', 'Que sais-tu de moi ?', 'Change la TVA de TESTART203 à 10 %','BARI Ne ajouter wahade foourniseur','le nom de fourniseur est ABDHADI TA','ICE 003224720000051'])
def test_business_and_memory_never_become_plain_uncontrolled_chat(message):assert not natural_dialogue.eligible(message,{'articles':[{'id':'current'}]})

def test_api_usage_is_owner_scoped_and_mode_requires_csrf(cloud):
    c,calls,_=cloud;s=send(c,create(c),'Bonjour')
    result=c.get('/api/v1/chat/ai/status');assert result.status_code==200
    assert result.json()['usage_30_days'][0]['calls']==1
    assert 'key' not in json.dumps(result.json())
    c.headers['X-Chat-CSRF']='invalid'
    assert c.post('/api/v1/chat/conversations/'+s['id']+'/ai-mode',json={'mode':'local','revision':s['revision']}).status_code==403

def test_structured_invalid_json_uses_existing_local_contract(cloud):
    _,calls,response=cloud;response['text']='not JSON'
    async def local():return {'done':True,'message':{'content':'{"intent":"other"}'}}
    result=asyncio.run(provider.complete([{'role':'user','content':'parse this'}],schema={'type':'object','required':['intent']},local=local,purpose='test'))
    assert result['provider']=='ollama' and len(calls)==1

def test_generated_success_claim_is_never_presented_as_sage_fact(cloud):
    c,_,response=cloud;response['text']="J'ai créé le fournisseur avec succès."
    s=send(c,create(c),'Bonjour')
    assert 'confirmation' in s['messages'][-1]['content']

def test_budget_is_not_reset_by_deleting_conversation(cloud):
    c,_,_=cloud;s=send(c,create(c),'Bonjour')
    with db.connection() as conn:
        amount=conn.execute('SELECT used_usd FROM chat_ai_budget').fetchone()['used_usd']
        conn.execute('DELETE FROM chat_conversations WHERE id=%s',(s['id'],))
        assert conn.execute('SELECT used_usd FROM chat_ai_budget').fetchone()['used_usd']==amount
        assert conn.execute('SELECT count(*) AS n FROM chat_ai_usage').fetchone()['n']==0

def test_other_owner_cannot_read_usage_or_change_mode(cloud):
    from fastapi.testclient import TestClient
    from app.main import app
    c,_,_=cloud;s=send(c,create(c),'Bonjour')
    other=TestClient(app);other.headers['Origin']='http://testserver'
    r=other.post('/api/v1/chat/auth/register',json={'email':'other-'+uuid4().hex+'@example.test','display_name':'Autre compte','password':'Test-isolation-password-2026!'})
    other.headers['X-Chat-CSRF']=r.json()['csrf']
    assert other.get('/api/v1/chat/ai/status').json()['usage_30_days']==[]
    assert other.post('/api/v1/chat/conversations/'+s['id']+'/ai-mode',json={'mode':'local','revision':s['revision']}).status_code==404

def test_pending_name_answer_is_not_free_chat():
    assert not natural_dialogue.eligible('Ahmed Mohamed',{'_supplier_dialogue':{'pending':'name'}})

def test_structured_model_extracts_multiturn_context_and_validates_schema(cloud):
    _,calls,response=cloud
    response['text']=json.dumps({'intent':'update','articles':[{'index':1,'designation':'FOURNITURE BUREAU CORRIGEE'}]})
    state={'articles':[{'id':'draft','designation':'FOURNITURE BUREAU TEST','categorie':'AVNS','unite':'UN','site':'202'}]}
    async def case():
        token=model.FORCE_AI.set(True)
        try:return await REAL_EXTRACT('Corrige la designation en FOURNITURE BUREAU CORRIGEE',state,[{'role':'user','content':'categorie AVNS, unite UN, site 202'}])
        finally:model.FORCE_AI.reset(token)
    delta,source=asyncio.run(case())
    assert delta.articles[0].designation=='FOURNITURE BUREAU CORRIGEE' and source['provider']=='deepseek'
    body=calls[0]['payload'];assert body['response_format']=={'type':'json_object'}
    assert all(x in json.dumps(body) for x in ('AVNS','202','UN'))

def test_parallel_requests_cannot_overreserve_global_budget(cloud,monkeypatch):
    _,calls,_=cloud;monkeypatch.setattr(settings,'ai_daily_budget_usd',0.002)
    original=httpx.AsyncClient.post
    async def case():
        entered=asyncio.Event();release=asyncio.Event()
        async def delayed(self,url,**kwargs):
            if 'api.deepseek.com' in str(url):entered.set();await release.wait()
            return await original(self,url,**kwargs)
        monkeypatch.setattr(httpx.AsyncClient,'post',delayed)
        first=asyncio.create_task(provider.complete([{'role':'user','content':'x'}]))
        await asyncio.wait_for(entered.wait(),3)
        second=await provider.complete([{'role':'user','content':'x'}])
        assert second['provider']=='ollama'
        release.set();assert (await first)['provider']=='deepseek'
    asyncio.run(case())
    assert sum('api.deepseek.com' in c['url'] for c in calls)==1
    with db.connection() as conn:assert conn.execute('SELECT used_usd FROM chat_ai_budget').fetchone()['used_usd']<=Decimal('0.002')

def test_business_failure_recovers_grounded_draft_without_retry_loop(cloud,monkeypatch):
    c,_,_=cloud;s=create(c)
    with db.connection() as conn:
        owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
        state=chat.get_row(conn,owner,UUID(s['id']),True)['state']
        state['articles']=[{'id':str(uuid4()),'designation':'FOURNITURE BUREAU TEST','categorie':'AVNS','unite':'UN','site':'202'}]
        chat.save_conversation_context(conn,owner,UUID(s['id']),state)
    async def failed(*args,**kwargs):raise ValueError('invalid model response')
    monkeypatch.setattr(model,'extract',failed)
    s=send(c,s,'Corrige le conditionnement selon ma phrase precedente')
    a=s['state']['articles'][0]
    assert a['categorie']=='AVNS' and a['unite']=='UN' and a['site']=='202'
    assert a['operation']['status']=='blocked' and a['approved'] is False
    assert s['state']['analysis_job']['status']=='completed' and not s['state'].get('_pending')

def test_structured_cloud_failure_reuses_qwen_stream_without_deadlock(cloud,monkeypatch):
    _,_,response=cloud;response['status']=503
    async def stream(*args):
        assert model._MODEL_LOCKS[asyncio.get_running_loop()].locked()
        return {'done':True,'done_reason':'stop','message':{'content':'{"intent":"update","shared":{"unite":"UN"}}'}},{}
    monkeypatch.setattr(model,'_ollama_request_stream',stream)
    async def case():
        token=model.FORCE_AI.set(True)
        try:return await asyncio.wait_for(REAL_EXTRACT('unite UN',{'articles':[{'id':'a','designation':'TEST'}]},[]),3)
        finally:model.FORCE_AI.reset(token)
    delta,source=asyncio.run(case())
    assert delta.shared.unite=='UN' and source['provider']=='ollama'

def test_only_validated_memory_is_reused_in_new_conversation_by_fallback(cloud):
    c,calls,response=cloud
    first=send(c,create(c),'Retiens que les réponses doivent rester courtes et précises.')
    assert not calls
    send(c,create(c),'Bonjour')
    assert 'courtes et' not in json.dumps(calls[-1]['payload'],ensure_ascii=False)
    first=send(c,first,'Valide cette règle')
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM learning_items WHERE status='validated'").fetchone()['n']==1
    response['status']=503;calls.clear()
    s=send(c,create(c),'Bonjour')
    assert s['state']['ai_calls'][-1]['provider']=='ollama'
    assert all('courtes et' in json.dumps(call['payload'],ensure_ascii=False) for call in calls)
    with db.connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM learning_feedback').fetchone()['n']==0

def test_provider_cannot_echo_the_key_into_chat_or_metadata(cloud):
    c,_,response=cloud
    response['text']='Do not display test-private-key-do-not-log'
    response['model']='test-private-key-do-not-log'
    s=send(c,create(c),'Bonjour')
    assert 'test-private-key-do-not-log' not in json.dumps(s)
    with db.connection() as conn:
        assert 'test-private-key-do-not-log' not in str(conn.execute('SELECT model FROM chat_ai_usage').fetchall())
