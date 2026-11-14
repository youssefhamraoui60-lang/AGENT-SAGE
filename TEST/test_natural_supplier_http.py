from test_learning import setup,fixture
from app.services import supplier_sql,conversation_chat as chat,sage_crud as crud
import httpx
import asyncio
import pytest

@pytest.mark.parametrize('prefix',['corriger','corrige','rectifier','correction :'])
def test_name_correction_updates_draft_and_is_persisted(setup,monkeypatch,prefix):
    from app.services import business_store as db,learning_auto
    from uuid import UUID
    import importlib
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    async def forbidden(*a,**kw):raise AssertionError('Explicit correction must not need Qwen')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    s=send(c,s,'Créer un fournisseur Nom : suivant dans le système ICE : 001859517000047')
    s=send(c,s,prefix+' le nom de fournisseur est : AISSAOUI PARTS')
    p=s['state']['partners'][0]
    assert p['nom']=='AISSAOUI PARTS' and p['ice']=='001859517000047' and not p['approved']
    importlib.reload(learning_auto)
    with db.connection() as conn:
        rows=conn.execute('SELECT lesson FROM learning_corrections WHERE owner_id=%s AND conversation_id=%s',(owner,UUID(s['id']))).fetchall()
    assert any('nom' in row['lesson']['correct_interpretation'] for row in rows)

def test_padded_formal_email_prefers_declared_name_over_introduction(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    async def forbidden(*a,**kw):raise AssertionError('Explicit form must not need Qwen')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    s=send(c,s,'Bonjour,  Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système :   Nom de frs : AISSAOUI PARTS    Ice : 001859517000047  Je reste à votre disposition pour toute information complémentaire.    Cordialement.')
    assert s['state']['partners'][0]['nom']=='AISSAOUI PARTS'
    assert s['state']['partners'][0]['ice']=='001859517000047'

def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
    assert r.status_code==200,r.text
    result=r.json()
    assert '_pending' not in result['state']
    assert result['state']['analysis_job']['status']=='completed'
    return result

def fake_prepare(p):
    return {'status':'prepared','parameters':{'Nom':p['nom']},'target_folder':'TEST','transport':'direct_sql','test_fixture':True}

def test_recover_ice_from_failed_previous_turn_when_name_is_repeated(setup,monkeypatch):
    from app.services import business_store as db
    from uuid import UUID
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user','Merci de créer le fournisseur : Nom de frs : AISSAOUI PARTS ICE : 001859517000047')
        chat.append(conn,UUID(s['id']),'assistant','Votre demande est conservée. Indiquez le nom du fournisseur.')
    async def forbidden(*a,**kw):raise AssertionError('No model fallback expected')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    s=send(c,s,'le nom de fournisseur : AISSAOUI PARTS')
    assert s['state']['partners'][0]['ice']=='001859517000047'
    s=send(c,s,'et le ici déja dans la convértion')
    assert s['state']['partners'][0]['ice']=='001859517000047'
    assert not s['state']['partners'][0]['approved']

def test_history_recovery_does_not_copy_other_supplier_or_overwrite_current():
    from app.services.supplier_dialogue import recover_missing_history
    state={'partners':[{'id':'test','kind':'supplier','nom':'AISSAOUI PARTS','ice':'009999999999999'}]}
    assert not recover_missing_history(state,[{'role':'user','content':'Créer un fournisseur Nom : AISSAOUI PARTS ICE : 001859517000047'}])
    state['partners'][0].pop('ice')
    assert not recover_missing_history(state,[{'role':'user','content':'Créer un fournisseur Nom : AUTRE FOURNISSEUR ICE : 001859517000047'}])
    assert not state['partners'][0].get('ice')

def test_formal_supplier_email_with_frs_and_polite_closing(setup,monkeypatch):
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    async def forbidden_model(*a,**kw):raise AssertionError('This explicit form must not need Qwen')
    monkeypatch.setattr(chat.model,'extract',forbidden_model)
    monkeypatch.setattr(supplier_sql,'run',lambda *a,**kw:pytest.fail('No Sage writes'))
    text='Bonjour, Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système : Nom de frs : AISSAOUI PARTS Ice : 001859517000047 Je reste à votre disposition pour toute information complémentaire. Cordialement.'
    s=send(c,s,text);p=s['state']['partners'][0]
    assert p['nom']=='AISSAOUI PARTS' and p['ice']=='001859517000047'
    assert not p['approved'] and p['operation']['status']=='prepared'

def test_multiturn_without_qwen_and_without_insert(setup,monkeypatch):
    c,s,owner=setup
    monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    def forbidden(*args,**kw):raise AssertionError('No Sage call permitted in this test')
    monkeypatch.setattr(supplier_sql,'run',forbidden)
    async def outage(*args,**kw):raise httpx.ConnectError('fixture offline')
    monkeypatch.setattr(chat.model,'extract',outage)
    for text in ['Je veux créer un fournisseur','AUTO SERVICE','ville','Berrechid','adresse','lot 12','Correction : le nom est AUTO SERVICE SARL','ajoute ICE 007456789012345']:
        s=send(c,s,text)
    p=s['state']['partners'][0]
    assert p['nom']=='AUTO SERVICE SARL' and p['ville']=='Berrechid' and p['adresse']=='lot 12'
    assert p['ice']=='007456789012345' and not p['approved']
    s=send(c,s,'xyz incompréhensible')
    assert 'conservée' in s['messages'][-1]['content']
    assert 'extraction' not in s['messages'][-1]['content'].lower()

def test_sage_unavailable_is_not_reported_as_verified(setup,monkeypatch):
    c,s,owner=setup
    def unavailable(*args):raise crud.CrudError('controlled_sql_outage',503)
    monkeypatch.setattr(supplier_sql,'prepare_operation',unavailable)
    s=send(c,s,'Je veux créer un fournisseur')
    s=send(c,s,'ATLAS SERVICES')
    p=s['state']['partners'][0]
    assert p['nom']=='ATLAS SERVICES' and p['operation']['verification_unavailable']
    assert not p['approved'] and 'momentanément indisponible' in s['messages'][-1]['content']

def test_cancelled_verification_retains_newly_extracted_fields(setup,monkeypatch):
    c,s,owner=setup
    def cancelled(*args):raise asyncio.CancelledError()
    monkeypatch.setattr(supplier_sql,'prepare_operation',cancelled)
    s=send(c,s,'Je veux créer un fournisseur')
    s=send(c,s,'NOUVEAU NOM CONSERVÉ')
    assert s['state']['partners'][0]['nom']=='NOUVEAU NOM CONSERVÉ'
    assert not s['state']['partners'][0]['approved']
    assert 'conservée' in s['messages'][-1]['content']
