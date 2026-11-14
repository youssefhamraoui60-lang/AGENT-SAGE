"""Native DeepSeek tool protocol -> FastAPI -> isolated PG -> mocked Sage.

Both the tool-call response and the response after tool results traverse the
real provider transport. No external process or Sage write is possible.
"""
import json,copy
from uuid import uuid4
import pytest,httpx
from test_campaign_1000 import campaign,fixture,simulated
from test_conversation_chat import create
from app.core.config import settings
from app.services import conversation_tools as engine,business_store as db
from psycopg.types.json import Jsonb

def call(tool_name,**arguments):return {'id':'call_'+uuid4().hex,'type':'function','function':{'name':tool_name,'arguments':json.dumps(arguments,ensure_ascii=False)}}
def native(*calls):return {'role':'assistant','content':None,'tool_calls':list(calls)}
def say(text):return {'role':'assistant','content':text}
def fact(field,value,evidence=None):return {'field':field,'value':value,'evidence':evidence or value}

@pytest.fixture
def native_chat(campaign,monkeypatch):
    c,current,reads,attempts,_=campaign
    monkeypatch.setattr(settings,'conversation_tool_calling_enabled',True)
    monkeypatch.setattr(settings,'conversation_local_tool_calling_enabled',True)
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    queue=[];requests=[];fault={}
    async def post(self,url,**kw):
        requests.append({'url':str(url),'body':copy.deepcopy(kw['json'])});req=httpx.Request('POST',url)
        cloud='deepseek' in str(url)
        if cloud and fault.get('cloud'):raise httpx.ReadTimeout('SIMULATED_NATIVE_CLOUD_DOWN')
        if not cloud and fault.get('local'):raise httpx.ConnectError('SIMULATED_NATIVE_LOCAL_DOWN')
        if cloud and fault.get('json'):return httpx.Response(200,request=req,content=b'{')
        message=queue.pop(0) if queue else say('Votre demande est conservée. Précisez la fiche souhaitée.')
        if cloud and kw['json'].get('tool_choice')=='required' and not message.get('tool_calls'):
            message=native(call('respond',intent='CHAT',text=message['content']))
        if cloud:return httpx.Response(200,request=req,json={'model':'deepseek-flash','choices':[{'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':10}})
        return httpx.Response(200,request=req,json={'done':True,'message':message,'model':'qwen2.5:7b','prompt_eval_count':20,'eval_count':10})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    return c,queue,requests,reads,attempts,fault

def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text
    s=r.json();assert not s['state'].get('_pending');assert s['state']['analysis_job']['status']=='completed'
    assert c.get('/api/v1/chat/conversations/'+s['id']).json()['state']==s['state']
    for kind in ('partners','articles','modification_drafts'):
        assert not any(x.get('approved') or x.get('operation',{}).get('status') in ('executing','approved') for x in s['state'].get(kind,[]))
    return s

def test_exact_cancel_switch_and_modification_full_protocol(native_chat,monkeypatch):
    c,q,requests,reads,attempts,_=native_chat;s=create(c)
    q.append(say('Bonjour ! Je vous écoute.'));s=send(c,s,'bonjour')
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[])),say('Quel est le nom du fournisseur ?')]);s=send(c,s,'je veux créer un fournisseur')
    original=s['state']['partners'][0]['id']
    q.append(say('La création est annulée. Quel fournisseur souhaitez-vous modifier ?'));s=send(c,s,'annuler cette création je veux modifier')
    assert s['state']['partners'][0]['operation']['status']=='cancelled' and not s['state']['partners'][0].get('nom')
    q.append(say('Cette création est déjà annulée.'));s=send(c,s,'je veux annuler la création')
    real_read=engine.read
    def read(args,state,text):
        if args.name=='ahmde test':return {'ok':True,'folder':'TEST','resource':'supplier','rows':[{'BPSNUM_0':'F994','BPRNAM_0':'ahmde test'}]}
        return real_read(args,state,text)
    monkeypatch.setattr(engine,'read',read)
    q.extend([native(call('select_for_modification',resource='supplier',name='ahmde test')),say('Fournisseur F994 identifié. Que souhaitez-vous modifier ?')]);s=send(c,s,'modifier le founissseur ahmde test')
    assert s['state']['modification_drafts'][-1]['code']=='F994' and s['state']['modification_drafts'][-1]['resource']=='supplier'
    assert s['state']['partners'][0]['id']==original and s['state']['partners'][0]['operation']['status']=='cancelled'
    q.extend([native(call('prepare_modification',resource='supplier',code='F994',changes=[{'field':'city','value':'Agadir','evidence':'Agadir'}])),say('Le changement de ville est préparé. Vérifiez les valeurs avant confirmation.')]);s=send(c,s,'sa ville doit être Agadir')
    assert s['state']['modification_drafts'][-1]['changes']=={'city':'Agadir'}
    assert s['state']['modification_drafts'][-1]['operation']['status']=='prepared'
    assert any(m.get('role')=='tool' for r in requests for m in r['body']['messages'])
    assert all(not x['execute'] for x in attempts)

