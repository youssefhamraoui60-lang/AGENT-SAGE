from test_learning import setup,fixture
from app.services import learning,learning_chat,business_store as db
from uuid import UUID,uuid4

def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
    assert r.status_code==200,r.text
    return r.json()

def latest_rule(s):
    return next(m['memory_rules'][-1] for m in reversed(s['messages']) if m.get('memory_rules'))

def act(c,s,item,action,**extra):
    return c.post(f'/api/v1/chat/learning/conversations/{s["id"]}/items/{item["id"]}/action',json={'action':action,'sha':item['sha256'],'confirm':True,**extra})

def test_inline_propose_edit_validate_and_forget(setup):
    c,s,owner=setup
    s=send(c,s,'Retiens que je préfère des réponses courtes.')
    item=latest_rule(s);assert item['status']=='validated' and 'mémoire et connaissances' not in s['messages'][-1]['content'].lower()
    assert learning.retrieve(owner,'réponses')['memory']
    r=act(c,s,item,'edit',content='Je préfère des réponses courtes en français.');assert r.status_code==200,r.text;s=r.json()
    item=latest_rule(s);assert item['status']=='pending'
    s=act(c,s,item,'validate').json();assert latest_rule(s)['status']=='validated'
    s=send(c,s,'Quelles règles as-tu retenues ?')
    assert 'réponses courtes en français' in latest_rule(s)['content']
    s=send(c,s,'Oublie la règle 1')
    assert 'oubliée' in s['messages'][-1]['content']
    assert learning.retrieve(owner,'réponses')['memory']==[]

def test_reject_and_text_validation_do_not_authorize_sage(setup):
    c,s,owner=setup
    s=send(c,s,'Retiens que les procédures doivent être présentées en tableaux.')
    s=send(c,s,'Refuse cette règle')
    assert latest_rule(s)['status']=='rejected'
    assert not s['state'].get('partners') and not s['state'].get('approved')
    assert learning.retrieve(owner,'tableaux')['memory']==[]

def test_feedback_creates_pending_correction_then_reused_in_new_conversation(setup):
    c,s,owner=setup
    from app.services import conversation_chat as chat
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user','Comment vérifier un identifiant fiscal ?')
        message=chat.append(conn,UUID(s['id']),'assistant','Réponse à corriger.')
    r=c.post('/api/v1/chat/learning/conversations/'+s['id']+'/feedback',json={'message_id':message,'verdict':'incorrect','expected':'Vérifiez le format puis demandez confirmation.'})
    assert r.status_code==200,r.text;s=r.json();item=latest_rule(s)
    assert item['status']=='pending'
    with db.connection() as conn:assert conn.execute('SELECT count(*) AS n FROM learning_feedback WHERE owner_id=%s',(owner,)).fetchone()['n']==0
    s=act(c,s,item,'validate').json()
    fresh=c.post('/api/v1/chat/conversations').json()
    fresh=send(c,fresh,'Comment vérifier un identifiant fiscal ?')
    assert 'Vérifiez le format puis demandez confirmation.' in fresh['messages'][-1]['content']
    assert fresh['state']['learning_context']['used_example_source']
    assert not fresh['state'].get('partners')

def test_memory_controls_require_csrf_and_owner_and_fresh_content(setup):
    c,s,owner=setup;s=send(c,s,'Retiens que je préfère les listes.')
    item=latest_rule(s)
    r=c.post(f'/api/v1/chat/learning/conversations/{s["id"]}/items/{item["id"]}/action',json={'action':'validate','sha':'0'*64,'confirm':True})
    assert r.status_code==409
    try:learning_chat.action(uuid4(),UUID(s['id']),UUID(item['id']),'validate',sha=item['sha256'],confirm=True)
    except Exception:pass
    else:raise AssertionError('Other owner must not review the rule')
    c.headers.pop('X-Chat-CSRF')
    assert act(c,s,item,'validate').status_code==403

def test_ambiguous_forget_does_not_forget_multiple_rules(setup):
    c,s,owner=setup
    a=learning.create_item(owner,'preference','Langue','Je préfère le français.');learning.review(owner,a['id'],'validated')
    b=learning.create_item(owner,'preference','Présentation','Je préfère les listes.');learning.review(owner,b['id'],'validated')
    s=send(c,s,'Que sais-tu de moi ?');s=send(c,s,'Oublie cette règle')
    assert 'Quelle règle' in s['messages'][-1]['content']
    with db.connection() as conn:assert conn.execute("SELECT count(*) AS n FROM learning_items WHERE owner_id=%s AND status='validated'",(owner,)).fetchone()['n']==2

def test_validated_rule_edit_waits_for_new_validation(setup):
    c,s,owner=setup;s=send(c,s,'Retiens que je préfère le français.')
    original=latest_rule(s)
    s=act(c,s,original,'edit',content='Je préfère le français et les réponses courtes.').json();replacement=latest_rule(s)
    assert replacement['status']=='pending'
    assert [r['content'] for r in learning.retrieve(owner,'français')['memory']]==[original['content']]
    s=act(c,s,replacement,'validate').json()
    found=learning.retrieve(owner,'français')['memory']
    assert len(found)==1 and found[0]['content']=='Je préfère le français et les réponses courtes.'

def test_forgetting_feedback_rule_stops_derived_example_reuse(setup):
    c,s,owner=setup
    from app.services import conversation_chat as chat
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user','Comment reconnaître cet identifiant ?')
        message=chat.append(conn,UUID(s['id']),'assistant','Ancienne réponse.')
    r=c.post('/api/v1/chat/learning/conversations/'+s['id']+'/feedback',json={'message_id':message,'verdict':'incorrect','expected':'Lire les informations avant confirmation.'})
    s=r.json();s=act(c,s,latest_rule(s),'validate').json()
    assert learning.document_answer(learning.retrieve(owner,'Comment reconnaître cet identifiant ?'),'Comment reconnaître cet identifiant ?')
    s=send(c,s,'Quelles règles as-tu retenues ?')
    s=act(c,s,latest_rule(s),'forget').json()
    assert learning.document_answer(learning.retrieve(owner,'Comment reconnaître cet identifiant ?'),'Comment reconnaître cet identifiant ?') is None
