"""HTTP workflows against a simulated SOAP gateway and real isolated local PostgreSQL."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,json
import os
from types import SimpleNamespace
import pytest
from lxml import etree
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services import sage_crud as service,business_store as db
from app.api import sage_crud as api
from app.services.sage_gateway import RESOURCES,build_xml,digest,projection,OneShotTransport
from app.services.sage_soap import SageError,SOAP_NS,NS,SOAP_PATH

def metadata(resource):
    spec=RESOURCES[resource]
    root=etree.Element('ADXDOC',FOL='TEST',SOL='V12',PNA=spec['publication'],OBJ=spec['object'],USER='TEST_TECH',TIM=str(uuid4()))
    data=etree.SubElement(root,'ADXDATA');groups={}
    fields=[(spec['key_group'],key,'Char','20','1') for key in spec['keys']]
    fields += [('ITM0_1','DES1AXX','Char','70','1')] if resource=='articles' else ([('BPRS_1','BPRNAM','Char','35','2'),('BPRS_1','BPRSHO','Char','10','1')] if resource=='suppliers' else [('ITF1_2','ABCCLS','Integer','16','1')])
    for group,name,typ,length,dim in fields:
        if group not in groups:groups[group]=etree.SubElement(data,'GRP',NAM=group,TYB='List',DIM='1')
        etree.SubElement(groups[group],'FLD',NAM=name,MOD='Input',TYP=typ,LEN=length,DIM=dim)
    read=etree.SubElement(root,'ADXREAD');group=etree.SubElement(read,'GRP')
    for key in spec['keys']:etree.SubElement(group,'FLD',NAM=key)
    methods=etree.SubElement(root,'ADXSER')
    for method in ['READ','LIST','CREATE','MODIFY']:etree.SubElement(methods,'MET',ID=method)
    return root

def body(resource,action='create'):
    keys={'ITMREF':'SYNTH_ITM'} if resource=='articles' else ({'BPSNUM':'SYNTH_BPS'} if resource=='suppliers' else {'ITMREF':'SYNTH_ITM','STOFCY':'TST'})
    field={'group':'ITM0_1','name':'DES1AXX','value':'SYNTH ARTICLE'} if resource=='articles' else ({'group':'BPRS_1','name':'BPRNAM','value':['SYNTH SUPPLIER','']} if resource=='suppliers' else {'group':'ITF1_2','name':'ABCCLS','value':'1'})
    if action=='update':field['value']=['SYNTH MODIFIED',''] if resource=='suppliers' else ('SYNTH MODIFIED' if resource=='articles' else '2')
    return {'action':action,'keys':keys,'fields':[field]}

class FakeGateway:
    records={};writes=[];fail_after_write=False;read_count=0
    def __init__(self,resource):self.resource=resource;self.spec=RESOURCES[resource]
    def describe(self):return metadata(self.resource)
    def read(self,keys,describe=True):
        type(self).read_count+=1
        key=(self.resource,json.dumps(keys,sort_keys=True))
        fields=self.records.get(key)
        return {'exists':fields is not None,'keys':keys,'status':1 if fields is not None else 0,'messages':[],**({'fields':deepcopy(fields),'fingerprint':digest(fields)} if fields is not None else {})}
    def query(self,limit):
        return {'records':[{self.spec['keys'][0]:'SYNTH'}],'limit':limit,'possibly_truncated':False,'status':1,'messages':[],'folder':'TEST'}
    def write_once(self,action,keys,xml,operation_id):
        self.writes.append((self.resource,action,operation_id))
        key=(self.resource,json.dumps(keys,sort_keys=True));fields=self.records.setdefault(key,{})
        fields.update(projection(etree.fromstring(xml.encode())))
        if self.fail_after_write:raise TimeoutError('SYNTHETIC TIMEOUT AFTER SERVER COMMIT')
        return {'status':1,'messages':['SYNTHETIC SOAP RESULT'],'xml':None}

@pytest.fixture
def client(monkeypatch):
    if os.environ.get('RUN_STEP2_INTEGRATION')!='1':pytest.skip('Local DB integration disabled')
    monkeypatch.setattr(settings,'business_schema','sage_crud_test_'+uuid4().hex[:12])
    monkeypatch.setattr(settings,'approval_token',SecretStr('test-crud-operator'))
    db.migrate();assert service.migrate();assert not service.migrate()
    FakeGateway.records={};FakeGateway.writes=[];FakeGateway.fail_after_write=False;FakeGateway.read_count=0
    monkeypatch.setattr(service,'Gateway',FakeGateway);monkeypatch.setattr(api,'Gateway',FakeGateway)
    monkeypatch.setattr(service,'check_article_rules',lambda *a:{'validated':True,'rules_sha256':'synthetic'})
    # This substitution is only inside the isolated mock test, never application configuration.
    monkeypatch.setattr(service,'security',lambda *a,**k:{'ready':True,'blockers':[],'individual_approval_required':True,'folder':'TEST'})
    c=TestClient(app);c.headers.update({'X-Approval-Token':'test-crud-operator'})
    return c

def prepare(client,resource,action='create'):
    request=body(resource,action);response=client.post('/api/v1/sage/'+resource+'/prepare',json=request)
    assert response.status_code==200,response.text
    return response.json()

def approval(client,operation):
    response=client.post('/api/v1/sage/operations/'+operation['id']+'/approve',json={'digest':operation['digest'],'confirm':True,'actor':'SYNTHETIC TEST OPERATOR','reason':'SIMULATED authorization in isolated test DB only'})
    assert response.status_code==200,response.text
    return {'operation_id':operation['id'],'approval_token':response.json()['approval_token']}

def execute(client,resource,operation,token):
    suffix='/'+'/'.join(operation['record_keys'][key] for key in RESOURCES[resource]['keys']) if operation['action']=='update' else ''
    return getattr(client,'patch' if suffix else 'post')('/api/v1/sage/'+resource+suffix,json=token)

@pytest.mark.parametrize('resource',list(RESOURCES))
def test_complete_create_and_distinct_update_http_workflow(client,resource):
    if resource=='article-sites':
        article=prepare(client,'articles');assert execute(client,'articles',article,approval(client,article)).status_code==200
    operation=prepare(client,resource);assert operation['status']=='prepared'
    token=approval(client,operation)
    response=execute(client,resource,operation,token);assert response.status_code==200,response.text
    assert response.json()['status']==('unverified' if resource=='suppliers' else 'succeeded') and response.json()['after_record']['exists']
    if resource=='suppliers':
        # The legacy synthetic payload contains only a name. It must no longer
        # claim a verified supplier creation without activation and SQL evidence.
        assert not response.json()['result']['supplier_verification']['confirmed']
    assert execute(client,resource,operation,token).status_code in [403,409]
    changed=prepare(client,resource,'update')
    old=client.post('/api/v1/sage/operations/'+changed['id']+'/approve',json={'digest':operation['digest'],'confirm':True,'actor':'SYNTHETIC','reason':'Test wrong old digest'})
    assert old.status_code==409
    new_token=approval(client,changed)
    response=execute(client,resource,changed,new_token);assert response.status_code==200,response.text
    assert response.json()['status']=='succeeded'
    assert response.json()['before_record']!=response.json()['after_record']
    assert client.get('/api/v1/sage/'+resource+'/history').json()['operations']
    assert len([v for v in FakeGateway.writes if v[0]==resource])==2


def test_supplier_verification_exception_is_journalled_without_retry(client,monkeypatch):
    from app.services import supplier_readback
    def unavailable(*args,**kwargs):raise RuntimeError('synthetic_verification_failure')
    monkeypatch.setattr(supplier_readback,'verify',unavailable)
    operation=prepare(client,'suppliers')
    token=approval(client,operation)
    response=execute(client,'suppliers',operation,token)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='unverified'
    assert result['result']['supplier_verification']['errors']==['supplier_verification_unavailable']
    assert result['result']['retry_allowed'] is False
    assert execute(client,'suppliers',operation,token).status_code in (403,409)

@pytest.mark.parametrize('resource',list(RESOURCES))
def test_missing_approval_never_writes(client,resource):
    operation=prepare(client,resource)
    response=execute(client,resource,operation,{'operation_id':operation['id'],'approval_token':'forged'})
    assert response.status_code in [403,409]
    assert FakeGateway.writes==[]

def test_ambiguous_write_is_not_retried_but_read_back(client):
    operation=prepare(client,'articles');token=approval(client,operation);FakeGateway.fail_after_write=True
    before=FakeGateway.read_count
    response=execute(client,'articles',operation,token);assert response.status_code==200
    assert response.json()['status']=='ambiguous' and response.json()['after_record']['exists']
    assert FakeGateway.read_count>before and len(FakeGateway.writes)==1
    assert execute(client,'articles',operation,token).status_code in [403,409]
    response=client.post('/api/v1/sage/operations/'+operation['id']+'/reconcile')
    assert response.json()['write_retried'] is False and len(FakeGateway.writes)==1

def test_expired_approval_and_concurrent_record_change(client):
    operation=prepare(client,'articles');token=approval(client,operation)
    with db.connection() as conn:conn.execute("UPDATE soap_operation_approvals SET expires_at=now()-interval '1 second' WHERE operation_id=%s",(operation['id'],))
    assert execute(client,'articles',operation,token).status_code==403 and not FakeGateway.writes

def test_changed_record_cannot_use_old_modification_approval(client):
    create=prepare(client,'articles');execute(client,'articles',create,approval(client,create))
    change=prepare(client,'articles','update');token=approval(client,change)
    key=('articles',json.dumps(change['record_keys'],sort_keys=True));FakeGateway.records[key]['ITM0_1.DES1AXX']='CHANGED ELSEWHERE'
    assert execute(client,'articles',change,token).status_code==409
    assert len(FakeGateway.writes)==1

def test_operation_scope_cannot_be_changed(client):
    operation=prepare(client,'articles');token=approval(client,operation)
    assert client.post('/api/v1/sage/suppliers',json=token).status_code==403
    assert not FakeGateway.writes

def test_tampered_stored_xml_cannot_use_prior_approval(client):
    operation=prepare(client,'articles');token=approval(client,operation)
    with db.connection() as conn:conn.execute('UPDATE soap_operations SET object_xml=%s WHERE id=%s',('<PARAM>CHANGED</PARAM>',operation['id']))
    assert execute(client,'articles',operation,token).status_code==409
    assert not FakeGateway.writes

def test_event_history_immutable(client):
    operation=prepare(client,'articles')
    import psycopg
    with pytest.raises(psycopg.Error):
        with db.connection() as conn:conn.execute('DELETE FROM soap_operation_events WHERE operation_id=%s',(operation['id'],))

def test_default_security_blocks_all_six_write_routes(monkeypatch):
    monkeypatch.setattr(settings,'approval_token',SecretStr('test-crud-operator'));monkeypatch.setattr(settings,'sage_writes_enabled',False)
    c=TestClient(app);c.headers.update({'X-Approval-Token':'test-crud-operator'})
    for resource in RESOURCES:
        assert c.post('/api/v1/sage/'+resource,json={}).status_code==423
        suffix='/A/S' if resource=='article-sites' else '/A'
        assert c.patch('/api/v1/sage/'+resource+suffix,json={}).status_code==423

@pytest.mark.parametrize('resource',list(RESOURCES))
def test_key_changes_and_unapproved_update_fields_rejected(resource):
    from app.schemas.sage_crud import Preparation
    p=body(resource,'update');p['fields']=[{'group':RESOURCES[resource]['key_group'],'name':RESOURCES[resource]['keys'][0],'value':'OTHER'}]
    with pytest.raises(SageError):build_xml(metadata(resource),RESOURCES[resource],Preparation(**p))

def test_published_array_dimensions_and_table_rows():
    from app.schemas.sage_crud import Preparation
    p=body('suppliers');p['fields'][0]['value']=['ONLY ONE']
    with pytest.raises(SageError):build_xml(metadata('suppliers'),RESOURCES['suppliers'],Preparation(**p))
    desc=metadata('suppliers');g=etree.SubElement(desc.find('ADXDATA'),'GRP',NAM='ADDR',TYB='Table',DIM='5');etree.SubElement(g,'FLD',NAM='CITY',MOD='Input',TYP='Char',LEN='30')
    p=body('suppliers');p['fields'].append({'group':'ADDR','name':'CITY','value':'TEST CITY','row':1})
    xml=build_xml(desc,RESOURCES['suppliers'],Preparation(**p));assert '<TAB ID="ADDR">' in xml and '<LIN NUM="1">' in xml

def test_technical_audit_fields_cannot_be_supplied():
    from app.schemas.sage_crud import Preparation
    desc=metadata('articles');group=desc.find('./ADXDATA/GRP');etree.SubElement(group,'FLD',NAM='CREUSR',MOD='Input',TYP='Char',LEN='20')
    p=body('articles');p['fields'].append({'group':group.get('NAM'),'name':'CREUSR','value':'OTHER'})
    with pytest.raises(SageError,match='technical_audit_field_forbidden'):build_xml(desc,RESOURCES['articles'],Preparation(**p))

def test_description_timestamp_does_not_invalidate_binding():
    assert service.description_hash(metadata('articles'))==service.description_hash(metadata('articles'))

def envelope(method,xml='<PARAM/>',publication='WS_ARTICLE'):
    env=etree.Element('{'+SOAP_NS+'}Envelope');node=etree.SubElement(etree.SubElement(env,'{'+SOAP_NS+'}Body'),'{'+NS+'}'+method)
    ctx=etree.SubElement(node,'callContext');etree.SubElement(ctx,'poolAlias').text='POOL_AI_TEST'
    etree.SubElement(node,'publicName').text=publication;etree.SubElement(node,'objectXml').text=xml
    return env

def test_one_shot_transport_rejects_replay_and_payload_switch(monkeypatch):
    expected={'method':'save','publication':'WS_ARTICLE','pool':'POOL_AI_TEST','xml_hash':hashlib.sha256(b'<PARAM/>').hexdigest(),'keys':{'ITMREF':'X'}}
    t=OneShotTransport('https://sage:8443',expected);calls=[]
    monkeypatch.setattr(t,'_bounded',lambda *a,**k:calls.append(a) or 'SIMULATED')
    with pytest.raises(SageError):t.post_xml(t.base+SOAP_PATH,envelope('modify'),{})
    assert not calls
    assert t.post_xml(t.base+SOAP_PATH,envelope('save'),{})=='SIMULATED'
    with pytest.raises(SageError):t.post_xml(t.base+SOAP_PATH,envelope('save'),{})
    assert len(calls)==1

def test_modify_transport_checks_composite_keys(monkeypatch):
    expected={'method':'modify','publication':'WS_AR_SITE','pool':'POOL_AI_TEST','xml_hash':hashlib.sha256(b'<PARAM/>').hexdigest(),'keys':{'ITMREF':'A/B','STOFCY':'TST'}}
    t=OneShotTransport('https://sage:8443',expected);calls=[]
    monkeypatch.setattr(t,'_bounded',lambda *a,**k:calls.append(a))
    env=envelope('modify',publication='WS_AR_SITE');node=env.find('{'+SOAP_NS+'}Body')[0];keys=etree.SubElement(node,'objectKeys')
    for name,value in {'ITMREF':'WRONG','STOFCY':'TST'}.items():
        item=etree.SubElement(keys,'item');etree.SubElement(item,'key').text=name;etree.SubElement(item,'value').text=value
    with pytest.raises(SageError,match='one_shot_key_mismatch'):t.post_xml(t.base+SOAP_PATH,env,{})
    assert not calls

def test_slash_in_article_site_code_read_via_http(client):
    keys={'ITMREF':'A10/40','STOFCY':'201'}
    FakeGateway.records[('article-sites',json.dumps(keys,sort_keys=True))]={'ITF0_1.ITMREF':'A10/40','ITF0_1.STOFCY':'201'}
    response=client.get('/api/v1/sage/article-sites/A10%2F40/201')
    assert response.status_code==200 and response.json()['record']['keys']==keys

def test_expired_policy_and_missing_evidence_refuse_execution(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'sage_writes_enabled',True);monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443');monkeypatch.setattr(settings,'sage_soap_username',SecretStr('TEST_TECH'))
    policy={'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),'folder':'TEST','solution':'V12','pool':settings.sage_soap_pool,'base_url':settings.sage_soap_base_url,'credentials_rotated':True,'dedicated_account_verified':True,'http_login_sha256':hashlib.sha256(b'TEST_TECH').hexdigest()}
    file=tmp_path/'policy.json';file.write_text(json.dumps(policy));monkeypatch.setattr(settings,'sage_security_policy_file',str(file))
    assert not service.security('articles','create',metadata('articles'))['ready']

def test_delete_route_absent_and_anonymous_write_forbidden(client):
    assert client.delete('/api/v1/sage/suppliers/SYNTH_BPS').status_code==405
    assert TestClient(app).post('/api/v1/sage/articles',json={}).status_code==403

def test_invalid_security_receipt_cannot_enable_http_admin(monkeypatch):
    monkeypatch.setattr(settings,'sage_writes_enabled',True);monkeypatch.setattr(settings,'sage_security_policy_file','')
    monkeypatch.setattr(settings,'sage_soap_base_url','http://192.168.9.200:8124');monkeypatch.setattr(settings,'sage_soap_username',SecretStr('admin'))
    state=service.security('articles','create',metadata('articles'))
    assert not state['ready'] and 'VERIFIED_HTTPS_REQUIRED' in state['blockers'] and 'DEDICATED_TECHNICAL_ACCOUNT_REQUIRED' in state['blockers']

def test_security_evidence_binds_identity_publication_scope_and_file_hashes(monkeypatch,tmp_path):
    # This test isolates policy signatures; actual TLS/CRL verification has its
    # own real MemoryBIO and negative-bundle tests.
    monkeypatch.setattr(service,'local_tls_readiness',lambda config:{'local_material_ready':True,'peer_verified':False})
    monkeypatch.setattr(settings,'sage_writes_enabled',True);monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443');monkeypatch.setattr(settings,'sage_soap_username',SecretStr('TEST_TECH'))
    document=tmp_path/'review.txt';document.write_text('SYNTHETIC ADMIN REVIEW - NOT FOR DEPLOYMENT');evidence={'path':str(document),'sha256':hashlib.sha256(document.read_bytes()).hexdigest()}
    desc=metadata('articles')
    policy={'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'folder':'TEST','solution':'V12','pool':settings.sage_soap_pool,'base_url':settings.sage_soap_base_url,
        'credentials_rotated':True,'dedicated_account_verified':True,'http_login_sha256':hashlib.sha256(b'TEST_TECH').hexdigest(),'x3_login_sha256':hashlib.sha256(b'TEST_TECH').hexdigest(),
        'permissions':{'articles':{'create':{'rights_verified':True,'business_rules_reviewed':True,'manual_keys_preserved':True,'rights_evidence':evidence,'business_rules_evidence':evidence,'description_sha256':service.description_hash(desc)}}}}
    file=tmp_path/'review.json';file.write_text(json.dumps(policy));monkeypatch.setattr(settings,'sage_security_policy_file',str(file))
    assert service.security('articles','create',desc)['ready']
    assert not service.security('articles','update',desc)['ready']
    wrong=deepcopy(desc);wrong.set('USER','ADMIN');assert not service.security('articles','create',wrong)['ready']
    document.write_text('MODIFIED EVIDENCE');assert not service.security('articles','create',desc)['ready']
    policy['credentials_rotated']='false';file.write_text(json.dumps(policy));assert not service.security()['ready']

@pytest.mark.parametrize('resource',list(RESOURCES))
def test_gateway_rejects_actual_description_outside_test(monkeypatch,resource):
    from app.services.sage_gateway import Gateway
    desc=metadata(resource);desc.set('FOL','PRODUCTION')
    gateway=Gateway(resource);monkeypatch.setattr(gateway.reader,'_invoke',lambda *a,**k:desc)
    with pytest.raises(SageError,match='target_not_test'):gateway.describe()