@pytest.mark.parametrize('failure',['cloud','json'])
def test_native_qwen_fallback_uses_the_same_tools(native_chat,failure):
    c,q,requests,_,_,fault=native_chat;fault[failure]=True
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','RIF TEST')])),say('La fiche RIF TEST est prête à relire.')])
    s=send(c,create(c),'crée un fournisseur RIF TEST')
    assert s['state']['partners'][0]['nom']=='RIF TEST' and s['state']['tool_orchestration']['provider']=='ollama'
    assert any('/api/chat' in r['url'] for r in requests)

def test_two_providers_down_cancellation_still_interrupts(native_chat):
    c,_,_,_,_,fault=native_chat;s=create(c);p={'id':str(uuid4()),'kind':'supplier','nom':None,'operation':{'status':'invalidated'}}
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb({'partners':[p],'_supplier_dialogue':{'expected_field':'nom'}}),s['id']))
    s=c.get('/api/v1/chat/conversations/'+s['id']).json();fault.update(cloud=True,local=True)
    s=send(c,s,'annuler cette création je veux modifier')
    assert s['state']['partners'][0]['operation']['status']=='cancelled' and not s['state'].get('_supplier_dialogue')
    assert 'modifier' in s['messages'][-1]['content']

@pytest.mark.parametrize('name,args',[
 ('execute_sql',{'sql':'DROP TABLE TEST.BPARTNER'}),
 ('prepare_draft',{'resource':'supplier','mode':'new','fields':[fact('nom','INVENTED','bonjour')]}),
 ('prepare_draft',{'resource':'supplier','mode':'update','target_id':str(uuid4()),'fields':[fact('nom','RIF TEST')]}),
 ('prepare_modification',{'resource':'article','code':'F999999','changes':[{'field':'deactivate','value':True,'evidence':'bonjour'}]}),
 ('prepare_modification',{'resource':'supplier','code':'F994','changes':[{'field':'activate','value':True,'evidence':'active'}]}),
 ('cancel_request',{'scope':'all','owner_id':str(uuid4())}),
 ('cancel_request',{'scope':'all'}),
])
def test_rejected_tool_cannot_mutate_or_grant_consent(native_chat,name,args):
    c,q,_,_,attempts,_=native_chat;q.extend([native(call(name,**args)),say('Précisez les informations exactes, sans écriture.')])
    s=send(c,create(c),'bonjour RIF TEST active F994')
    assert not s['state'].get('partners') and not s['state'].get('modification_drafts')
    assert s['state']['tool_orchestration']['calls'][0]['result']['ok'] is False and not attempts

