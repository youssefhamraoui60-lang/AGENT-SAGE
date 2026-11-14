from test_learning import setup,fixture
from test_natural_supplier_http import send
from test_supplier_articles_split import MESSAGE
from app.services import supplier_sql,conversation_chat as chat

def test_reported_mixed_request_prepares_three_independent_drafts(setup,monkeypatch):
    c,s,owner=setup
    async def forbidden(*a,**kw):raise AssertionError('No model required to split explicit clauses')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    s=send(c,s,MESSAGE)
    state=s['state'];p=state['partners'][0]
    assert p['nom']=='VM HOLZ TIMBER'
    assert [a['designation'] for a in state['articles']]==['madriers 3m','madriers 4m']
    assert all(a.get('fournisseur_nom')=='VM HOLZ TIMBER' for a in state['articles'])
    assert all(not a.get('approved') for a in state['articles']) and not p.get('approved')
    snapshot=s['messages'][-1]['payload']['supplier_snapshots'][0]
    assert snapshot['name']=='VM HOLZ TIMBER'
