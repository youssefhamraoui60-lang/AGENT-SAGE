"""Full chat/approval path in an isolated local PG schema, with fake SQL writes."""
import sys,json
from pathlib import Path
from copy import deepcopy
from uuid import UUID
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from test_conversation_chat import fixture,create
from app.services import supplier_sql as sql,conversation_chat as chat,business_store as db

REQUEST='Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système :\nNom de frs : Izs.Tex\nIce :003224720000051'

@pytest.fixture
def flow(fixture,monkeypatch):
    client,queue=fixture;calls=[]
    defaults=json.loads((ROOT/'TEST/supplier.example.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(sql,'load_defaults',lambda:deepcopy(defaults))
    monkeypatch.setattr(chat,'supplier_security',lambda:{'ready':True,'folder':'TEST','transport':'direct_sql'})
    async def forbidden(*a,**k):raise AssertionError('Supplier recovery must not call the model')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    def run(values,execute=False,approved_duplicate_codes=None):
        calls.append({'execute':execute,'values':deepcopy(values),'codes':approved_duplicate_codes})
        if not execute:return {'ok':True,'rows':[{'RESULTAT':'VALIDATED_NO_INSERT','CODE_PROPOSE_NON_RESERVE':'F10016'}],
            'duplicate_warnings':[{'code':'F10014','name':'TEST'},{'code':'F10015','name':'TEST'}]}
        row={col:values[key] for key,col in sql.READBACK.items()}
        row.update(CODE_FOURNISSEUR='F10016',partner_active=2,supplier_active=2)
        return {'ok':True,'folder':'TEST','executed':True,'rows':[row]}
    monkeypatch.setattr(sql,'run',run)
    return client,calls

def send(client,session,text):
    r=client.post(f'/api/v1/chat/conversations/{session["id"]}/messages',json={'content':text,'revision':session['revision']})
    assert r.status_code==200,r.text
    return r.json()

def call(client,session,step,**flags):
    p=session['state']['partners'][0]
    return client.post(f'/api/v1/chat/conversations/{session["id"]}/partners/{p["id"]}/{step}',json={'revision':session['revision'],**flags})

def test_minimal_request_is_prepared_without_repeated_questions_or_model(flow):
    c,calls=flow;s=send(c,create(c),REQUEST);p=s['state']['partners'][0]
    assert p['operation']['status']=='prepared' and p['operation']['parameters']['Nom']=='Izs.Tex'
    assert p['operation']['parameters']['ICE']=='003224720000051'
    assert p['operation']['parameters']['IF']=='' and p['operation']['parameters']['RC']==''
    assert p['operation']['parameters']['Paiement']=='EFF60'
    assert p['operation']['duplicate_warnings'][0]['code']=='F10014'
    assert not p['reviewed'] and all(not x['execute'] for x in calls)
    again=send(c,s,'une nouvelle fiche fournisseur')
    assert again['state']['partners'][0]['id']==p['id'] and len(calls)==1
    assert again['state']['analysis_job']['status']=='completed'

def test_legacy_clarification_recovers_original_name_and_ice_without_model(flow):
    c,calls=flow;s=create(c)
    with db.connection() as conn:
        chat.append(conn,UUID(s['id']),'user',REQUEST)
        chat.append(conn,UUID(s['id']),'assistant','Souhaitez-vous créer une nouvelle fiche fournisseur ou utiliser une fiche existante ?')
        for _ in range(5):
            chat.append(conn,UUID(s['id']),'user','une nouvelle fiche fournisseur')
            chat.append(conn,UUID(s['id']),'assistant','Ancienne extraction interrompue.')
    s=send(c,s,'une nouvelle fiche fournisseur')
    p=s['state']['partners'][0]
    assert p['nom']=='Izs.Tex' and p['ice']=='003224720000051'
    assert p['operation']['status']=='prepared' and len(calls)==1

def test_explicit_duplicate_confirmation_then_one_sql_execution(flow):
    c,calls=flow;s=send(c,create(c),REQUEST)
    assert call(c,s,'execute',confirm=True).status_code==403
    assert call(c,s,'approve',confirm=True).status_code==423
    r=call(c,s,'approve',confirm=True,confirm_duplicates=True);assert r.status_code==200,r.text;s=r.json()
    assert all(not x['execute'] for x in calls)
    r=call(c,s,'execute',confirm=True);assert r.status_code==200,r.text;s=r.json()
    op=s['state']['partners'][0]['operation']
    assert op['status']=='succeeded' and op['record_keys']=={'BPSNUM':'F10016'}
    assert calls[-1]['codes']==['F10014','F10015']
    assert call(c,s,'execute',confirm=True).status_code==409
    assert len([x for x in calls if x['execute']])==1

def test_correction_preserves_identity_and_reprepares_only_changed_parameters(flow):
    c,calls=flow;s=send(c,create(c),REQUEST);before=s['state']['partners'][0]
    s=send(c,s,'téléphone : 0612345678');after=s['state']['partners'][0]
    assert after['id']==before['id'] and after['ice']==before['ice']
    assert after['operation']['id']!=before['operation']['id']
    assert after['operation']['parameters']['Telephone']=='0612345678'
    assert all(not x['execute'] for x in calls)

def test_new_collision_at_execution_requires_fresh_preparation(flow,monkeypatch):
    c,calls=flow;s=send(c,create(c),REQUEST)
    s=call(c,s,'approve',confirm=True,confirm_duplicates=True).json()
    original=sql.run
    def rejected(values,execute=False,**kwargs):
        if execute:return {'ok':False,'code':'sql_validation_rejected','sql_error_number':50109}
        return original(values,execute,**kwargs)
    monkeypatch.setattr(sql,'run',rejected)
    r=call(c,s,'execute',confirm=True);assert r.status_code==200,r.text;s=r.json()
    assert s['state']['partners'][0]['operation']['status']=='blocked'
    assert call(c,s,'approve',confirm=True,confirm_duplicates=True).status_code==409
    r=call(c,s,'prepare');assert r.status_code==200,r.text
    assert r.json()['state']['partners'][0]['operation']['status']=='prepared'

def test_resume_old_empty_checkpoint_recovers_supplier_without_model(flow):
    import asyncio
    c,calls=flow;s=create(c);identifier=UUID(s['id'])
    with db.connection() as conn:
        owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(identifier,)).fetchone()['owner_id']
        chat.append(conn,identifier,'user',REQUEST)
    job=chat.reserve_analysis(owner,identifier,'une nouvelle fiche fournisseur',s['revision'])
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True);state=row['state']
        state['analysis_job'].update(checkpoint='extracted',delta={'intent':'update'})
        chat.save_conversation_context(conn,owner,identifier,state);revision=row['revision']
    result=asyncio.run(chat.send(owner,identifier,'une nouvelle fiche fournisseur',revision,_job_id=job['id']))
    p=result['state']['partners'][0]
    assert p['nom']=='Izs.Tex' and p['ice']=='003224720000051' and p['operation']['status']=='prepared'
    assert all(not x['execute'] for x in calls)