def test_three_suppliers_independent_tools_and_result_feedback(native_chat):
    c,q,requests,_,attempts,_=native_chat;names=['ATLAS TEST','RIF TEST','SUD TEST']
    q.extend([native(*[call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom',name),fact('ville','Rabat')]) for name in names]),say('Les trois fiches sont préparées séparément. Vérifiez-les avant confirmation.')])
    s=send(c,create(c),'prépare ATLAS TEST, RIF TEST et SUD TEST à Rabat')
    assert [p['nom'] for p in s['state']['partners']]==names
    assert len({p['id'] for p in s['state']['partners']})==3
    assert all(p['operation']['status']=='prepared' for p in s['state']['partners'])
    assert len([m for m in requests[-1]['body']['messages'] if m['role']=='tool'])==3
    assert all(not x['execute'] for x in attempts)

def test_false_success_is_replaced_with_backend_result(native_chat):
    c,q,_,_,_,_=native_chat;q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','RIF TEST')])),say('Le fournisseur RIF TEST a été créé avec succès dans Sage.')])
    s=send(c,create(c),'créer fournisseur RIF TEST')
    assert 'créé avec succès' not in s['messages'][-1]['content'] and s['state']['partners'][0]['operation']['status']=='prepared'

def test_manual_local_never_calls_cloud(native_chat):
    c,q,requests,_,_,_=native_chat;s=create(c)
    s=c.post('/api/v1/chat/conversations/'+s['id']+'/ai-mode',json={'mode':'local','revision':s['revision']}).json()
    q.append(say('Salam ! Je vous écoute.'));s=send(c,s,'Salam')
    assert all('/api/chat' in r['url'] for r in requests) and s['state']['tool_orchestration']['provider']=='ollama'

def test_how_to_cancel_is_not_a_cancellation():
    assert not engine.cancellation('comment annuler une création ?')
    assert not engine.cancellation('je ne veux pas annuler')
    assert engine.cancellation('annuler cette création je veux modifier')

def test_repeat_tool_call_is_bounded(native_chat):
    c,q,requests,_,_,_=native_chat
    q.extend([native(call('inspect_context')) for _ in range(8)])
    s=send(c,create(c),'résume la conversation')
    assert len(requests)==4 and len(s['state']['tool_orchestration']['calls'])==4

def test_switch_without_target_is_durable_and_suspends_creation(native_chat):
    c,q,_,_,_,_=native_chat
    q.extend([native(call('select_for_modification',resource='supplier')),say('Quel fournisseur souhaitez-vous modifier ?')])
    s=send(c,create(c),'je veux modifier un fournisseur')
    assert s['state']['modification_pending_target']['resource']=='supplier'
    assert s['state']['supplier_creation_hold'] and not s['state'].get('partners')

def test_article_fields_markdown_and_boolean_flags(native_chat):
    c,q,_,_,attempts,_=native_chat
    fields=[fact('code_article','**NATIVE001**'),fact('designation','**BUREAU TEST**'),fact('categorie','avns'),fact('unite','un'),fact('site','202'),fact('gestion_stock','1','non géré en stock'),fact('achete','2','acheté'),fact('vendu','2','vendu'),fact('fournisseurs',[],'sans fournisseur')]
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=fields)),say('La fiche est préparée, vérifiez ses informations.')])
    s=send(c,create(c),'crée article **NATIVE001**, désignation **BUREAU TEST**, catégorie avns, unité un, site 202, non géré en stock, acheté et vendu, sans fournisseur')
    a=s['state']['articles'][0]
    assert a['code_article']=='NATIVE001' and a['designation']=='BUREAU TEST' and a['gestion_stock']=='1' and a['achete']==a['vendu']=='2'
    assert a['categorie']=='AVNS' and a['unite']=='UN' and a['flag_fournisseur']=='1' and not a['fournisseurs']
    assert a['operation']['status']=='prepared'
    assert all(not x['execute'] for x in attempts)

