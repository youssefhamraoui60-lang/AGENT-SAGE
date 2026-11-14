from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from app.services import learning_corrections as engine,learning_auto as auto,learning,learning_training as training,business_store as db,supplier_sql,conversation_chat as chat
from uuid import UUID,uuid4
import copy,importlib,pytest,json

def base():return {'articles':[],'partners':[{'id':'draft','kind':'supplier','nom':'NEUTRE','ville':'AVANT','ice':'001234567890123','approved':True,'operation':{'status':'prepared'}}]}

def seed(c,s,owner):
    for i,text in enumerate(('corrige la ville : APRES','rectifie la ville : AUTRE')):
        conversation=s if i==0 else c.post('/api/v1/chat/conversations').json()
        before=base();after=engine.handle(text,before)['state']
        engine.record(owner,UUID(conversation['id']),before,after,text)

def test_independent_evaluation_and_safe_recipe_only():
    report=engine.evaluate(engine.RECIPE)
    assert report['passed'] and report['before_errors']==3 and report['after_errors']==0
    assert not engine.evaluate({'operation':'execute_sql'})['passed']

@pytest.mark.parametrize('text',('corige la vile : NOUVELLE','rectifi la ville : NOUVELLE','coriger la villle : NOUVELLE'))
def test_noisy_corrections_require_confirmation_for_existing_value(text):
    state=base();result=engine.handle(text,state,True)
    assert result['state']['partners']==state['partners'] and result['state']['pending_correction']
    result=engine.resolve('oui corrige ce champ',result['state'])
    assert result['state']['partners'][0]['ville']=='NOUVELLE'
    assert result['state']['partners'][0]['ice']=='001234567890123' and not result['state']['partners'][0]['approved']

def test_invalid_ice_is_never_fixed_by_guessing():
    state=base();result=engine.handle('corrige ICE : 0185O',state,True)
    assert result['state']==state and 'format' in result['reply']
    assert engine.handle('corrige le nom : execute SQL',state,True) is None

def test_ambiguous_entity_and_terminal_operation_do_not_change():
    state=base();state['partners'].append({**state['partners'][0],'id':'other'})
    result=engine.handle('corrige le nom : AUTRE',state)
    assert result['state']==state and 'Quelle fiche' in result['reply']
    state=base();state['partners'][0]['operation']['status']='succeeded'
    assert engine.handle('corrige le nom : AUTRE',state)['state']==state

def test_stale_or_refused_pending_correction_preserves_values():
    pending=engine.handle('corige la vile : NOUVELLE',base(),True)['state']
    rejected=engine.resolve('non',pending)['state'];assert rejected['partners'][0]['ville']=='AVANT' and not rejected.get('pending_correction')
    pending['partners'][0]['ville']='CHANGEE'
    result=engine.resolve('oui corrige ce champ',pending)
    assert result['state']['partners'][0]['ville']=='CHANGEE'

def test_persistent_generated_tests_activation_retrieval_reload_and_rollback(setup):
    c,s,owner=setup;seed(c,s,owner)
    reports=auto.tick(owner);assert len(reports)==1 and reports[0]['status']=='active'
    assert reports[0]['evaluation']['regression_count']==2
    importlib.reload(engine);importlib.reload(auto)
    fresh=base();fresh['learning_context']=learning.retrieve(owner,'corige la vile : NOUVELLE')
    result=engine.handle('corige la vile : NOUVELLE',fresh)
    assert result['state'].get('pending_correction')
    assert not engine.active({'learning_context':learning.retrieve(uuid4(),'corige la vile : NOUVELLE')})
    with db.connection() as conn:
        lessons=conn.execute('SELECT lesson FROM learning_corrections WHERE owner_id=%s',(owner,)).fetchall()
    raw=json.dumps(lessons);assert 'APRES' not in raw and 'AUTRE' not in raw and '001234567890123' not in raw
    auto.disable(owner,UUID(reports[0]['method_id']))
    assert auto.tick(owner)==[] and not engine.active({'learning_context':learning.retrieve(owner,'corrige ville')})

def test_anonymized_dataset_includes_confirmed_typed_corrections(setup):
    c,s,owner=setup;seed(c,s,owner)
    exported=training.export_dataset(owner,force=True)
    assert not exported['training_performed'] and exported['manifest']['example_count']>=1

