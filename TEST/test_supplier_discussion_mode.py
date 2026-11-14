from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from app.services import supplier_sql,conversation_chat as chat

def test_off_topic_is_short_and_does_not_become_a_name(setup,monkeypatch):
    c,s,owner=setup
    async def forbidden(*a,**kw):raise AssertionError('No model needed for off-topic message')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    s=c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier'}).json()
    s=send(c,s,'je veux manger')
    assert s['messages'][-1]['content'].startswith('Désolé,') and not s['state'].get('partners')
    s=send(c,s,'Je veux créer un fournisseur')
    before=s['state']['partners']
    s=send(c,s,'je veux manger')
    assert s['state']['partners']==before and s['messages'][-1]['content'].startswith('Désolé,')

def test_dedicated_supplier_conversation_and_normal_conversations(setup,monkeypatch):
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    def forbidden(*a,**kw):raise AssertionError('No Sage call permitted')
    async def model_forbidden(*a,**kw):raise AssertionError('No model needed for this route')
    monkeypatch.setattr(supplier_sql,'run',forbidden);monkeypatch.setattr(chat.model,'extract',model_forbidden)
    r=c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier'});assert r.status_code==200,r.text
    dedicated=r.json();assert dedicated['folder']=='TEST' and dedicated['state']['discussion_mode']=='supplier'
    assert 'fournisseur' in dedicated['messages'][0]['content']
    dedicated=send(c,dedicated,'Créer un article BOUTON TEST')
    assert 'réservée aux fournisseurs' in dedicated['messages'][-1]['content']
    assert not dedicated['state'].get('articles')
    dedicated=send(c,dedicated,'le nom du fournisseur est BOUTON FOURNISSEUR')
    assert dedicated['state']['partners'][0]['nom']=='BOUTON FOURNISSEUR'
    assert dedicated['state']['discussion_mode']=='supplier'
    reopened=c.get('/api/v1/chat/conversations/'+dedicated['id']).json()
    assert reopened['state']['discussion_mode']=='supplier'
    normal=c.post('/api/v1/chat/conversations').json()
    assert normal['state'].get('discussion_mode','general')=='general'
    assert c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier','folder':'PROD'}).status_code==422
