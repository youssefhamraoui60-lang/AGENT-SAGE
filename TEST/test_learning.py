"""Persistent learning integration: isolated PostgreSQL, never Sage writes."""
import sys,json,importlib
from pathlib import Path
from uuid import UUID,uuid4
from datetime import datetime,timezone
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from test_conversation_chat import fixture,create
from app.services import learning,learning_training as training,business_store as db,conversation_chat as chat
REAL_MODEL_EXTRACT=chat.model.extract

@pytest.fixture
def setup(fixture,monkeypatch,tmp_path):
    c,q=fixture;s=create(c)
    monkeypatch.setattr(training,'capability',lambda:{'available':False,'model':'qwen2.5:7b','digest':'test-baseline','format':'gguf','missing':['No verified training environment']})
    monkeypatch.setattr(training.settings,'learning_dataset_directory',str(tmp_path))
    with db.connection() as conn:owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(UUID(s['id']),)).fetchone()['owner_id']
    return c,s,owner

def test_pending_memory_not_used_until_explicit_review_and_survives_service_reload(setup):
    c,s,owner=setup
    r=c.post('/api/v1/chat/learning/items',json={'kind':'preference','title':'Langue','content':'Répondre en français avec des phrases courtes.'});assert r.status_code==200,r.text
    item=r.json();assert item['status']=='pending'
    assert learning.retrieve(owner,'français')['memory']==[]
    assert c.post('/api/v1/chat/learning/items/'+item['id']+'/review',json={'status':'validated','confirm':False}).status_code==422
    assert c.post('/api/v1/chat/learning/items/'+item['id']+'/review',json={'status':'validated','confirm':True}).status_code==200
    importlib.reload(learning)
    found=learning.retrieve(owner,'français')['memory'];assert found[0]['source']=='user' and found[0]['validated_at']
    assert learning.retrieve(uuid4(),'français')['memory']==[]
    with pytest.raises(Exception):learning.review(uuid4(),UUID(item['id']),'validated')

def test_documents_have_source_date_status_and_can_be_retrieved(setup):
    c,s,owner=setup
    item=learning.create_item(owner,'document','Procédure fournisseur','Pour préparer un fournisseur, vérifier les identifiants fiscaux avant confirmation.','procedure-fournisseurs.md')
    assert not learning.retrieve(owner,'identifiants fiscaux')['documents']
    learning.review(owner,item['id'],'validated')
    doc=learning.retrieve(owner,'identifiants fiscaux')['documents'][0]
    assert doc['source']=='procedure-fournisseurs.md' and doc['source_date'] and doc['status']=='validated'
    learning.review(owner,item['id'],'superseded')
    assert not learning.retrieve(owner,'identifiants fiscaux')['documents']

@pytest.mark.parametrize('content',['password=abc123','{"api_key":"secret-value"}','postgresql://user:secret@db/x','-----BEGIN PRIVATE KEY-----'])
def test_secrets_rejected_without_persisting(setup,content):
    c,s,owner=setup
    r=c.post('/api/v1/chat/learning/items',json={'kind':'document','title':'Test','content':content})
    assert r.status_code==422
    with db.connection() as conn:assert conn.execute('SELECT count(*) AS n FROM learning_items WHERE owner_id=%s',(owner,)).fetchone()['n']==0

def test_volatile_facts_cannot_become_persistent_memory(setup):
    c,s,owner=setup
    r=c.post('/api/v1/chat/learning/items',json={'kind':'rule','title':'Stock','content':'Le stock disponible est 120.'})
    assert r.status_code==422 and learning.retrieve(owner,'Quel est le stock disponible ?')['requires_live_data']

def seed_turn(s):
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user','Comment reconnaître un identifiant fiscal ?')
        return chat.append(conn,UUID(s['id']),'assistant','Il faut vérifier son format dans le dossier concerné.')

def test_feedback_is_required_before_export_and_correction_supersedes_previous(setup):
    c,s,owner=setup;message=seed_turn(s)
    before=training.export_dataset(owner,force=True);assert before['manifest']['example_count']==0
    r=c.post('/api/v1/chat/learning/feedback',json={'message_id':message,'verdict':'incorrect','expected':'Vérifier le format et demander confirmation.','confirm':True});assert r.status_code==200,r.text
    exported=training.export_dataset(owner,force=True)
    manifest=exported['manifest'];assert manifest['example_count']==1 and not exported['training_performed']
    files=manifest['files'];lines=[]
    for meta in files.values():lines+=Path(meta['path']).read_text(encoding='utf-8').splitlines()
    assert json.loads(lines[0])['messages'][1]['content']=='Vérifier le format et demander confirmation.'
    assert c.post('/api/v1/chat/learning/feedback',json={'message_id':message,'verdict':'incorrect','expected':'Autre correction validée.','confirm':True}).status_code==200
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM learning_items WHERE owner_id=%s AND status='validated'",(owner,)).fetchone()['n']==1
    assert training.export_dataset(owner,force=True)['manifest']['example_count']==1

def test_feedback_and_schedule_require_csrf_and_ownership(setup):
    c,s,owner=setup;message=seed_turn(s)
    with pytest.raises(Exception):learning.feedback(uuid4(),message,'correct',confirm=True)
    c.headers.pop('X-Chat-CSRF')
    assert c.post('/api/v1/chat/learning/feedback',json={'message_id':message,'verdict':'correct','confirm':True}).status_code==403

