"""Full supplier chat approval pipeline with fake Sage/SQL and isolated PG."""
import json
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
from app.services import conversation_chat as chat,chat_supplier_actions as actions,sage_crud as crud,chat_tools
from app.services.sage_gateway import RESOURCES,projection,digest
from app.services.sage_soap import parse_xml
from test_conversation_chat import fixture,create
from test_supplier_ob_preparation import profile

class FakeSupplier:
    records={};writes=[]
    def __init__(self,resource):assert resource=='suppliers';self.spec=RESOURCES[resource]
    def describe(self):return parse_xml((Path(__file__).resolve().parents[2]/'runtime/crud-WS_FOURNIS-description.xml').read_bytes())
    def read(self,keys,describe=True):
        fields=self.records.get(keys['BPSNUM'])
        return {'exists':fields is not None,'fields':deepcopy(fields or {}),'fingerprint':digest(fields or {})}
    def write_once(self,action,keys,xml,identifier):
        assert action=='create' and keys['BPSNUM'] not in self.records
        self.writes.append(keys['BPSNUM']);self.records[keys['BPSNUM']]=projection(parse_xml(xml.encode()))
        return {'status':1,'messages':['CONTROLLED TEST ONLY: no Sage request']}


@pytest.fixture
def workflow(fixture,monkeypatch):
    client,queue=fixture;FakeSupplier.records={};FakeSupplier.writes=[];actions.PERMITS.clear()
    monkeypatch.setattr(actions,'Gateway',FakeSupplier);monkeypatch.setattr(crud,'Gateway',FakeSupplier)
    monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':True,'blockers':[],'folder':'TEST'})
    def sql(calls):
        out={}
        for c in calls:
            rows=[];tool=c['tool']
            if tool=='get_supplier_preparation_profile':out[c['id']]=profile();continue
            if tool=='get_supplier_record':
                code=c['args']['Supplier'];f=FakeSupplier.records.get(code)
                if f:
                    row={'folder':'TEST','BPSNUM_0':code,'BPRNUM_0':code}
                    from app.services.supplier_readback import MAPPING
                    for path,columns in MAPPING.items():
                        if path not in f:continue
                        value=f[path][0] if isinstance(f[path],list) else f[path]
                        for column in columns:row[column]=int(value) if column.endswith('_active') else value
                    rows=[row]
            out[c['id']]={'ok':True,'rows':rows,'source':'SQL TEST','folder':'TEST','controlled_fixture':True}
        return out
    monkeypatch.setattr(chat_tools,'run',sql)
    fields={'nom':'SYNTH SUPPLIER','code':'F0012','ice':'001850814000094','identifiant_fiscal':'20734927','rc':'10909',
            'pays':'MA','devise':'MAD','categorie_fournisseur':'FR','statut':'actif','intitule_court':'SYNTH'}
    text='Créer un fournisseur SYNTH SUPPLIER, code fournisseur F0012, ICE 001850814000094, IF 20734927, RC 10909, pays MA, devise MAD, catégorie fournisseur FR, statut actif, intitulé court SYNTH'
    session=create(client);queue.append({'intent':'new','fournisseurs':[fields]})
    response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':text,'revision':session['revision']});assert response.status_code==200,response.text
    session=response.json();p=session['state']['partners'][0]
    response=client.post('/api/v1/chat/conversations/'+session['id']+'/partners/'+p['id']+'/review',json={'revision':session['revision'],'confirm':True});assert response.status_code==200,response.text
    return client,queue,response.json()


def call(client,s,step,confirm=False):
    p=s['state']['partners'][0]
    return client.post('/api/v1/chat/conversations/'+s['id']+'/partners/'+p['id']+'/'+step,json={'revision':s['revision'],'confirm':confirm})


def test_supplier_uses_same_staged_approval_and_readback_without_token_in_chat(workflow):
    c,q,s=workflow
    r=call(c,s,'prepare');assert r.status_code==200,r.text;s=r.json()
    assert s['state']['partners'][0]['operation']['status']=='prepared' and not FakeSupplier.writes
    assert call(c,s,'execute',True).status_code==403
    r=call(c,s,'approve',True);assert r.status_code==200,r.text;s=r.json()
    token=actions.PERMITS[s['state']['partners'][0]['id']]['token']
    assert token not in json.dumps(s) and not FakeSupplier.writes
    r=call(c,s,'execute',True);assert r.status_code==200,r.text;s=r.json()
    p=s['state']['partners'][0]
    assert p['operation']['status']=='succeeded'
    assert p['operation']['result']['supplier_verification']['created_and_active']
    assert 'F0012' in s['messages'][-1]['content'] and 'créé et activé' in s['messages'][-1]['content']
    assert FakeSupplier.writes==['F0012'] and token not in json.dumps(s)
    assert call(c,s,'execute',True).status_code==409 and FakeSupplier.writes==['F0012']


