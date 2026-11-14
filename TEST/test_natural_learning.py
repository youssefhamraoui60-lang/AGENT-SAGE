from test_learning import setup,fixture
from app.services import learning,learning_chat,learning_methods,business_store as db
from uuid import uuid4,UUID
import pytest,importlib

def test_explicit_preference_persists_without_buttons(setup):
    c,s,owner=setup
    result=learning_chat.turn(owner,UUID(s['id']),'Retiens que je préfère des réponses courtes.')
    assert result['items'][0]['status']=='validated'
    importlib.reload(learning)
    assert learning.retrieve(owner,'réponses')['memory'][0]['content']=='je préfère des réponses courtes.'
    result=learning_chat.turn(owner,UUID(s['id']),'Quelles règles as-tu retenues ?')
    assert '1. je préfère' in result['text']
    assert not learning.retrieve(uuid4(),'réponses')['memory']

def test_conflicting_preference_waits_for_explicit_choice(setup):
    c,s,owner=setup;conversation=UUID(s['id'])
    learning_chat.turn(owner,conversation,'Retiens que je préfère des réponses courtes.')
    result=learning_chat.turn(owner,conversation,'Retiens que je préfère des réponses longues.')
    assert result['items'][0]['status']=='pending'
    assert 'diffère' in result['text']
    assert len(learning.retrieve(owner,'réponses')['memory'])==1

def test_shared_method_requires_membership_independent_review_and_no_private_turns(setup):
    c,s,owner=setup;company=uuid4()
    with pytest.raises(Exception):learning_methods.propose(owner,company,'Fiscalité','Vérifier le format fiscal avant confirmation.')
    r=c.post('/api/v1/chat/auth/register',json={'email':'review-'+uuid4().hex+'@example.test','display_name':'Reviewer','password':'Review-example-password-2026!'})
    assert r.status_code==201,r.text
    with db.connection() as conn:
        reviewer=conn.execute('SELECT id FROM chat_accounts WHERE display_name=%s',('Reviewer',)).fetchone()['id']
        conn.execute("INSERT INTO learning_memberships(company_id,owner_id,folder,role) VALUES(%s,%s,'TEST','member'),(%s,%s,'TEST','reviewer')",(company,owner,company,reviewer))
    method=learning_methods.propose(owner,company,'Fiscalité','Vérifier le format fiscal avant confirmation.')
    assert not learning.retrieve(reviewer,'format fiscal')['memory']
    with pytest.raises(Exception):learning_methods.review(owner,method['id'],True,{'passed':True,'suite':'independent','case_count':3})
    learning_methods.review(reviewer,method['id'],True,{'passed':True,'suite':'independent','case_count':3})
    assert any(i['kind']=='company_method' for i in learning.retrieve(reviewer,'format fiscal')['memory'])
    assert not learning.retrieve(uuid4(),'format fiscal')['memory']
    with db.connection() as conn:conn.execute('UPDATE learning_memberships SET active=false WHERE owner_id=%s',(owner,))
    assert not learning.retrieve(owner,'format fiscal')['memory']
    learning_methods.review(reviewer,method['id'],False)
    assert not learning.retrieve(reviewer,'format fiscal')['memory']

def test_legacy_documents_require_explicit_access_grant(setup):
    c,s,owner=setup;document=uuid4()
    with db.connection() as conn:
        conn.execute("INSERT INTO knowledge_documents(id,source_path,sha256,source_kind,reviewed) VALUES(%s,'private-procedure.md','test','manual',true)",(document,))
        conn.execute('INSERT INTO knowledge_passages(document_id,ordinal,content) VALUES(%s,1,%s)',(document,'Procédure documentaire confidentielle de rapprochement fiscal.'))
    assert not learning.retrieve(owner,'rapprochement fiscal')['documents']
    with pytest.raises(Exception):learning.import_document(owner,document)
    with db.connection() as conn:conn.execute("INSERT INTO learning_document_access VALUES(%s,%s,%s,NULL,'TEST')",(uuid4(),document,owner))
    assert learning.retrieve(owner,'rapprochement fiscal')['documents'][0]['source']=='private-procedure.md'
    assert not learning.retrieve(uuid4(),'rapprochement fiscal')['documents']

def test_repeated_corrections_strengthen_only_pending_signal(setup):
    from app.services.learning_signals import record
    c,s,owner=setup
    before={'partners':[{'id':'draft','nom':'Ancien'}]};after={'partners':[{'id':'draft','nom':'Corrigé'}]}
    record(owner,UUID(s['id']),before,after,'Correction du nom')
    record(owner,UUID(s['id']),before,after,'Non, corrige le nom')
    with db.connection() as conn:signal=conn.execute('SELECT * FROM learning_items WHERE owner_id=%s',(owner,)).fetchone()
    assert signal['status']=='pending' and signal['payload']['occurrences']==2
    assert 'Ancien' not in signal['content'] and 'Corrigé' not in signal['content']
    assert not learning.retrieve(owner,'correction nom')['memory']