def test_schedule_and_dataset_dedup_holdout_are_not_training(setup):
    c,s,owner=setup
    assert c.put('/api/v1/chat/learning/schedule',json={'enabled':True,'min_examples':5,'interval_hours':24}).status_code==200
    assert training.export_dataset(owner)['status']=='waiting_for_validated_examples'
    rows=[{'id':uuid4(),'user_text':'Question '+str(i),'expected':'Réponse validée '+str(i),'conversation_id':uuid4(),'message_id':i,'created_at':datetime.now(timezone.utc)} for i in range(8)]
    examples,excluded=training.build_examples(rows+[rows[0]])
    assert excluded['duplicate_or_near_duplicate']>=1
    train={x['conversation_group'] for x in examples if x['split']=='train'};test={x['conversation_group'] for x in examples if x['split']=='test'}
    assert not train.intersection(test)

def test_exact_validated_correction_is_reusable_but_never_an_execution_permit(setup):
    c,s,owner=setup;text='Créer un fournisseur EXEMPLE'
    item=learning.create_item(owner,'correction','Nom fournisseur','Interpréter la demande de fournisseur EXEMPLE.','user',
        {'input_normalized':learning.normalized(text),'expected_delta':{'intent':'new','fournisseurs':[{'nom':'EXEMPLE'}]}})
    assert learning.exact_delta(learning.retrieve(owner,text),text) is None
    learning.review(owner,item['id'],'validated');context=learning.retrieve(owner,text)
    delta=learning.exact_delta(context,text);assert delta.fournisseurs[0].nom=='EXEMPLE'
    assert 'approval' not in delta.model_dump() and context['authority']=='context_only_never_execution_approval'

def test_explicit_personal_memory_is_validated_without_model_or_sage(setup,monkeypatch):
    c,s,owner=setup
    async def forbidden(*a,**k):raise AssertionError('No model for an explicit memory command')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'Retiens que je préfère des réponses en français.','revision':s['revision']})
    assert r.status_code==200,r.text
    assert r.json()['state']['analysis_job']['status']=='completed'
    with db.connection() as conn:
        row=conn.execute("SELECT status FROM learning_items WHERE owner_id=%s AND kind='preference'",(owner,)).fetchone()
        assert row['status']=='validated'

def test_validated_document_answers_a_question_without_model(setup,monkeypatch):
    c,s,owner=setup
    item=learning.create_item(owner,'document','Procédure fournisseur','Pour préparer un fournisseur, relire les informations puis confirmer la création.','guide-valide.md')
    learning.review(owner,item['id'],'validated')
    async def forbidden(*a,**k):raise AssertionError('Relevant validated document is sufficient')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'Comment préparer un fournisseur ?','revision':s['revision']})
    assert r.status_code==200,r.text
    assert 'guide-valide.md' in r.json()['messages'][-1]['content']
    assert r.json()['state']['learning_context']['documents'][0]['status']=='validated'

def test_live_queries_are_fresh_and_amounts_do_not_mix_currencies(monkeypatch):
    from types import SimpleNamespace
    from app.services import learning_live
    calls=[]
    def run(*args,**kwargs):
        request=json.loads(kwargs['input']);calls.append(request)
        return SimpleNamespace(stdout=json.dumps({'ok':True,'folder':'TEST','checked_at':'now','rows':[
            {'Devise':'MAD','Sens':1,'Montant':'100.00'},{'Devise':'MAD','Sens':-1,'Montant':'25.00'},
            {'Devise':'EUR','Sens':1,'Montant':'10.00'}]}))
    monkeypatch.setattr(learning_live.subprocess,'run',run)
    result=learning_live.read('balance','4411',company='20',ledger='SOC',date_from='2026-01-01',date_to='2026-11-02')
    assert result['totals']==[{'Devise':'MAD','Solde_signe':'75.00'},{'Devise':'EUR','Solde_signe':'10.00'}]
    learning_live.read('balance','4411',company='20',ledger='SOC',date_from='2026-01-01',date_to='2026-11-02')
    assert len(calls)==2 and all(c['folder']=='TEST' for c in calls)

def test_explicit_correction_can_fix_future_literal_extraction(setup):
    c,s,owner=setup;text="Créer le fournisseur ORION SERVICES avec l'ICE 004444444444444."
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user',text)
        message=chat.append(conn,UUID(s['id']),'assistant','Le nom a été mal interprété.')
    learning.feedback(owner,message,'incorrect',expected='Nom : ORION SERVICES\nICE : 004444444444444',confirm=True)
    context=learning.retrieve(owner,text)
    delta=learning.exact_delta(context,text)
    assert delta is not None and delta.fournisseurs[0].nom=='ORION SERVICES'
    assert delta.fournisseurs[0].ice=='004444444444444'

def test_model_receives_only_validated_rag_context_without_execution_authority(setup,monkeypatch):
    import asyncio
    from app.services import chat_model
    c,s,owner=setup
    pending=learning.create_item(owner,'document','En attente','Procédure fournisseurs : texte non validé.','pending.md')
    approved=learning.create_item(owner,'document','Validé','Procédure fournisseurs : vérifier avant confirmation.','approved.md')
    learning.review(owner,approved['id'],'validated')
    context=learning.retrieve(owner,'procédure fournisseurs')
    captured={}
    async def stream(client,payload):
        captured.update(payload)
        return {'done':True,'message':{'content':'{"intent":"lookup"}'}},{}
    monkeypatch.setattr(chat_model,'request_stream',stream)
    token=chat_model.FORCE_AI.set(True)
    try:asyncio.run(REAL_MODEL_EXTRACT('Explique la procédure fournisseurs',{'articles':[],'learning_context':context},[]))
    finally:chat_model.FORCE_AI.reset(token)
    data=json.loads(captured['messages'][1]['content'])['connaissances_retrouvees']
    assert data['documents'][0]['source']=='approved.md'
    assert 'pending.md' not in json.dumps(data)
    assert 'autorisation' in captured['messages'][0]['content']
