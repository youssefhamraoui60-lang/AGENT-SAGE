"""Regression tests complement (do not replace) the real Qwen evaluation campaign."""
import os
from uuid import uuid4
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services import conversation_chat as chat,chat_model,chat_tools,chat_auth,business_store as db,sage_crud as crud,article_agent
REAL_TOOL_RUN=chat_tools.run

pytestmark=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Explicit local PG integration')

class FakeSQL:
    def __call__(self,calls):
        out={}
        for c in calls:
            a=c['args'];t=c['tool'];rows=[]
            if t=='get_article_categories' and a.get('Category'):rows=[{'TCLCOD_0':a['Category'],'STOFCY_0':' ','STU_0':'M2'}]
            if t=='get_units':rows=[{'UOM_0':v} for v in [a.get('Unit'),a.get('Unit2')] if v]
            if t=='get_sites':rows=[{'FCY_0':a.get('Site') or '201','LEGCPY_0':'20'}]
            if t=='search_suppliers' and a.get('Supplier')=='F234':rows=[{'BPSNUM_0':'F234','BPRNAM_0':'Modern for Foam and Plastic','BPRNAM_1':''}]
            if t=='check_article_duplicate' and a.get('Code')=='EXIST001':rows=[{'ITMREF_0':'EXIST001'}]
            out[c['id']]={'ok':True,'rows':rows,'tool':t,'source':'CONTROLLED_FIXTURE'}
        return out

@pytest.fixture
def fixture(monkeypatch):
    # Legacy-controller regressions remain reproducible independently of the
    # native tool-loop tests, which explicitly enable the new architecture.
    monkeypatch.setattr(settings,'conversation_tool_calling_enabled',False)
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',False)
    name='chat_test_'+uuid4().hex[:12]
    monkeypatch.setattr(settings,'business_schema',name);monkeypatch.setattr(settings,'approval_token',SecretStr('test-chat-key'))
    db.migrate();crud.migrate();article_agent.migrate();assert chat.migrate();assert not chat.migrate()
    queue=[]
    async def extract(*args):return chat_model.Delta.model_validate(queue.pop(0)),{'real_model_called':False,'source':'UNIT_TEST_ONLY'}
    monkeypatch.setattr(chat.model,'extract',extract);monkeypatch.setattr(chat.tools,'run',FakeSQL())
    from app.services.chat_storage import migrate as migrate_accounts
    migrate_accounts()
    c=TestClient(app);c.headers.update({'Origin':'http://testserver'})
    r=c.post('/api/v1/chat/auth/register',json={'email':'test-'+uuid4().hex+'@example.test','display_name':'Utilisateur Test','password':'Integration-test-password-2026!'});assert r.status_code==201,r.text
    c.headers.update({'X-Chat-CSRF':r.json()['csrf']})
    yield c,queue
    from psycopg import sql
    with db.connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))

def create(c):return c.post('/api/v1/chat/conversations').json()
def send(c,q,s,text,delta):
    q.append(delta);r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
    assert r.status_code==200,r.text
    return r.json()
def initial():return {'intent':'new','shared':{'categorie':'AR','unite':'M2','fournisseur_nom':'Modern for Foam and Plastic'},'articles':[{'designation':'Modern foam boards A XPS 4 CM'},{'designation':'Modern foam boards B XPS 4 CM'}]}
TEXT='Deux articles Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM, catégorie AR, unité M2, fournisseur Modern for Foam and Plastic.'

def test_two_articles_memory_and_financial_distinction(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial())
    for text,patch in [('131.',{'site':'131'}),('F234.',{'code_fournisseur':'F234'}),('TVA 20 %. ',{'taux_tva':'20'}),('Catégorie comptable Marchandises.',{'accounting_category':'Marchandises'})]:s=send(c,q,s,text,{'intent':'update','shared':patch})
    a=s['state']['articles'];assert len(a)==2
    for i,item in enumerate(a):
        assert item['code_article']==f'MFB-{"AB"[i]}-XPS-40'
        assert item['reference_interne']==f'F234-MFB-{"AB"[i]}-40'
        assert item['categorie']=='AR' and item['accounting_category']=='Marchandises' and item['taux_tva']=='20'
        assert item['site']=='131' and item['site_exclusive'] is None and not item['code_tva']
    assert not any(x['field'] in ['site','unite','code_fournisseur'] for x in s['state']['pending'])

