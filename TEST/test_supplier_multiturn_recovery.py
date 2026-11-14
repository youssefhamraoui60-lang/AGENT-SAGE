"""Conversation continuity: simulated inference, isolated PostgreSQL, no Sage writes."""
import sys,copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
import pytest
from app.services import supplier_dialogue as dialogue,supplier_multiturn,ai_provider,chat_partners
from test_conversation_chat import fixture,create

TURNS=['Bonjour','Je veux crrer un fourniseur','Un nevelle fourniseur',"Il s'appelle ATLAS TEST et il est à Rabat",'Non, je me suis trompé, son nom est ATLAS BUREAU TEST',"C'est une SARL AU, je ne connais pas encore son ICE"]

def replay():
    state={'articles':[],'partners':[]};history=[]
    for text in TURNS[1:]:
        result=dialogue.handle(text,state,history)
        assert result is not None,text
        state=result['state'];history.append({'role':'user','content':text})
    return state

def test_exact_six_turns_without_inference():
    state=replay();p=state['partners'][0]
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat'
    assert p['forme_juridique']=='SARL AU' and not p.get('ice')
    assert p['field_states']['ice']['status']=='unknown' and not p['approved']

@pytest.mark.parametrize('unknown',["je ne connais pas encore son ICE","je connais pas son ICE","je n'ai pas encore son ICE"])
def test_unknown_is_not_an_error_or_permission(unknown):
    s=replay();s['partners'][0]['ice']='001234567890123'
    out=dialogue.handle(unknown,s)['state']['partners'][0]
    assert out['ice']=='001234567890123' and not out['approved']

def test_recover_missing_draft_from_actual_user_history():
    result=dialogue.handle(TURNS[-1],{'partners':[],'articles':[]},[{'role':'user','content':t} for t in TURNS[:-1]])
    p=result['state']['partners'][0]
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'

def test_confirmed_value_requires_reread_when_new_fact_conflicts():
    s=replay();p=s['partners'][0]
    p['field_states']['ville']['status']='confirmed'
    out=dialogue.handle('Il est à Tanger',s)['state']
    assert out['partners'][0]['ville']=='Rabat' and out['pending_correction']['value']=='Tanger'

def test_natural_correction_is_persisted_as_anonymized_candidate(fixture):
    from app.services import learning_signals,business_store as db
    from uuid import UUID
    c,_=fixture;conv=create(c)
    owner=UUID(c.get('/api/v1/chat/session').json()['user']['id'])
    before=dialogue.handle(TURNS[3],dialogue.handle(TURNS[1],{'articles':[],'partners':[]})['state'])['state']
    after=dialogue.handle(TURNS[4],before)['state']
    learning_signals.record(owner,UUID(conv['id']),before,after,TURNS[4])
    with db.connection() as conn:
        rows=conn.execute('SELECT lesson FROM learning_corrections WHERE owner_id=%s',(owner,)).fetchall()
    assert rows
    assert 'ATLAS' not in json.dumps(rows) and not any(r['lesson'].get('training_performed') for r in rows)

@pytest.mark.parametrize('value',['inconnu','non renseigné','unknown',''])
def test_optional_fiscal_normalization_keeps_zeroes(value):
    content=json.dumps({'fournisseurs':[{'ice':value,'rc':'00123','nom':'inconnu'}]})
    p=json.loads(ai_provider.normalize_optional_fiscal(content))['fournisseurs'][0]
    assert p['ice'] is None and p['rc']=='00123' and p['nom']=='inconnu'

def test_orphan_model_patch_asks_instead_of_crashing():
    from app.services.chat_model import Delta
    s=chat_partners.merge({'partners':[],'articles':[]},Delta(intent='update',fournisseurs=[{'index':1,'forme_juridique':'SARL AU'}]),TURNS[-1])
    assert not s['partners'] and s.get('unapplied_partner_patch')

def test_exact_conversation_in_fastapi_preserves_pg_draft(fixture,monkeypatch):
    c,q=fixture
    from app.services import supplier_chat_flow
    def prepare(state):
        assert not state['partners'][0]['approved']
        return 'Fiche conservée. Vérifiez les informations avant confirmation.'
    monkeypatch.setattr(supplier_chat_flow,'prepare_state',prepare)
    s=create(c)
    # Greeting is already covered by provider tests; business turns must never call Qwen.
    for text in TURNS[1:]:
        r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
        assert r.status_code==200,r.text
        s=r.json();assert not s['state'].get('_pending')
        assert 'extraction' not in s['messages'][-1]['content'].lower()
    saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
    p=saved['state']['partners'][0]
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'
    assert not p.get('ice') and not p['approved'] and not q
