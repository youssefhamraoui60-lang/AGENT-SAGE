"""Conversation tests: real isolated local PG, mocked SQL/Sage/model; never ERP writes."""
import os,json
from copy import deepcopy
from uuid import uuid4
import pytest
from lxml import etree
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services import article_agent as agent,business_store as db,sage_crud as crud
from app.api import article_agent as api
from test_sage_crud import FakeGateway,metadata as old_metadata

pytestmark=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Explicit local integration tests only')

def sql_result(draft):
    return {'ok':True,'folder':'TEST','article':[],'designation_matches':[],
            'category':[{'TCLCOD_0':draft.categorie}],'unit':[{'UOM_0':draft.unite}],
            'site':[{'FCY_0':draft.site}],'supplier':[],'reference':[]}

def draft():
    return agent.Draft(code_article='SYNTHCHAT001',designation='Ciment test',categorie='NEG',unite='UN',site='201')

@pytest.fixture
def client(monkeypatch):
    schema='agent_chat_test_'+uuid4().hex[:12]
    monkeypatch.setattr(settings,'business_schema',schema)
    monkeypatch.setattr(settings,'approval_token',SecretStr('synthetic-chat-token'))
    db.migrate();crud.migrate();assert agent.migrate();assert not agent.migrate()
    monkeypatch.setattr(agent,'sql_check',sql_result)
    monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':True,'blockers':[],'folder':'TEST'})
    # This fixture simulates an authorized publication. Its business evidence is
    # simulated too; the actual evidence gate is exercised in test_sage_article_rules.
    monkeypatch.setattr(crud,'check_article_rules',lambda *a:{'validated':True,'rules_sha256':'synthetic-fixture'})
    def metadata(resource):
        root=old_metadata(resource)
        if resource=='articles':
            data=root.find('ADXDATA')
            for group,fields in [('ITM0_1',['TCLCOD','ITMSTA']),('ITM3_1',['STU','PUU','SAU','PUUSTUCOE','SAUSTUCOE'])]:
                node=data.find("GRP[@NAM='"+group+"']")
                if node is None:node=etree.SubElement(data,'GRP',NAM=group,TYB='List',DIM='1')
                for field in fields:etree.SubElement(node,'FLD',NAM=field,MOD='Input',TYP='Char',LEN='10',DIM='1')
        return root
    monkeypatch.setattr('test_sage_crud.metadata',metadata)
    FakeGateway.records={};FakeGateway.writes=[];FakeGateway.fail_after_write=False
    monkeypatch.setattr(crud,'Gateway',FakeGateway)
    async def analyze(body):
        p={'intention':'create_article','articles':[{**draft().model_dump(),'famille':None}],
           'fournisseurs':[],'ambigu':False,'questions':[]}
        identifier=db.create_request(body.demande,{'synthetic':True})
        return {'id':identifier,'proposition':p}
    monkeypatch.setattr(api,'analyze_business',analyze)
    c=TestClient(app);c.headers.update({'X-Approval-Token':'synthetic-chat-token'})
    yield c
    # Only this fixture-owned local PG schema is removed; ERP never touched.
    from psycopg import sql
    with db.connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def create(client):
    r=client.post('/api/v1/article-agent/conversations',json={'message':'Crée Ciment test code SYNTHCHAT001 catégorie NEG unité UN site 201'})
    assert r.status_code==200,r.text
    return r.json()

def action(client,value,name,extra=None):
    return client.post('/api/v1/article-agent/conversations/'+value['id']+'/'+name,json={'revision':value['revision'],**(extra or {})})

def prepared(client):
    value=create(client)
    r=action(client,value,'validate');assert r.status_code==200,r.text
    value=r.json();assert value['validated']
    r=action(client,value,'prepare');assert r.status_code==200,r.text
    return r.json()

def test_conversation_validation_and_correction_invalidates_old_state(client):
    value=prepared(client)
    assert value['operation'] and not FakeGateway.writes
    data=value['draft'];data['designation']='Ciment corrigé'
    r=client.patch('/api/v1/article-agent/conversations/'+value['id'],json={'revision':value['revision'],'draft':data})
    assert r.status_code==200,r.text
    changed=r.json();assert not changed['validated'] and changed['operation'] is None
    assert action(client,value,'validate').status_code==409
    assert action(client,changed,'prepare').status_code==409
    assert client.get('/api/v1/article-agent/conversations').json()['conversations']

@pytest.mark.parametrize('failure', ['duplicate','offline','unknown_unit'])
def test_fail_closed_sql_validation(client,monkeypatch,failure):
    def check(d):
        r=sql_result(d)
        if failure=='duplicate':r['article']=[{'ITMREF_0':d.code_article}]
        if failure=='offline':r={'ok':False}
        if failure=='unknown_unit':r['unit']=[]
        return r
    monkeypatch.setattr(agent,'sql_check',check)
    value=create(client);r=action(client,value,'validate')
    assert r.status_code==200
    assert not r.json()['validated'] and not r.json()['validation']['valid']
    assert not FakeGateway.writes

