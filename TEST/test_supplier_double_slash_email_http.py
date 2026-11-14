from test_learning import setup,fixture
from test_natural_supplier_http import send
from test_supplier_double_slash_email import MESSAGE
from app.services import conversation_chat as chat,supplier_sql

def test_exact_email_form_never_loses_data_or_calls_model(setup,monkeypatch):
    c,s,owner=setup
    async def model_forbidden(*a,**kw):raise AssertionError('No model required')
    def forbidden(*a,**kw):raise AssertionError('No SQL preparation permitted for unsupported email')
    monkeypatch.setattr(chat.model,'extract',model_forbidden);monkeypatch.setattr(supplier_sql,'prepare_operation',forbidden)
    s=send(c,s,MESSAGE);p=s['state']['partners'][0]
    assert p['nom']=='AL ALAMIA' and p['email']=='auto.alalamia@gmail.com'
    assert p['ice']=='003388875000087' and p['identifiant_fiscal']=='60106228'
    assert p['operation']['status']=='blocked' and not p['approved']
    assert 'Email conservé' in s['messages'][-1]['content']
