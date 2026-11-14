from test_learning import setup,fixture
from app.services import learning_auto as auto,learning,business_store as db,supplier_dialogue,learning_training as training
from uuid import UUID,uuid4
import pytest,json

def state():return {'articles':[],'partners':[{'id':'draft','kind':'supplier','nom':'PRIVÉ SARL','ice':'001234567890123','adresse':'Berrechid','ville':None,'approved':True,'operation':{'status':'prepared'}}]}

def evidence(c,s,owner):
    for i in range(2):
        conversation=s if i==0 else c.post('/api/v1/chat/conversations').json()
        before=state();after=auto.correct_relation('Berrechid est la ville, pas l’adresse',before)['state']
        auto.record(owner,UUID(conversation['id']),before,after,'Berrechid est la ville, pas l’adresse')

def test_immediate_correction_is_local_and_preserves_other_fields():
    result=supplier_dialogue.handle('Berrechid est la ville, pas l’adresse',state())
    p=result['state']['partners'][0]
    assert p['ville']=='Berrechid' and p['adresse'] is None and p['ice']=='001234567890123' and not p['approved']
    assert auto.correct_relation('non, c’est la ville',state()) is None

def test_evaluation_is_measured_and_unsafe_recipe_cannot_pass():
    metrics=auto.evaluate(auto.RECIPE)
    assert metrics['passed'] and metrics['before_errors']==3 and metrics['after_errors']==0
    assert not auto.evaluate({'operation':'execute_sql'})['passed']

def test_already_provided_information_and_new_intent_are_understood():
    current=state();current['_supplier_dialogue']={'expected_field':'ville'}
    result=supplier_dialogue.handle('tu m’as déjà demandé cette information',current)
    assert result['state']['partners']==current['partners'] and not result['state']['_supplier_dialogue'].get('expected_field')
    assert 'déjà fournies' in result['reply']
    result=supplier_dialogue.handle('je voulais créer un nouveau fournisseur',current)
    assert result['state']['partners'][0]['id']!='draft' and not result['state']['partners'][0].get('ice')
    assert result['state']['_supplier_dialogue']['expected_field']=='nom'

def test_periodic_worker_really_invokes_the_processing_loop(monkeypatch):
    import asyncio
    calls=[]
    monkeypatch.setattr(auto,'tick',lambda:calls.append('tick'))
    async def stop(_):raise asyncio.CancelledError()
    monkeypatch.setattr(auto.asyncio,'sleep',stop)
    with pytest.raises(asyncio.CancelledError):asyncio.run(auto.periodic())
    assert calls==['tick']

def test_automatic_activation_and_new_value_after_service_reload(setup):
    import importlib
    c,s,owner=setup;evidence(c,s,owner)
    with db.connection() as conn:
        raw=json.dumps(conn.execute('SELECT lesson FROM learning_corrections WHERE owner_id=%s',(owner,)).fetchall(),ensure_ascii=False)
    assert 'Berrechid' not in raw and 'PRIVÉ' not in raw and '001234567890123' not in raw
    reports=auto.tick(owner);assert len(reports)==1 and reports[0]['status']=='active'
    importlib.reload(auto)
    fresh=state();fresh['learning_context']=learning.retrieve(owner,'ESSAI DELTA correspond à la ville')
    result=auto.apply('ESSAI DELTA correspond à la ville',fresh)
    assert result['state']['partners'][0]['ville']=='ESSAI DELTA'
    assert not result['state']['partners'][0]['approved']
    assert auto.tick(owner)==[]
    auto.disable(owner,UUID(reports[0]['method_id']))
    assert auto.tick(owner)==[]
    assert not any(m['kind']=='evaluated_method' for m in learning.retrieve(owner,'ville')['memory'])

def test_repetition_same_conversation_is_not_sufficient(setup):
    c,s,owner=setup
    before=state();after=auto.correct_relation('Berrechid est la ville',before)['state']
    for text in ('Berrechid est la ville','non, Berrechid est la ville'):
        auto.record(owner,UUID(s['id']),before,after,text)
    assert auto.tick(owner)==[]

def test_auto_method_is_private_unless_administrator_allows_sharing(setup):
    c,s,owner=setup;evidence(c,s,owner)
    registered=c.post('/api/v1/chat/auth/register',json={'email':'auto-'+uuid4().hex+'@example.test','display_name':'Reader','password':'Auto-learning-test-2026!'});assert registered.status_code==201
    with db.connection() as conn:
        reader=conn.execute("SELECT id FROM chat_accounts WHERE display_name='Reader'").fetchone()['id'];company=uuid4()
        conn.execute("INSERT INTO learning_memberships(company_id,owner_id,folder,role,auto_share) VALUES(%s,%s,'TEST','member',true),(%s,%s,'TEST','member',false)",(company,owner,company,reader))
    auto.tick(owner)
    assert any(m['kind']=='evaluated_method' for m in learning.retrieve(reader,'ville')['memory'])
    assert not learning.retrieve(uuid4(),'ville')['memory']
    with db.connection() as conn:conn.execute('UPDATE learning_memberships SET active=false WHERE owner_id=%s',(reader,))
    assert not learning.retrieve(reader,'ville')['memory']

def test_anonymized_corrections_are_exported_not_trained(setup):
    c,s,owner=setup;evidence(c,s,owner)
    report=training.export_dataset(owner,force=True)
    assert not report['training_performed'] and report['manifest']['example_count']==1
    for entry in report['manifest']['files'].values():
        from pathlib import Path
        body=Path(entry['path']).read_text(encoding='utf-8')
        assert 'Berrechid' not in body and 'PRIVÉ' not in body