def test_human_approval_distinct_and_single_use_execution(client,monkeypatch):
    value=prepared(client);op=value['operation']
    invalid={'execution':{'operation_id':op['id'],'approval_token':'invented'}}
    assert action(client,value,'execute',invalid).status_code==403
    approve={'approval':{'digest':op['digest'],'actor':'SYNTHETIC REVIEWER','reason':'Mock write authorized in test only','confirm':True}}
    r=action(client,value,'approve',approve);assert r.status_code==200,r.text
    nonce=r.json()['approval_token']
    def check(d):
        r=sql_result(d)
        if FakeGateway.writes:r['article']=[{'ITMREF_0':d.code_article,'ITMDES1_0':d.designation,'TCLCOD_0':d.categorie,'STU_0':d.unite,'PUU_0':d.unite,'SAU_0':d.unite}]
        return r
    monkeypatch.setattr(agent,'sql_check',check)
    execution={'execution':{'operation_id':op['id'],'approval_token':nonce}}
    r=action(client,value,'execute',execution);assert r.status_code==200,r.text
    assert r.json()['outcome']['confirmed']
    assert r.json()['outcome']['site_creation_executed'] is False
    assert len(FakeGateway.writes)==1
    assert action(client,value,'execute',execution).status_code==409
    assert len(FakeGateway.writes)==1
    r=client.patch('/api/v1/article-agent/conversations/'+value['id'],json={'revision':value['revision'],'draft':value['draft']})
    assert r.status_code==409
    assert nonce not in json.dumps(client.get('/api/v1/article-agent/conversations/'+value['id']).json())

def test_security_gate_never_bypassed(client,monkeypatch):
    value=prepared(client)
    monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':False,'blockers':['VERIFIED_HTTPS_REQUIRED'],'folder':'TEST'})
    r=action(client,value,'approve',{'approval':{'digest':value['operation']['digest'],'actor':'SYNTH','reason':'Should remain blocked','confirm':True}})
    assert r.status_code==423
    r=action(client,value,'execute',{'execution':{'operation_id':value['operation']['id'],'approval_token':'invented'}})
    assert r.status_code==423 and not FakeGateway.writes

def test_no_secrets_or_anonymous_analysis(client):
    assert client.post('/api/v1/article-agent/conversations',json={'message':'mot de passe=secret'}).status_code==422
    assert client.post('/api/v1/article-agent/conversations',json={'message':'mon mot de passe est secret'}).status_code==422
    assert client.post('/api/v1/article-agent/conversations',json={'message':'Utilise synthetic-chat-token dans le modèle'}).status_code==422
    client.headers.clear()
    assert client.get('/api/v1/article-agent/conversations').status_code==403
    assert client.post('/api/v1/article-agent/conversations',json={'message':'article'}).status_code==403

def test_optional_supplier_not_silently_dropped(client):
    d=draft();d.code_fournisseur='SYNTHSUP'
    result=agent.evaluate(d,sql_result(d))
    assert 'supplier_link_mapping_requires_review' in result['errors']

def test_ungrounded_category_and_unit_removed(client):
    identifier=db.create_request('Crée Ciment test',{'synthetic':True})
    value=agent.create(identifier,{'intention':'create_article','articles':[draft().model_dump()]})
    assert value['draft']['categorie']==value['draft']['unite']==''
    assert value['history'][0]['payload']['ungrounded_fields_removed']==['categorie','unite']

def test_article_preparation_omits_unrequested_associations(client):
    d=draft();d.designation='Ciment <A> & B'
    preparation=agent.preparation(d)
    assert preparation.keys=={'ITMREF':'SYNTHCHAT001'}
    assert not any(f.name in ['STOFCY','BPSNUM','ACCCOD'] for f in preparation.fields)

def test_duplicate_appearing_after_validation_blocks_preparation(client,monkeypatch):
    value=create(client);value=action(client,value,'validate').json()
    monkeypatch.setattr(agent,'sql_check',lambda d:{**sql_result(d),'article':[{'ITMREF_0':d.code_article}]})
    assert action(client,value,'prepare').status_code==409
    assert not FakeGateway.writes

def test_sql_mismatch_after_sage_success_is_not_confirmed(client,monkeypatch):
    value=prepared(client);op=value['operation']
    r=action(client,value,'approve',{'approval':{'digest':op['digest'],'actor':'SYNTH','reason':'Mock only for comparison','confirm':True}})
    assert r.status_code==200
    # Fake Sage succeeds; SQL remains empty. Must never claim confirmed creation.
    r=action(client,value,'execute',{'execution':{'operation_id':op['id'],'approval_token':r.json()['approval_token']}})
    assert r.status_code==200,r.text
    assert r.json()['operation']['status']=='succeeded'
    assert not r.json()['outcome']['confirmed']
    assert len(FakeGateway.writes)==1

def test_confirmation_must_be_explicit_boolean(client):
    value=prepared(client)
    r=action(client,value,'approve',{'approval':{'digest':value['operation']['digest'],'actor':'SYNTH','reason':'Not an explicit approval','confirm':False}})
    assert r.status_code==422 and not FakeGateway.writes