def test_correction_invalidates_approval_and_scopes_target(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 201.',{**initial(),'shared':{**initial()['shared'],'site':'201'}})
    owner=chat_auth.identity if False else None
    with db.connection() as conn:
        row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()
        row['state']['articles'][0]['approved']=True
        chat.PERMITS[row['state']['articles'][0]['id']]={'synthetic':True}
        chat.save_conversation_context(conn,row['owner_id'],s['id'],row['state'])
    s=send(c,q,s,'Pour le premier article : site 131.',{'intent':'update','targets':[1],'shared':{'site':'131'}})
    a=s['state']['articles'];assert a[0]['site']=='131' and a[1]['site']=='201'
    assert not a[0].get('approved') and a[0]['id'] not in chat.PERMITS

def test_session_cookie_csrf_and_owner_isolation(fixture):
    c,q=fixture;s=create(c)
    response=c.get('/api/v1/chat/session');assert response.status_code==200
    cookie=c.cookies.get(chat_auth.COOKIE);assert cookie
    other=TestClient(app);other.headers['Origin']='http://testserver'
    r=other.post('/api/v1/chat/auth/register',json={'email':'other-'+uuid4().hex+'@example.test','display_name':'Autre utilisateur','password':'Integration-test-password-2026!'});other.headers['X-Chat-CSRF']=r.json()['csrf']
    assert other.get('/api/v1/chat/conversations/'+s['id']).status_code==404
    assert not other.get('/api/v1/chat/conversations').json()['conversations']
    c.headers['X-Chat-CSRF']='wrong';assert c.post('/api/v1/chat/conversations').status_code==403
    assert TestClient(app).get('/api/v1/chat/conversations').status_code==401

def test_cross_site_and_network_bootstrap_refused(fixture):
    c,q=fixture
    c.headers['Origin']='https://evil.example';assert c.post('/api/v1/chat/session').status_code==403
    lan=TestClient(app,client=('192.168.9.99',1234));lan.headers['Origin']='http://testserver'
    assert lan.post('/api/v1/chat/session').status_code==403

def test_duplicate_and_sql_failure_do_not_become_creations(fixture,monkeypatch):
    c,q=fixture
    s=send(c,q,create(c),'Crée un article Collision, code article EXIST001, catégorie NEG, unité UN, site 201.',{'intent':'new','shared':{'code_article':'EXIST001','categorie':'NEG','unite':'UN','site':'201'},'articles':[{'designation':'Collision'}]})
    assert 'duplicate_article_code' in s['state']['articles'][0]['checks']['errors']
    monkeypatch.setattr(chat.tools,'run',lambda calls:{c['id']:{'ok':False,'rows':[]} for c in calls})
    s=send(c,q,s,'TVA 20 %. ',{'intent':'update','shared':{'taux_tva':'20'}})
    assert 'sql_checks_incomplete' in s['state']['articles'][0]['checks']['errors']
    assert not s['state']['articles'][0]['checks']['sage_created']

def test_unknown_secrets_and_ungrounded_values(fixture):
    c,q=fixture;s=create(c)
    assert c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'APPROVAL_TOKEN=test-chat-key','revision':s['revision']}).status_code==422
    s=send(c,q,s,'Crée un article Panneau simple.',{'intent':'new','articles':[{'designation':'Panneau simple','code_fournisseur':'F999','unite':'M2','taux_tva':'20'}]})
    a=s['state']['articles'][0];assert not a['code_fournisseur'] and not a['unite'] and not a['taux_tva']

def test_ten_articles_keep_own_category_and_unit(fixture):
    c,q=fixture
    rows=[{'designation':'Test '+str(i),'categorie':'AR' if i%2 else 'NEG','unite':'M2' if i%2 else 'UN'} for i in range(1,11)]
    text='Créer : '+ '; '.join(f"{r['designation']}, catégorie {r['categorie']}, unité {r['unite']}" for r in rows)
    s=send(c,q,create(c),text,{'intent':'new','articles':rows})
    assert len(s['state']['articles'])==10
    assert [(a['categorie'],a['unite']) for a in s['state']['articles']]==[(r['categorie'],r['unite']) for r in rows]

