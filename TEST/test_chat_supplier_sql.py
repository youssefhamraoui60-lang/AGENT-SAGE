"""Chat/API integration with a fake SQL transport; no Sage writes."""
import sys,json,subprocess
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.chat import router
from app.services import chat_supplier_sql_actions as actions,supplier_sql as sql,conversation_chat as chat,chat_auth as auth,chat_partners
from app.services.sage_crud import CrudError

def supplier():
    raw=json.loads((Path(__file__).parent/'supplier.example.json').read_text(encoding='utf-8'))
    raw['Telephone']='0612345678'  # A valid-format synthetic Moroccan contact.
    return {'id':str(uuid4()),'kind':'supplier','reviewed':True,'dossier_cible':'TEST',
            **{field:raw[key] for key,field in sql.MAPPING.items()}}

def result(values,code='F104'):
    row={col:values[key] for key,col in sql.READBACK.items()}
    row.update({column:values.get(key,'') for key,column in [('Adresse2','ADRESSE2'),('Adresse3','ADRESSE3')]})
    row.update(CODE_FOURNISSEUR=code,partner_active=2,supplier_active=2)
    return {'ok':True,'executed':True,'folder':'TEST','rows':[row]}

@pytest.fixture
def workflow(monkeypatch):
    state={'partners':[supplier()]};calls=[];owner=uuid4();conversation=uuid4()
    @contextmanager
    def connection():yield object()
    monkeypatch.setattr(actions.db,'connection',connection)
    def get_row(conn,who,identifier,lock=False):
        if who!=owner or identifier!=conversation:raise CrudError('conversation_not_found',404)
        return {'revision':1,'state':deepcopy(state)}
    def save(conn,who,identifier,value):state.clear();state.update(deepcopy(value))
    monkeypatch.setattr(chat,'get_row',get_row);monkeypatch.setattr(chat,'save_conversation_context',save)
    monkeypatch.setattr(chat,'append',lambda *a,**k:None)
    monkeypatch.setattr(chat,'read',lambda *a:{'revision':1,'state':deepcopy(state)})
    def run(values,execute=False):
        calls.append(execute)
        return result(values) if execute else {'ok':True,'rows':[{'RESULTAT':'VALIDATED_NO_INSERT','CODE_PROPOSE_NON_RESERVE':'F104'}]}
    monkeypatch.setattr(sql,'run',run)
    app=FastAPI();app.include_router(router);app.dependency_overrides[auth.operator]=lambda:{'owner_id':owner}
    actions.PERMITS.clear()
    def call(step,confirm=False,revision=1,**options):
        return TestClient(app).post(f'/api/v1/chat/conversations/{conversation}/partners/{state["partners"][0]["id"]}/{step}',
                                   json={'revision':revision,'confirm':confirm,**options})
    return state,calls,call

def test_existing_chat_route_prepares_approves_and_executes_sql_once(workflow):
    state,calls,call=workflow
    assert call('prepare').status_code==200 and calls==[False]
    op=state['partners'][0]['operation'];assert op['transport']=='direct_sql' and op['parameters']['Nom']=='Télfix'
    assert call('execute',True).status_code==403 and calls==[False]
    assert call('approve',False).status_code==409
    assert call('approve',True).status_code==200 and calls==[False]
    response=call('execute',True);assert response.status_code==200,response.text
    op=response.json()['state']['partners'][0]['operation']
    assert op['status']=='succeeded' and op['record_keys']=={'BPSNUM':'F104'}
    assert call('execute',True).status_code==409 and calls==[False,True]

@pytest.mark.parametrize('change',['parameters','query','expired','owner','missing_confirmation'])
def test_changed_or_invalid_approval_never_executes(workflow,monkeypatch,change):
    state,calls,call=workflow;call('prepare');call('approve',True);p=state['partners'][0]
    if change=='parameters':p['nom']='Changed'
    if change=='query':monkeypatch.setattr(sql,'query_digest',lambda:'changed')
    if change=='expired':actions.PERMITS[p['id']]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    if change=='owner':actions.PERMITS[p['id']]['owner']='other'
    assert call('execute',change!='missing_confirmation').status_code==403 and calls==[False]

def test_ob_and_stale_revision_are_rejected(workflow):
    state,calls,call=workflow
    assert call('prepare',revision=2).status_code==409
    state['partners'][0]['dossier_cible']='OB'
    assert call('prepare').status_code==403 and calls==[]

def test_sql_error_is_terminal_and_cannot_retry(workflow,monkeypatch):
    state,calls,call=workflow;call('prepare');call('approve',True)
    def fail(*a,**k):calls.append(True);return {'ok':False,'code':'sql_result_requires_readback'}
    monkeypatch.setattr(sql,'run',fail)
    assert call('execute',True).json()['state']['partners'][0]['operation']['status']=='ambiguous'
    assert call('execute',True).status_code==409 and calls==[False,True]

