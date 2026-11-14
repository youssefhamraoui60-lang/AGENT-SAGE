from test_learning import setup,fixture
from app.services import supplier_sql,conversation_chat as chat
from test_natural_supplier_http import send,fake_prepare

def test_supplier_name_is_first_message_in_each_new_conversation(setup,monkeypatch):
    c,s,owner=setup;prepared=[]
    def prepare(p):prepared.append(p['nom']);return fake_prepare(p)
    def forbidden(*a,**kw):raise AssertionError('No Sage call permitted')
    async def model_forbidden(*a,**kw):raise AssertionError('No model required for literal name')
    monkeypatch.setattr(supplier_sql,'prepare_operation',prepare)
    monkeypatch.setattr(supplier_sql,'run',forbidden)
    monkeypatch.setattr(chat.model,'extract',model_forbidden)
    identifiers=[]
    for _ in range(2):
        fresh=c.post('/api/v1/chat/conversations').json()
        fresh=send(c,fresh,'le nom de fourniseur est ABDHADI TA')
        p=fresh['state']['partners'][0];identifiers.append(p['id'])
        assert p['nom']=='ABDHADI TA' and not p['approved'] and not p.get('ice')
        assert p['operation']['status']=='prepared'
    assert len(set(identifiers))==2 and prepared==['ABDHADI TA','ABDHADI TA']

def test_exact_reported_dialogue_without_qwen_or_any_sage_call(setup,monkeypatch):
    c,s,owner=setup;prepared=[]
    def prepare(p):prepared.append(p['nom']);return fake_prepare(p)
    def forbidden(*a,**kw):raise AssertionError('No Sage call permitted')
    async def model_forbidden(*a,**kw):raise AssertionError('No Qwen required for clarification')
    monkeypatch.setattr(supplier_sql,'prepare_operation',prepare)
    monkeypatch.setattr(supplier_sql,'run',forbidden)
    monkeypatch.setattr(chat.model,'extract',model_forbidden)
    for text in ['BARI Ne ajouter wahade foourniseur','je dire créer un fourniseur mais on darija','le darija pas le nom de fourniseur sample darija']:
        s=send(c,s,text)
        assert not s['state']['partners'][0].get('nom')
        assert not prepared and not s['state']['partners'][0].get('approved')
    identifier=s['state']['partners'][0]['id']
    s=send(c,s,'le nom de fourniseur est ABDHADI TA')
    p=s['state']['partners'][0]
    assert p['nom']=='ABDHADI TA' and p['id']==identifier and not p['approved']
    assert prepared==['ABDHADI TA'] and p['operation']['status']=='prepared'