def test_sage_gate_applies_even_with_chat_session(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());a=s['state']['articles'][0]
    for action in ['prepare','approve','execute']:
        r=c.post(f"/api/v1/chat/conversations/{s['id']}/articles/{a['id']}/{action}",json={'revision':s['revision'],'confirm':True})
        assert r.status_code==423,r.text

def test_stale_revision_and_format_rejected(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial())
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'131.','revision':1})
    assert r.status_code==409
    with pytest.raises(ValueError):REAL_TOOL_RUN([{'id':'0','tool':'DELETE FROM TEST.ITMMASTER','args':{}}])

def test_model_failure_keeps_draft_and_allows_resume(fixture,monkeypatch):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());before=s['state']['articles']
    async def fail(*args):raise ValueError('synthetic_model_failure')
    monkeypatch.setattr(chat.model,'extract',fail)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'131.','revision':s['revision']})
    assert r.status_code==502
    restored=c.get('/api/v1/chat/conversations/'+s['id']).json()
    assert restored['state']['articles']==before and '_pending' not in restored['state']

def test_no_exclusivity_or_official_supplier_reference_invented(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 131. Code fournisseur F234.',{**initial(),'shared':{**initial()['shared'],'site':'131','code_fournisseur':'F234','site_exclusive':True}})
    for a in s['state']['articles']:
        assert a['site_exclusive'] is None
        assert not a['checks']['supplier_reference_official']

def test_initial_need_is_kept_as_draft_even_when_model_says_lookup(fixture):
    c,q=fixture
    s=send(c,q,create(c),'Besoin article Panneau incomplet ; cat AR ; unité M2.',{'intent':'lookup','shared':{'categorie':'AR','unite':'M2'},'articles':[{'designation':'Panneau'}]})
    assert len(s['state']['articles'])==1
    assert s['state']['articles'][0]['designation']=='Panneau incomplet'
    assert any(v['field']=='site' for v in s['state']['pending'])

def test_literal_single_article_declaration_survives_empty_model_entities(fixture):
    c,q=fixture
    s=send(c,q,create(c),'Besoin article Panneau incomplet ; cat AR ; unité M2.',{'intent':'lookup','shared':{'unite':'M2','compte_general':'AR'}})
    assert s['state']['articles'][0]['designation']=='Panneau incomplet'
    assert s['state']['articles'][0]['categorie']=='AR'
    assert any(v['field']=='site' for v in s['state']['pending'])

def test_creation_label_and_duplicate_are_kept_when_model_omits_designation(fixture):
    c,q=fixture
    text='Création demandée : Test collision. Code article : EXIST001 ; site 201 ; unité UN ; catégorie NEG.'
    s=send(c,q,create(c),text,{'intent':'new','shared':{'site':'201','compte_general':'NEG'},'articles':[{'code_article':'EXIST001','unite':'UN'}]})
    assert s['state']['articles'][0]['designation']=='Test collision'
    assert 'duplicate_article_code' in s['state']['articles'][0]['checks']['errors']

def test_reader_role_cannot_mutate_and_expiry_refuses_session(fixture):
    c,q=fixture
    with db.connection() as conn:conn.execute("UPDATE chat_web_sessions SET role='reader'")
    assert c.get('/api/v1/chat/conversations').status_code==200
    assert c.post('/api/v1/chat/conversations').status_code==403
    with db.connection() as conn:conn.execute("UPDATE chat_web_sessions SET expires_at=now()-interval '1 minute'")
    assert c.get('/api/v1/chat/conversations').status_code==401

def test_correction_revokes_actual_local_approval_record(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());a=s['state']['articles'][0]
    request=db.create_request('Contrôle local approuvé AR M2',{'synthetic':True})
    article_agent.create(request,{'intention':'create_article','articles':[{'designation':'Contrôle local','categorie':'AR','unite':'M2'}]})
    operation=uuid4()
    from psycopg.types.json import Jsonb
    with db.connection() as conn:
        conn.execute('INSERT INTO soap_operations(id,resource,action,record_keys,payload,object_xml,digest,description_hash,status,checks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(operation,'articles','create',Jsonb({'ITMREF':'SYNTH'}),Jsonb({}),'<PARAM/>','a'*64,'b'*64,'approved',Jsonb({})))
        conn.execute("INSERT INTO soap_operation_approvals(operation_id,digest,token_sha256,actor,reason,expires_at) VALUES (%s,%s,%s,'SYNTH','TEST',now()+interval '10 minute')",(operation,'a'*64,'c'*64))
        conn.execute('UPDATE article_agent_drafts SET operation_id=%s WHERE id=%s',(operation,request))
        row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()
        row['state']['articles'][0].update(legacy_id=str(request),approved=True,operation={'id':str(operation)})
        chat.save_conversation_context(conn,row['owner_id'],s['id'],row['state'])
    s=send(c,q,s,'Pour le premier article : site 131.',{'intent':'update','targets':[1],'shared':{'site':'131'}})
    assert 'operation' not in s['state']['articles'][0]
    with db.connection() as conn:
        assert conn.execute('SELECT status FROM soap_operations WHERE id=%s',(operation,)).fetchone()['status']=='invalidated'
        assert conn.execute('SELECT consumed_at FROM soap_operation_approvals WHERE operation_id=%s',(operation,)).fetchone()['consumed_at']

def test_explicit_confirmation_is_a_real_boolean(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());a=s['state']['articles'][0]
    r=c.post(f"/api/v1/chat/conversations/{s['id']}/articles/{a['id']}/review",json={'revision':s['revision'],'confirm':'true'})
    assert r.status_code==422

def test_literal_financial_declarations_override_wrong_model_classification(fixture):
    c,q=fixture
    text=TEXT+' Site 131. Code fournisseur F234. TVA 20 %. Catégorie comptable Marchandises.'
    delta={**initial(),'shared':{'unite':'M2','accounting_category':'AR','code_comptable':'F234','taux_tva':'20','fournisseur_nom':'Modern for Foam and Plastic'}}
    s=send(c,q,create(c),text,delta)
    for a in s['state']['articles']:
        assert a['accounting_category']=='Marchandises' and a['categorie']=='AR'
        assert a['taux_tva']=='20' and not a['code_comptable'] and a['code_fournisseur']=='F234'

def test_unrelated_reply_cannot_copy_first_article_code_over_second(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial())
    codes=[a['code_article'] for a in s['state']['articles']]
    s=send(c,q,s,'TVA 20 %. ',{'intent':'update','shared':{'taux_tva':'20','code_article':codes[0]}})
    assert [a['code_article'] for a in s['state']['articles']]==codes

def test_generate_request_cannot_recreate_context_articles(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial())
    before=[(a['id'],a['designation'],a['code_article']) for a in s['state']['articles']]
    s=send(c,q,s,'Tu dois créer toi-même les codes articles et les références.',initial())
    assert [(a['id'],a['designation'],a['code_article']) for a in s['state']['articles']]==before

def test_explicit_article_category_repairs_truncated_accounting_label(fixture):
    c,q=fixture
    text='Prépare Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Catégorie comptable : Marchandises ; TVA 20 % ; site 131 ; catégorie article AR ; unité M2.'
    delta={'intent':'new','shared':{'categorie':'March','taux_tva':'20'},'articles':[{'designation':f'Modern foam boards {v} XPS 4 CM','unite':'M2','accounting_category':'Marchandises'} for v in 'AB']}
    s=send(c,q,create(c),text,delta)
    assert all(a['categorie']=='AR' and a['accounting_category']=='Marchandises' for a in s['state']['articles'])

def test_reversed_financial_declaration_and_article_category_are_distinct(fixture):
    c,q=fixture
    text=TEXT+' Site 131. Marchandises est la catégorie comptable ; TVA 20 %.'
    delta={**initial(),'shared':{'unite':'M2','accounting_category':'AR','taux_tva':'20','fournisseur_nom':'Modern for Foam and Plastic'}}
    s=send(c,q,create(c),text,delta)
    assert all(a['accounting_category']=='Marchandises' and a['categorie']=='AR' for a in s['state']['articles'])

def test_reviewed_corrections_feed_only_same_owner_rag(fixture,monkeypatch):
    c,q=fixture
    s=send(c,q,create(c),'Crée un article Pierre, catégorie NEG, unité UN, site 201.',{'intent':'new','shared':{'categorie':'NEG','unite':'UN','site':'201'},'articles':[{'designation':'Pierre'}]})
    a=s['state']['articles'][0];url=f"/api/v1/chat/conversations/{s['id']}/articles/{a['id']}/review"
    assert c.post(url,json={'revision':s['revision'],'confirm':True}).status_code==200
    assert c.post(url,json={'revision':s['revision'],'confirm':True}).status_code==409
    s=send(c,q,s,'Correction : unité M2.',{'intent':'update','shared':{'unite':'M2'}})
    assert not s['state']['articles'][0].get('reviewed')
    assert c.post(url,json={'revision':s['revision'],'confirm':True}).status_code==200
    examples_seen=[]
    async def model(message,state,history,examples):
        examples_seen.append(examples)
        return chat_model.Delta(intent='other'),{'real_model_called':False,'source':'UNIT_TEST_ONLY'}
    monkeypatch.setattr(chat.model,'extract',model)
    session=create(c)
    r=c.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':'Pierre M2','revision':session['revision']})
    assert r.status_code==200 and any(e.get('unite')=='M2' for e in examples_seen[-1])
    other=TestClient(app);other.headers['Origin']='http://testserver'
    response=other.post('/api/v1/chat/auth/register',json={'email':'rag-other-'+uuid4().hex+'@example.test','display_name':'Autre compte RAG','password':'Rag-isolation-example-2026!'})
    assert response.status_code==201,response.text
    other.headers['X-Chat-CSRF']=response.json()['csrf']
    session=create(other)
    assert other.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':'Pierre M2','revision':session['revision']}).status_code==200
    assert not examples_seen[-1]

@pytest.mark.parametrize('message',['Et pour le site, est-ce qu’il existe ?','ET POUR LE SITE est-ce qu’il y a ou non ?','ET POUR LE SITE est ce que il y a ou non ','Vérifie le site 131','Et pour le fournisseur ?','Le site est-il 201 ?'])
def test_questions_and_verifications_cannot_mutate_drafts(fixture,message):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 131. Fournisseur F234.',{**initial(),'shared':{**initial()['shared'],'site':'131','code_fournisseur':'F234'}})
    before=[{k:a[k] for k in chat.FIELDS} for a in s['state']['articles']]
    # Deliberately wrong model output reproduces the real failure, independently of its prompt.
    s=send(c,q,s,message,{'intent':'update','shared':{'site':'EST','code_fournisseur':'F999','categorie':'NEG'},'articles':[{'index':1,'site':'201'}]})
    assert [{k:a[k] for k in chat.FIELDS} for a in s['state']['articles']]==before
    assert s['state']['last_turn']['readonly'] is True

def test_readonly_question_does_not_regenerate_code_when_new_collision_is_found(fixture,monkeypatch):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());codes=[a['code_article'] for a in s['state']['articles']]
    base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='check_article_duplicate':out[call['id']]['rows']=[{'ITMREF_0':call['args']['Code']}]
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,s,'Et pour le site, est-ce qu’il existe ?',{'intent':'update','shared':{'site':'EST'}})
    assert [a['code_article'] for a in s['state']['articles']]==codes
    assert all('duplicate_article_code' in a['checks']['errors'] for a in s['state']['articles'])

