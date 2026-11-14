"""Private JSON context and DeepSeek-first multi-operation session regressions."""
import json,sys
from pathlib import Path
from uuid import uuid4
import pytest,jsonschema
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import conversation_state as journal,conversation_tools as engine
from app.core.config import settings
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create


def test_json_projection_preserves_archives_and_excludes_execution_material():
    old={'id':'one','kind':'supplier','nom':'Ancien','ice':'001234567890123','operation':{'status':'cancelled','permit':'SECRET','object_xml':'SECRET'}}
    current={'id':'two','kind':'supplier','nom':'Nouveau','operation':{'status':'prepared','password':'SECRET'}}
    state={'supplier_target':'OB','supplier_archives':[{'partners':[old]}],'partners':[current]}
    first=journal.synchronize(state,'session')
    second=journal.synchronize(state,'session')
    assert first==second and first['context_revision']==1
    assert {op['id'] for op in first['operations']}=={'one','two'}
    assert all(op['folder']=='OB' for op in first['operations'])
    assert 'SECRET' not in json.dumps(first)
    assert first['authority']=='context_only_no_execution_permission'
    jsonschema.validate(first,json.loads((ROOT/'config/conversation-state.schema.json').read_text()))
    current['ice']='000000000000001';journal.synchronize(state,'session')
    assert state['operation_context']['context_revision']==2


def test_cancel_specific_article_keeps_other_drafts():
    state={'articles':[{'id':'one','code_article':'NEG_A','designation':'A'},{'id':'two','code_article':'NEG_B','designation':'B'}]}
    result=engine.dispatch('cancel_request',engine.Cancel(code='NEG_A'),state,'annule NEG_A')
    assert result['cancelled_drafts']==1
    assert state['articles'][0]['operation']['status']=='cancelled'
    assert not state['articles'][1].get('operation')


def test_deepseek_primary_keeps_parameters_cancel_then_multiple_modifications_and_export(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','SESSION FOURNISSEUR'),fact('adresse','HAY RAH R56')])),say('Fiche conservée pour relecture.')])
    s=send(c,create(c),'Créer un fournisseur SESSION FOURNISSEUR, adresse HAY RAH R56')
    supplier_id=s['state']['partners'][0]['id']
    assert requests and 'business_state' in json.dumps(requests[0]['body'])
    assert s['state']['operation_context']['operations'][0]['parameters']['adresse']=='HAY RAH R56'
    q.extend([native(call('select_for_modification',resource='supplier',code='F994')),
              native(call('prepare_modification',resource='supplier',code='F994',changes=[{'field':'city','value':'Agadir','evidence':'Agadir'},{'field':'phone','value':'0612345678','evidence':'0612345678'}])),
              say('Création annulée et modifications préparées pour vérification.')])
    s=send(c,s,'annule cette création puis modifie le fournisseur F994 : sa ville est Agadir et son téléphone est 0612345678')
    assert s['state']['partners'][0]['id']==supplier_id
    assert s['state']['partners'][0]['operation']['status']=='cancelled'
    modification=s['state']['modification_drafts'][-1]
    assert modification['changes']=={'city':'Agadir','phone':'0612345678'}
    assert modification['operation']['status']=='prepared'
    response=c.get('/api/v1/chat/conversations/'+s['id']+'/operation-state.json')
    assert response.status_code==200
    assert 'attachment' in response.headers['content-disposition'] and response.headers['cache-control']=='no-store'
    exported=response.json()
    assert exported['objective']['intent']=='modify'
    assert next(op for op in exported['operations'] if op['id']==supplier_id)['status']=='cancelled'
    assert next(op for op in exported['operations'] if op['action']=='modify')['changes']==modification['changes']
    assert len(exported['events'])>=3
    assert exported==s['state']['operation_context']
    jsonschema.validate(exported,json.loads((ROOT/'config/conversation-state.schema.json').read_text()))
    assert all(not attempt['execute'] for attempt in attempts)
    assert c.get('/api/v1/chat/conversations/'+str(uuid4())+'/operation-state.json').status_code==404


def test_other_account_cannot_export_context(native_chat):
    from fastapi.testclient import TestClient
    from app.main import app
    c,*_=native_chat;s=create(c)
    with TestClient(app) as other:
        other.headers['Origin']='http://testserver'
        response=other.post('/api/v1/chat/auth/register',json={'email':uuid4().hex+'@example.test','display_name':'Other','password':'Context-isolated-password-2026!'})
        assert response.status_code==201
        assert other.get('/api/v1/chat/conversations/'+s['id']+'/operation-state.json').status_code==404


def test_primary_article_correction_goes_through_deepseek_and_keeps_all_fields(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','ARTICLE ALPHA')])),say('Quel est le code de catégorie à retenir ?')])
    s=send(c,create(c),'Créer un article ARTICLE ALPHA')
    identifier=s['state']['articles'][0]['id'];before=len(requests)
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('designation','ARTICLE BETA'),fact('unite','UN')])),say('Nom et unité conservés pour relecture.')])
    s=send(c,s,'Corrige la désignation : ARTICLE BETA, unité UN')
    assert len(requests)>before and s['state']['tool_orchestration']['provider']=='deepseek'
    a=s['state']['articles'][0]
    assert a['id']==identifier and a['designation']=='ARTICLE BETA' and a['unite']=='UN'
    assert all(not attempt['execute'] for attempt in attempts)


def test_primary_outage_retains_context_and_applies_literal_supplier_update(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','ROBUSTE'),fact('adresse','ADRESSE A1')])),say('Fiche conservée.')])
    s=send(c,create(c),'Créer un fournisseur ROBUSTE, adresse ADRESSE A1')
    identifier=s['state']['partners'][0]['id'];fault.update(cloud=True,local=True)
    s=send(c,s,'le addrise est ADRESSE B2')
    assert len(s['state']['partners'])==1
    p=s['state']['partners'][0]
    assert p['id']==identifier and p['nom']=='ROBUSTE' and p['adresse']=='ADRESSE B2'
    projected=next(op for op in s['state']['operation_context']['operations'] if op['id']==identifier)
    assert projected['parameters']['adresse']=='ADRESSE B2'
    assert not p.get('approved') and all(not attempt['execute'] for attempt in attempts)


@pytest.mark.parametrize('enabled,action',[(True,'activate'),(False,'deactivate')])
def test_supplier_status_change_is_a_distinct_operation(enabled,action):
    context=journal.project({'modification_drafts':[{'id':'status-change','resource':'supplier','code':'F007','changes':{'enabled':enabled},'operation':{'status':'prepared'}}]})
    assert context['operations'][0]['action']==action