@pytest.mark.parametrize('step',['prepare','approve','execute'])
def test_supplier_security_423_before_any_gateway_or_save(workflow,monkeypatch,step):
    c,q,s=workflow;monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':False,'blockers':['CA_CRL_MATERIAL_REQUIRED']})
    def forbidden(*args,**kwargs):raise AssertionError('No gateway behind closed security gate')
    monkeypatch.setattr(actions,'Gateway',forbidden)
    assert call(c,s,step,True).status_code==423 and FakeSupplier.writes==[]


def test_supplier_requires_explicit_approval_and_rejects_expired_permit(workflow):
    c,q,s=workflow;s=call(c,s,'prepare').json()
    assert call(c,s,'approve',False).status_code==409
    s=call(c,s,'approve',True).json();actions.PERMITS[s['state']['partners'][0]['id']]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert call(c,s,'execute',True).status_code==403 and not FakeSupplier.writes


def test_supplier_change_before_execution_invalidates_preparation(workflow):
    c,q,s=workflow;s=call(c,s,'prepare').json();s=call(c,s,'approve',True).json()
    q.append({'intent':'update','fournisseurs':[{'index':1,'nom':'SYNTH MODIFIED'}]})
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'nom SYNTH MODIFIED','revision':s['revision']});assert r.status_code==200,r.text;s=r.json()
    assert s['state']['partners'][0]['operation']['status']=='invalidated'
    assert call(c,s,'execute',True).status_code in (403,409) and not FakeSupplier.writes


def test_supplier_route_requires_csrf(workflow):
    c,q,s=workflow;c.headers.pop('X-Chat-CSRF')
    assert call(c,s,'prepare').status_code==403 and not FakeSupplier.writes


def test_duplicate_appearing_after_approval_blocks_execution(workflow,monkeypatch):
    c,q,s=workflow;s=call(c,s,'prepare').json();s=call(c,s,'approve',True).json()
    original=chat_tools.run
    def collision(calls):
        result=original(calls)
        for call_ in calls:
            if call_['tool']=='check_supplier_fiscal_duplicates':result[call_['id']]['rows']=[{'folder':'TEST','BPRNUM_0':'F0099','BPSNUM_0':'F0099','BPRNAM_0':'OTHER','BPSNAM_0':'OTHER','XICE_0':'001850814000094'}]
        return result
    monkeypatch.setattr(chat_tools,'run',collision)
    assert call(c,s,'execute',True).status_code==409 and not FakeSupplier.writes


def test_supplier_ob_target_is_read_only(workflow):
    c,q,s=workflow;q.append({'intent':'update','fournisseurs':[{'index':1,'dossier_cible':'OB'}]})
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'Dossier OB','revision':s['revision']});assert r.status_code==200,r.text
    assert call(c,r.json(),'prepare').status_code==403 and not FakeSupplier.writes


def test_supplier_conversation_cannot_be_used_by_another_owner(workflow):
    from fastapi.testclient import TestClient
    from app.main import app
    c,q,s=workflow;other=TestClient(app);other.headers['Origin']='http://testserver'
    response=other.post('/api/v1/chat/session');other.headers['X-Chat-CSRF']=response.json()['csrf']
    assert call(other,s,'prepare').status_code==404 and not FakeSupplier.writes


def test_publication_specific_security_failure_never_offers_approval(workflow,monkeypatch):
    c,q,s=workflow
    monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':len(a)<3,'blockers':[] if len(a)<3 else ['SCOPED_X3_RIGHTS_AND_RULES_EVIDENCE_REQUIRED'],'folder':'TEST'})
    r=call(c,s,'prepare');assert r.status_code==200,r.text;s=r.json()
    assert s['state']['partners'][0]['operation']['status']=='blocked'
    assert call(c,s,'approve',True).status_code==409 and not FakeSupplier.writes