@pytest.mark.parametrize('message,expected',[('Change le site 131 vers 201','201'),('Le site est 131','131'),('Remplace le site 131 par 201','201'),('Remplace le site par 131 pour les deux articles.','131')])
def test_site_declaration_and_correction_destination(fixture,message,expected):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 131.',{**initial(),'shared':{**initial()['shared'],'site':'131'}})
    s=send(c,q,s,message,{'intent':'update','shared':{'site':'EST'}})
    assert all(a['site']==expected for a in s['state']['articles'])

def test_category_label_lookup_requires_confirmation(fixture,monkeypatch):
    c,q=fixture;base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='get_article_categories' and call['args'].get('Label')=='NEGOSE':
                out[call['id']]['rows']=[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':' ','STU_0':'UN'}]
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,create(c),TEXT,initial())
    s=send(c,q,s,'Recherche la catégorie « NEGOSE ». ',{'intent':'update','shared':{'categorie':'NEG'}})
    assert all(a['categorie']=='AR' and a['proposals']['categorie']=='NEG' for a in s['state']['articles'])
    assert s['state']['awaiting_confirmation']['value']=='NEG'
    s=send(c,q,s,'Oui.',{'intent':'other'})
    assert all(a['categorie']=='NEG' for a in s['state']['articles'])
    assert 'awaiting_confirmation' not in s['state']