def test_memory_tool_uses_current_user_and_persists(native_chat):
    c,q,_,_,_,_=native_chat
    q.extend([native(call('manage_memory')),say('Votre préférence est enregistrée dans votre mémoire personnelle.')])
    s=send(c,create(c),'Retiens que je préfère des réponses courtes')
    assert s['state']['memory_focus']
    with db.connection() as conn:
        row=conn.execute('SELECT content,source FROM learning_items WHERE id=%s',(s['state']['memory_focus'],)).fetchone()
        assert 'courtes' in row['content'] and s['id'] in row['source']

def test_context_keeps_all_declared_fields_not_only_name_and_city():
    p={'id':'local','nom':'TEST','email':'test@example.test','rc':'000123','adresse':'25 rue du Test','capital':'150000 DH','conditions_paiement':'CHQ30'}
    ctx=engine.context({'partners':[p]})['suppliers'][0]
    assert all(ctx[k]==v for k,v in p.items())

@pytest.mark.parametrize('text',['comment annuler une création ?','je ne veux pas annuler','explique comment annuler'])
def test_discussion_about_cancel_does_not_interrupt(native_chat,text):
    c,q,_,_,_,_=native_chat;q.append(say('Une annulation concerne seulement les propositions non envoyées.'))
    s=send(c,create(c),text)
    assert not s['state'].get('supplier_creation_hold')

def test_document_resolution_keeps_owner_access_checks(native_chat,monkeypatch):
    c,q,_,_,_,_=native_chat;s=create(c);observed=[]
    from app.services import chat_documents
    def denied(owner,conversation,text,state):
        observed.append((str(owner),str(conversation)))
        from app.services.sage_crud import CrudError
        raise CrudError('Document inaccessible pour cet utilisateur.',403)
    monkeypatch.setattr(chat_documents,'turn',denied)
    q.extend([native(call('resolve_document')),say('Le document est inaccessible. Vérifiez le fichier joint.')])
    s=send(c,s,'je confirme la lecture du document')
    assert observed[0][1]==s['id']
    assert not s['state']['tool_orchestration']['calls'][0]['result']['ok']

def test_question_records_model_focus_without_empty_supplier(native_chat):
    c,q,requests,_,_,_=native_chat
    q.append(native(call('respond',intent='CREATE_SUPPLIER',text='Quel est le nom du fournisseur ?',expected_fields=['nom'])))
    s=send(c,create(c),'je veux créer un fournisseur')
    assert s['state']['pending_creation']['resource']=='supplier' and not s['state'].get('partners')
    assert requests[0]['body']['tool_choice']=='required'

def test_respond_tool_cannot_bypass_false_success_guard(native_chat):
    c,q,_,_,_,_=native_chat
    q.append(native(call('respond',intent='CHAT',text='Le fournisseur a été créé avec succès dans Sage.')))
    s=send(c,create(c),'bonjour')
    assert 'créé avec succès' not in s['messages'][-1]['content']

def test_live_stock_tool_reuses_only_the_current_reader(native_chat,monkeypatch):
    c,q,_,_,_,_=native_chat;seen=[]
    from app.services import learning_live
    def read(kind,**kwargs):seen.append((kind,kwargs));return {'ok':True,'folder':'TEST','rows':[{'quantity':'12'}],'definition':'Quantité de la fixture, pas une disponibilité.'}
    monkeypatch.setattr(learning_live,'read',read)
    q.extend([native(call('read_live_stock',code='ART001',site='202')),say('Stock actuel : 12, selon la lecture du site 202.')])
    s=send(c,create(c),'consulte le stock de ART001 au site 202')
    assert seen==[('stock',{'code':'ART001','site':'202'})]
    assert s['state']['tool_orchestration']['calls'][0]['result']['authority']=='read_only'

def test_model_cannot_restart_a_cancelled_creation(native_chat):
    c,q,_,_,_,_=native_chat
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[])),say('La demande est annulée.')])
    s=send(c,create(c),'annuler cette création je veux modifier')
    assert s['state']['supplier_creation_hold'] and not s['state'].get('partners')
    assert s['state']['tool_orchestration']['calls'][-1]['result']['ok'] is False