def test_missing_values_and_truncation_are_rejected():
    p=supplier();p.pop('ice')
    assert sql.parameters(p)['ICE']==''  # Explicitly optional since supplier-without-ICE support.
    p=supplier();p['telephone']='0'*31
    with pytest.raises(CrudError):sql.parameters(p)

def test_readback_requires_all_values_and_one_test_row():
    values=sql.parameters(supplier());body=result(values)
    assert sql.verify(values,body)
    body['rows'][0]['ICE']='wrong';assert sql.verify(values,body) is None
    body=result(values);body['folder']='OB';assert sql.verify(values,body) is None
    body=result(values);body['rows']*=2;assert sql.verify(values,body) is None

def test_literal_chat_accepts_new_sql_parameters():
    text='Créer un fournisseur Télfix, ICE 001850814901094, IF 20734924, RC 10903, adresse AYNE HARODA, ville CASABLANCA, téléphone 06965654689, paiement EFF60, type montant TTC, date régularité 2026-02-27, pays MA, devise MAD, intitulé court TELFIX, catégorie FR, code comptable STD, regime taxe MAR'
    delta=chat_partners.literal_extract(text,{})
    assert delta is not None
    p=delta.fournisseurs[0];assert p.ville=='CASABLANCA' and p.type_montant=='TTC' and p.conditions_paiement=='EFF60'
    state=chat_partners.merge({'partners':[]},delta,text)
    assert state['partners'][0]['type_montant']=='TTC'

def test_worker_timeout_after_send_is_ambiguous(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(sql.settings,'sage_supplier_sql_connection_string',SecretStr('configured-for-mock-only'))
    def timeout(*a,**k):raise subprocess.TimeoutExpired('powershell.exe',75)
    monkeypatch.setattr(sql.subprocess,'run',timeout)
    assert sql.run(sql.parameters(supplier()),True)['code']=='sql_result_requires_readback'

def test_permission_status_exposes_missing_test_insert_without_grants(monkeypatch):
    from types import SimpleNamespace
    sql._PERMISSION_CACHE.clear()
    body={'ok':True,'folder':'TEST','ready':False,'permissions':[
        {'object':'TEST.BPARTNER','requires_insert':1,'can_select':1,'can_insert':0},
        {'object':'TEST.BPSUPPLIER','requires_insert':1,'can_select':1,'can_insert':1},
        {'object':'TEST.BPADDRESS','requires_insert':1,'can_select':1,'can_insert':0}]}
    def audit(*args,**kwargs):
        assert str(args[0][-1]).endswith('Check-SupplierSql.ps1')
        return SimpleNamespace(stdout=json.dumps(body))
    monkeypatch.setattr(sql.subprocess,'run',audit)
    status=sql.security()
    assert status['ready'] is False and 'TEST.BPARTNER' in status['blockers'][0] and 'TEST.BPADDRESS' in status['blockers'][0]
    sql._PERMISSION_CACHE.clear()

def test_rejected_preview_is_visible_in_chat_and_cannot_be_approved(workflow,monkeypatch):
    state,calls,call=workflow
    def rejected(values,execute=False):
        assert execute is False
        calls.append(False)
        return {'ok':False,'code':'sql_validation_rejected','sql_error_number':50109,
            'diagnostics':[{'proposed_code':'F10016','duplicate_code':'F10014'}]}
    monkeypatch.setattr(sql,'run',rejected)
    response=call('prepare');assert response.status_code==200,response.text
    op=response.json()['state']['partners'][0]['operation']
    assert op['status']=='blocked' and op['parameters']['Nom']=='Télfix'
    assert op['proposed_code']=='F10016' and 'F10014' in op['validation']['message']
    assert call('approve',True).status_code==423 and call('execute',True).status_code==423
    assert calls==[False]

@pytest.mark.parametrize('right',['SELECT','EXECUTE'])
def test_missing_additional_right_is_reported(monkeypatch,right):
    from types import SimpleNamespace
    row={'object':'sys.sp_executesql' if right=='EXECUTE' else 'OB.BPARTNER',
         'requires_select':int(right=='SELECT'),'can_select':0,
         'requires_execute':int(right=='EXECUTE'),'can_execute':0}
    body={'ok':True,'ready':False,'folder':'TEST','permissions':[row]}
    monkeypatch.setattr(sql.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=json.dumps(body)))
    sql._PERMISSION_CACHE.clear()
    status=sql.security(force=True)
    assert status['ready'] is False and right in status['blockers'][0]
    sql._PERMISSION_CACHE.clear()

def test_backend_sends_utf8_json_without_bom(monkeypatch):
    from types import SimpleNamespace
    def run(*args,**kwargs):
        encoded=kwargs['input'].encode(kwargs['encoding'])
        assert not encoded.startswith(b'\xef\xbb\xbf')
        assert json.loads(encoded)['execute'] is False
        return SimpleNamespace(stdout=json.dumps({'ok':True,'executed':False,'rows':[]}))
    monkeypatch.setattr(sql.subprocess,'run',run)
    assert sql.run(sql.parameters(supplier()))['ok']