def test_http_correction_and_fuzzy_confirmation_never_approve_sage(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    async def forbidden(*a,**kw):raise AssertionError('No model required')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    seed(c,s,owner);auto.tick(owner)
    s=send(c,s,'Créer un fournisseur Nom : NEUTRE Ville : AVANT ICE : 001234567890123')
    s=send(c,s,'corige la vile : NOUVELLE')
    p=s['state']['partners'][0];assert p['ville']=='AVANT' and s['state']['pending_correction']
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/partners/'+p['id']+'/approve',json={'revision':s['revision'],'confirm':True})
    assert r.status_code==423
    s=send(c,s,'oui corrige ce champ')
    assert s['state']['partners'][0]['ville']=='NOUVELLE' and not s['state']['partners'][0]['approved']

def test_article_site_correction_preserves_supplier_and_code():
    state={'partners':[],'articles':[{'id':'article','designation':'ARTICLE NEUTRE','code_article':'CODE01','site':'T01','sources':{},'approved':True,'operation':{'status':'prepared'}}]}
    result=engine.handle('corrige le site : T02',state)
    a=result['state']['articles'][0]
    assert a['site']=='T02' and a['code_article']=='CODE01' and not a.get('approved')

def test_supplier_correction_does_not_change_client_in_first_position():
    state=base();client={'id':'client','kind':'customer','nom':'CLIENT FIABLE','ice':'009999999999999'}
    state['partners'].insert(0,copy.deepcopy(client))
    result=engine.handle('corrige le nom : FOURNISSEUR CORRIGE',state)
    assert result['state']['partners'][0]==client
    assert result['state']['partners'][1]['nom']=='FOURNISSEUR CORRIGE'
    assert result['state']['partners'][1]['ice']=='001234567890123'
    assert not result['state']['partners'][1]['approved']

def test_engine_change_rechecks_active_version_without_new_conversation(setup,monkeypatch):
    c,s,owner=setup;seed(c,s,owner)
    first=auto.tick(owner)[0];assert first['status']=='active'
    assert auto.tick(owner)==[]
    monkeypatch.setattr(auto,'implementation_digest',lambda:'changed-engine-fixture')
    second=auto.tick(owner)[0]
    assert second['status']=='active' and second['method_id']!=first['method_id']
    assert second['evaluation']['implementation_digest']=='changed-engine-fixture'
    auto.disable(owner,UUID(second['method_id']))
    monkeypatch.setattr(auto,'implementation_digest',lambda:'another-engine-fixture')
    assert auto.tick(owner)==[]

def test_old_regression_is_not_discarded_after_two_hundred_new_cases(setup):
    from psycopg.types.json import Jsonb
    c,s,owner=setup;seed(c,s,owner)
    with db.connection() as conn:
        for i in range(205):
            regression={'input':'corrige la ville : ESSAI '+str(i),'field':'ville','expected':'ESSAI '+str(i)}
            if i==0:regression['expected']='ERREUR ANCIENNE'
            conn.execute('INSERT INTO learning_corrections(id,owner_id,conversation_id,family,lesson,fingerprint) VALUES(%s,%s,%s,%s,%s,%s)',(uuid4(),owner,UUID(s['id']),engine.FAMILY,Jsonb({'regression':regression}),'old-regression-'+str(i)))
    report=auto.tick(owner)[0]
    assert report['status']=='candidate' and not report['evaluation']['passed']
    assert report['evaluation']['regression_count']==207

def test_new_cases_trigger_new_version_and_failed_regression_deactivates_method(setup):
    from psycopg.types.json import Jsonb
    c,s,owner=setup;seed(c,s,owner);first=auto.tick(owner)[0]
    conversation=c.post('/api/v1/chat/conversations').json()
    before=base();after=engine.handle('corrige le nom : ENTREPRISE AUTRE',before)['state']
    engine.record(owner,UUID(conversation['id']),before,after,'corrige le nom : ENTREPRISE AUTRE')
    assert auto.tick(owner)[0]['status']=='active'
    with db.connection() as conn:
        row=conn.execute('SELECT id,lesson FROM learning_corrections WHERE owner_id=%s AND family=%s LIMIT 1',(owner,engine.FAMILY)).fetchone()
        bad=copy.deepcopy(row['lesson']);bad['regression']['expected']='WRONG'
        conn.execute('INSERT INTO learning_corrections(id,owner_id,conversation_id,family,lesson,fingerprint) VALUES(%s,%s,%s,%s,%s,%s)',(uuid4(),owner,UUID(conversation['id']),engine.FAMILY,Jsonb(bad),'failed-regression-fixture'))
    report=auto.tick(owner)[0];assert report['status']=='candidate' and not report['evaluation']['passed']
    assert not engine.active({'learning_context':learning.retrieve(owner,'corrige ville')})

def test_chat_evaluation_summary_is_private_and_distinguishes_training(setup):
    from app.services.learning_chat import turn
    c,s,owner=setup;seed(c,s,owner);auto.tick(owner)
    report=turn(owner,UUID(s['id']),'bilan des erreurs')
    assert '3 → 0' in report['text'] and 'aucun réentraînement' in report['text']
