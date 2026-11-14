from test_learning import setup,fixture
from test_natural_supplier_http import send
from test_supplier_fiscal_slashes import MESSAGE
from app.services import supplier_sql,conversation_chat as chat

def test_bad_ice_kept_in_table_and_no_sql_preparation(setup,monkeypatch):
    c,s,owner=setup
    def forbidden(*a,**kw):raise AssertionError('No SQL preparation with malformed ICE')
    async def model_forbidden(*a,**kw):raise AssertionError('No model required for explicit slash form')
    monkeypatch.setattr(supplier_sql,'prepare_operation',forbidden);monkeypatch.setattr(chat.model,'extract',model_forbidden)
    s=send(c,s,MESSAGE);p=s['state']['partners'][0]
    assert p['ice']=='00295940100040' and p['identifiant_fiscal']=='50647721'
    assert p['operation']['status']=='blocked' and not p['approved']
    assert '14 chiffres' in s['messages'][-1]['content']
    rows={r['key']:r['value'] for r in s['messages'][-1]['payload']['supplier_snapshots'][0]['rows']}
    assert rows['ICE']=='00295940100040' and rows['IF']=='50647721'
    assert rows['Adresse']=='bouskoura victoria oulad saleh bloc 24'