@pytest.mark.parametrize('message',['Recherche la catégorie « NEGOSE ».','Recherche la catégorie NEGOSE.','Recherche la catégorie "NEGOSE".','Vérifie la catégorie NÉGOCE.'])
def test_category_lookup_never_extracts_suffix_from_keyword(message):
    from app.services.chat_turns import analyse
    result=analyse(message,{'articles':[]})
    assert result.lookups['categorie'] in ['NEGOSE','NEGOCE']
    assert result.readonly and result.values=={}

def test_supplier_correction_archives_derived_references(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 131. Fournisseur F234.',{**initial(),'shared':{**initial()['shared'],'site':'131','code_fournisseur':'F234'}})
    ids=[a['id'] for a in s['state']['articles']]
    s=send(c,q,s,'F992.',{'intent':'update','shared':{'code_fournisseur':'F234'}})
    assert [a['id'] for a in s['state']['articles']]==ids
    for i,a in enumerate(s['state']['articles']):
        assert a['code_fournisseur']=='F992' and a['reference_interne']==f'F992-MFB-{"AB"[i]}-40'
        assert a['obsolete_derived_values'][-1]['value']==f'F234-MFB-{"AB"[i]}-40'
        assert a['obsolete_derived_values'][-1]['obsolete'] is True
    assert not any(p['field']=='code_fournisseur' for p in s['state']['pending'])

@pytest.mark.parametrize('message',['Change le fournisseur F234 vers F992','Remplace le fournisseur F234 par F992','Remplace le fournisseur par F992'])
def test_supplier_correction_uses_destination_not_old_code(message):
    from app.services.chat_turns import analyse
    assert analyse(message,{}).values['code_fournisseur']=='F992'

def test_supplier_name_starting_with_f_is_not_a_silent_code():
    from app.services.chat_turns import analyse
    assert 'code_fournisseur' not in analyse('Fournisseur Foam and Plastic',{}).values
    assert 'code_fournisseur' not in analyse('Foam.',{}).values
    assert analyse('Code fournisseur FOAM',{}).values['code_fournisseur']=='FOAM'

def test_actual_misspelled_mixed_verification_preserves_other_fields(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 131.',{**initial(),'shared':{**initial()['shared'],'site':'131'}})
    text="pour la ctigorier c'est NEGOSE vérifier si il y a déaja comme ce nome pour le fornisseur est F992"
    s=send(c,q,s,text,{'intent':'update','shared':{'site':'EST','categorie':'NEG','code_fournisseur':'F234'},'articles':[{'index':1,'site':'201'}]})
    assert all(a['site']=='131' and a['categorie']=='AR' and a['code_fournisseur']=='F992' for a in s['state']['articles'])
    assert s['state']['lookup_requests']['categorie']=='NEGOSE'
    assert s['state']['last_turn']['restricted'] is True

@pytest.mark.parametrize('text',['Vérifie le site 131 et le fournisseur F992','Vérifie le site 131 et le fournisseur est F992'])
def test_verification_of_two_fields_does_not_turn_second_into_declaration(fixture,text):
    c,q=fixture;s=send(c,q,create(c),TEXT+' Site 201. Fournisseur F234.',{**initial(),'shared':{**initial()['shared'],'site':'201','code_fournisseur':'F234'}})
    s=send(c,q,s,text,{'intent':'update','shared':{'site':'131','code_fournisseur':'F992'}})
    assert all(a['site']=='201' and a['code_fournisseur']=='F234' for a in s['state']['articles'])
    assert s['state']['last_turn']['readonly'] is True

def test_missing_sites_preserve_value_and_show_only_sql_choices(fixture,monkeypatch):
    c,q=fixture;base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='get_sites':out[call['id']]['rows']=[] if call['args'].get('Site')=='131' else [{'FCY_0':v} for v in ['201','202','209','301']]
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,create(c),TEXT+' Site 131.',{**initial(),'shared':{**initial()['shared'],'site':'131'}})
    response=[m for m in s['messages'] if m['role']=='assistant'][-1]['content']
    assert all(a['site']=='131' and 'unknown:site' in a['checks']['errors'] for a in s['state']['articles'])
    assert '201, 202, 209, 301' in response and 'absence de tout Sage' in response

def test_similar_article_tax_codes_follow_real_reference_chain(fixture,monkeypatch):
    c,q=fixture;base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='search_articles':out[call['id']]['rows']=[{'ITMREF_0':'E-XPS_8','TCLCOD_0':'NEG','STU_0':'M2','ACCCOD_0':'POLYSTYREN','VACITM_0':'T20'}]
            if call['tool']=='get_accounting_categories':out[call['id']]['rows']=[{'ACCCOD_0':'POLYSTYREN','DES_0':'Polystyrène','TYP_0':1}]
            if call['tool']=='get_tax_determination':out[call['id']]['rows']=[{'VACITM_0':'T20','VAT_0':'T20','VACBPR_0':'MAR'}]
            if call['tool']=='get_tax_rules':out[call['id']]['rows']=[{'VAT_0':'T20','VATRAT_0':20}]
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,create(c),TEXT,initial())
    assert s['title']!='Nouvelle conversation'
    for a in s['state']['articles']:
        assert a['suggestions'][0]['tax_rates'][0]['VAT_0']=='T20'
        assert a['suggestions'][0]['accounting_reference'][0]['ACCCOD_0']=='POLYSTYREN'
        assert not a['code_tva'] and not a['code_comptable'] and not a['niveau_taxe']
        assert a['suggestions'][0]['applied'] is False

