"""No Sage writes or live inference: copied greeting and noisy UPDATE regression."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/tests'))
import pytest
from test_conversation_chat import fixture,create
from app.services import modification_dialogue as modification,conversation_guardrails as guards,supplier_sql
from app.services.sage_crud import CrudError

WELCOME='Bonjour ! Décrivez l’article ou le fournisseur souhaité. Je préparerai sa fiche pour votre confirmation. Aucune création ne sera lancée sans votre approbation.'

@pytest.mark.parametrize('ending',['','&#x20;','  '])
def test_echo_is_not_a_creation_or_model_request(fixture,ending):
    c,q=fixture;s=create(c)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':WELCOME+ending,'revision':s['revision']})
    assert r.status_code==200,r.text
    s=r.json()
    assert not s['state'].get('partners') and not s['state'].get('articles') and not q
    assert 'recopié' in s['messages'][-1]['content']
    assert not s['messages'][-1].get('payload',{}).get('supplier_snapshots')

@pytest.mark.parametrize('text',['je veux modifer mon founiseur','je veux modifier mon fournisseur','modifie mon founisseur'])
def test_noisy_modification_asks_for_existing_record(text,monkeypatch):
    monkeypatch.setattr(modification.settings,'sage_modification_enabled',True)
    state={'articles':[],'partners':[{'id':'existing','kind':'supplier','nom':'votre confirmation','operation':{'status':'succeeded','record_keys':{'BPSNUM':'F10034'}}}]}
    out=modification.turn(None,None,text,state)
    assert out['state']['modification_pending_target']['resource']=='supplier'
    assert 'code exact' in out['reply'] and 'à modifier' in out['reply']
    assert out['state']['partners']==state['partners']

@pytest.mark.parametrize('name',['votre confirmation','VOTRE APPROBATION','suivant dans le système'])
def test_template_identity_cannot_be_prepared_or_approved(name):
    with pytest.raises(CrudError,match='raison sociale exacte'):supplier_sql.parameters({'nom':name})

def test_greeting_guard_does_not_intercept_real_name():
    assert not guards.welcome_echo('Bonjour, crée le fournisseur CONFIRMATION INDUSTRIES')
    assert not guards.invalid_supplier_name('CONFIRMATION INDUSTRIES')

def test_update_reply_does_not_repeat_previous_creation_table(fixture,monkeypatch):
    from app.services import business_store as db
    from psycopg.types.json import Jsonb
    c,q=fixture;monkeypatch.setattr(modification.settings,'sage_modification_enabled',True)
    s=create(c);state=s['state'];state['partners']=[{'id':'existing','kind':'supplier','nom':'votre confirmation','operation':{'status':'succeeded','record_keys':{'BPSNUM':'F10034'}}}]
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(state),s['id']))
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'je veux modifer mon founiseur','revision':s['revision']})
    assert r.status_code==200,r.text
    s=r.json();assert 'code exact' in s['messages'][-1]['content']
    assert not s['messages'][-1].get('payload',{}).get('supplier_snapshots')
    assert s['state']['partners']==state['partners'] and not q
