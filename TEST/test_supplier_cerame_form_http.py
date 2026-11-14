from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from test_supplier_cerame_form import MESSAGE,FOLLOWUP
from app.services import supplier_sql,conversation_chat as chat

def test_original_message_and_short_followup_never_request_creation_intent(setup,monkeypatch):
    c,s,owner=setup
    async def forbidden(*a,**kw):raise AssertionError('No model needed for labelled fiscal values')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=send(c,s,MESSAGE);p=s['state']['partners'][0];identifier=p['id']
    assert p['nom']=='Super Cerame' and p['ice']=='000000505000042'
    assert p['identifiant_fiscal']=='01067182'
    s=send(c,s,FOLLOWUP);p=s['state']['partners'][0]
    assert p['id']==identifier and p['nom']=='Cerame' and len(s['state']['partners'])==1
    assert not p.get('approved') and 'Souhaitez-vous créer' not in s['messages'][-1]['content']