def test_category_exists_only_for_another_site_is_not_globally_absent(fixture,monkeypatch):
    c,q=fixture;base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='get_article_categories':
                out[call['id']]['rows']=[] if call['args'].get('Site') else [{'TCLCOD_0':'AR','STOFCY_0':'201','STU_0':'M2'}]
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,create(c),TEXT+' Site 131.',{**initial(),'shared':{**initial()['shared'],'site':'131'}})
    assert all('category_not_applicable_for_site' in a['checks']['errors'] and 'unknown:categorie' not in a['checks']['errors'] for a in s['state']['articles'])

def test_supplier_unavailable_is_not_reported_as_absent(fixture,monkeypatch):
    c,q=fixture;base=FakeSQL()
    def sql(calls):
        out=base(calls)
        for call in calls:
            if call['tool']=='search_suppliers':out[call['id']].update(ok=False,rows=[])
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    s=send(c,q,create(c),TEXT+' Fournisseur F992.',{**initial(),'shared':{**initial()['shared'],'code_fournisseur':'F992'}})
    assert all('supplier_lookup_unavailable' in a['checks']['errors'] and 'supplier_code_not_verified' not in a['checks']['errors'] for a in s['state']['articles'])
    assert 'consultation est indisponible' in [m for m in s['messages'] if m['role']=='assistant'][-1]['content']

def test_cancellation_retains_values_and_revokes_approval(fixture):
    c,q=fixture;s=send(c,q,create(c),TEXT,initial());before=s['state']['articles']
    s=send(c,q,s,'Annule la demande.',{'intent':'update','shared':{'categorie':'NEG','site':'EST'}})
    assert s['state']['workflow']=='cancelled'
    assert [{k:a.get(k) for k in chat.FIELDS} for a in s['state']['articles']]==[{k:a.get(k) for k in chat.FIELDS} for a in before]