def test_native_model_can_choose_existing_mcp_readonly_tool(native_chat,monkeypatch):
    c,q,_,reads,attempts,_=native_chat
    monkeypatch.setattr(settings,'sage_mcp_enabled',True)
    q.extend([native(call('sage_get_units',unit='UN')),say('L’unité UN est retournée par la lecture dans TEST.')])
    s=send(c,create(c),'vérifie l’unité UN dans TEST')
    event=s['state']['tool_orchestration']['calls'][0]
    assert event['tool']=='sage_get_units' and event['result']['writes']==0 and event['result']['ok']
    assert not attempts

def test_provider_outage_does_not_retry_in_each_legacy_layer(native_chat):
    c,q,requests,_,_,fault=native_chat;fault.update(cloud=True,local=True)
    s=send(c,create(c),'je veux créer un fournisseur')
    assert len(requests)==3 and sum(bool(r['body'].get('tools')) for r in requests)==2 and s['state']['tool_orchestration']['status']=='fallback'
    assert 'nom' in s['messages'][-1]['content'].lower()

def test_progressive_modification_reuses_draft_and_preserves_other_changes(native_chat):
    c,q,_,_,_,_=native_chat;s=create(c)
    q.extend([native(call('select_for_modification',resource='supplier',code='F994')),say('Quelle information souhaitez-vous modifier ?')]);s=send(c,s,'modifier le fournisseur F994')
    draft_id=s['state']['modification_drafts'][0]['id']
    for field,value in [('city','Agadir'),('phone','0788877766')]:
        q.extend([native(call('prepare_modification',resource='supplier',code='F994',changes=[{'field':field,'value':value,'evidence':value}])),say('Proposition prête à relire avant confirmation.')])
        s=send(c,s,'la nouvelle valeur est '+value)
    assert len(s['state']['modification_drafts'])==1
    d=s['state']['modification_drafts'][0]
    assert d['id']==draft_id and d['changes']=={'city':'Agadir','phone':'0788877766'} and d['operation']['status']=='prepared'

def test_light_local_reply_does_not_restart_the_tool_loop(native_chat,monkeypatch):
    c,q,requests,_,_,fault=native_chat;fault['cloud']=True
    original=httpx.AsyncClient.post
    async def post(self,url,**kw):
        if '/api/chat' in str(url) and kw['json'].get('tools'):
            requests.append({'url':str(url),'body':copy.deepcopy(kw['json'])});raise httpx.ReadTimeout('NATIVE_LOCAL_TOOL_TIMEOUT')
        return await original(self,url,**kw)
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    q.append(say('Bonjour ! Je vous écoute.'));s=send(c,create(c),'Bonjour')
    assert s['messages'][-1]['content']=='Bonjour ! Je vous écoute.'
    assert s['state']['tool_orchestration']['status']=='text_fallback' and len(requests)==3

def test_light_local_default_skips_expensive_tool_catalog(native_chat,monkeypatch):
    c,q,requests,_,_,fault=native_chat;fault['cloud']=True
    monkeypatch.setattr(settings,'conversation_local_tool_calling_enabled',False)
    q.append(say('Bonjour ! Je vous écoute.'));s=send(c,create(c),'Bonjour')
    assert len(requests)==2 and not requests[-1]['body'].get('tools')
    assert s['state']['tool_orchestration']['status']=='text_fallback'

def test_legacy_compatibility_is_typed_and_does_not_grant_write_rights():
    result=engine.dispatch('legacy_module',engine.Legacy(resource='customer'),{},'prépare un client')
    assert result['delegate'] and result['sage_writes']==0
    with pytest.raises(ValueError):engine.dispatch('legacy_module',engine.Legacy(resource='unit'),{},'bonjour')
