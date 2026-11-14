from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from app.services import supplier_sql

def snapshots(session):return [m['payload']['supplier_snapshots'][0] for m in session['messages'] if m.get('payload',{}).get('supplier_snapshots')]
def value(snapshot,key):return next(r['value'] for r in snapshot['rows'] if r['key']==key)

def test_each_turn_has_immutable_supplier_values_after_reload(setup,monkeypatch):
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    def forbidden(*a,**kw):raise AssertionError('No Sage call permitted')
    monkeypatch.setattr(supplier_sql,'run',forbidden)
    s=send(c,s,'Je veux créer un fournisseur')
    s=send(c,s,'le nom du fournisseur est TABLEAU TEST')
    s=send(c,s,'la ville est Rabat')
    s=send(c,s,'la ville est Tanger')
    s=c.get('/api/v1/chat/conversations/'+s['id']).json()
    history=snapshots(s)
    assert len(history)==4
    assert [value(h,'Ville') for h in history]==[None,None,'Rabat','Tanger']
    assert [value(h,'Nom') for h in history]==[None,'TABLEAU TEST','TABLEAU TEST','TABLEAU TEST']
    assert all(len(h['rows'])==18 for h in history)
    assert all(set(h)=={'supplier_id','name','stage','rows'} for h in history)
    assert not s['state']['partners'][0]['approved']

def test_reported_name_sentence_has_inline_table_and_short_reply(setup,monkeypatch):
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=send(c,s,'bonjour je veux créer un fournisseur')
    s=send(c,s,'le fournisseur s’appelle Atlas Fournitures')
    message=s['messages'][-1]
    assert value(message['payload']['supplier_snapshots'][0],'Nom')=='Atlas Fournitures'
    assert len(message['content'])<130
    assert 'Fiche prête' in message['content']
