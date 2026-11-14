from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from test_supplier_pasted_form import MESSAGE,ADDRESS
from app.services import supplier_sql,conversation_chat as chat

def test_pasted_form_is_prepared_without_model_or_sage_write(setup,monkeypatch):
    c,s,owner=setup
    async def forbidden(*a,**kw):raise AssertionError('No model required for explicit supplier form')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=send(c,s,MESSAGE)
    p=s['state']['partners'][0]
    assert p['nom']=='SOS MECANIQUE HYDRAULIQUE' and p['adresse']==ADDRESS
    assert p['ice']=='001538584000034' and p['identifiant_fiscal']=='1921340'
    assert not p.get('approved') and p['operation']['status']=='prepared'
    assert 'Souhaitez-vous créer' not in s['messages'][-1]['content']
    assert s['messages'][-1]['payload']['supplier_snapshots'][0]['name']==p['nom']
