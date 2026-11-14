"""Explicit partner review is scoped learning, never ERP write approval."""
import os
import pytest
from test_conversation_chat import fixture,create,send
from app.services import business_store as db

pytestmark=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='isolated local PG only')


def test_partner_review_retains_experience_and_never_creates(fixture):
    client,queue=fixture
    state=send(client,queue,create(client),'Créer un client Atlas, pays MA.',
               {'intent':'new','clients':[{'nom':'Atlas','pays':'MA'}]})
    p=state['state']['partners'][0]
    url=f"/api/v1/chat/conversations/{state['id']}/partners/{p['id']}/review"
    assert client.post(url,json={'revision':state['revision'],'confirm':False}).status_code==422
    reviewed=client.post(url,json={'revision':state['revision'],'confirm':True})
    assert reviewed.status_code==200,reviewed.text
    p=reviewed.json()['state']['partners'][0]
    assert p['reviewed'] and p['field_states']['nom']['status']=='confirmed'
    assert not p['checks']['creation_ready'] and not p['checks']['sage_created']
    assert client.post(url,json={'revision':state['revision'],'confirm':True}).status_code==409
    with db.connection() as conn:
        example=conn.execute('SELECT snapshot FROM chat_business_examples ORDER BY id DESC LIMIT 1').fetchone()['snapshot']
        assert example['_experience']['correct_intent']=='customer_draft'
        assert example['_experience']['validated_by_human']


@pytest.mark.parametrize('mode,expected',[('stale',409),('csrf',403),('missing',404),('reader',403)])
def test_partner_review_keeps_existing_authorization_boundaries(fixture,mode,expected):
    from uuid import uuid4
    client,queue=fixture
    state=send(client,queue,create(client),'Créer un fournisseur Atlas.',{'intent':'new','fournisseurs':[{'nom':'Atlas'}]})
    p=state['state']['partners'][0];identifier=str(uuid4()) if mode=='missing' else p['id']
    if mode=='csrf':client.headers['X-Chat-CSRF']='invalid'
    if mode=='reader':
        with db.connection() as conn:conn.execute("UPDATE chat_web_sessions SET role='reader'")
    response=client.post(f"/api/v1/chat/conversations/{state['id']}/partners/{identifier}/review",
                         json={'revision':999 if mode=='stale' else state['revision'],'confirm':True})
    assert response.status_code==expected,response.text
    with db.connection() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM chat_business_examples').fetchone()['n']==0
