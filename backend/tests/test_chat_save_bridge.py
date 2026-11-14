"""Native service values -> persisted chat results. ERP/SQL writes are mocked."""
import json,os
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from test_conversation_chat import fixture,create,send
from app.services import conversation_chat as chat
pytestmark=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Explicit isolated local PostgreSQL tests')

@pytest.mark.parametrize('status,confirmed,phrase',[('succeeded',True,'Création confirmée'),('succeeded',False,'Création non confirmée'),('ambiguous',False,'Création non confirmée'),('failed',False,'Création refusée')])
def test_chat_preserves_native_operation_and_reports_verified_outcome(fixture,monkeypatch,status,confirmed,phrase):
    # Compatibility bridge unit test. New non-demo articles use the strict
    # general lifecycle, covered independently by test_cpj345_creation.
    from app.services import article_execution
    monkeypatch.setattr(article_execution,'legacy_scope',lambda article:True)
    client,queue=fixture
    value=send(client,queue,create(client),'Crée un article Ciment test, code article SYNTH001, catégorie NEG, unité M2, site 201.',{'intent':'new','shared':{'code_article':'SYNTH001','categorie':'NEG','unite':'M2','site':'201'},'articles':[{'designation':'Ciment test'}]})
    article=value['state']['articles'][0];identifier=article['id']
    monkeypatch.setattr(chat.crud,'security',lambda *a,**k:{'ready':True,'folder':'TEST','blockers':[]})
    operation={'id':uuid4(),'created_at':datetime.now(timezone.utc),'status':'prepared','digest':'a'*64,'amount_for_precision_test':Decimal('1.234567890123456789')}
    for method in ['create','update','validate']:monkeypatch.setattr(chat.legacy,method,lambda *a,**k:None)
    monkeypatch.setattr(chat.legacy,'prepare',lambda *a,**k:{'operation':operation})
    monkeypatch.setattr(chat.legacy,'read',lambda *a,**k:{'revision':2,'operation':operation})
    nonce='SERVER_ONLY_SYNTHETIC_NONCE'
    monkeypatch.setattr(chat.legacy,'approve',lambda *a,**k:{'approval_token':nonce})
    calls=[]
    def execute(*args):
        calls.append(args)
        return {'operation':{**operation,'status':status,'after_record':{'exists':True}},'outcome':{'confirmed':confirmed,'retry_allowed':False,'sql_readback':{'ok':confirmed,'folder':'TEST','article':[{'ITMREF_0':'SYNTH001'}] if confirmed else []},'comparisons':dict.fromkeys(['code','label','category','stock','purchase','sales'],confirmed)}}
    monkeypatch.setattr(chat.legacy,'execute',execute)
    prefix=f"/api/v1/chat/conversations/{value['id']}/articles/{identifier}/"
    response=client.post(prefix+'review',json={'revision':value['revision'],'confirm':True});assert response.status_code==200,response.text
    response=client.post(prefix+'prepare',json={'revision':value['revision']});assert response.status_code==200,response.text
    prepared=response.json();assert prepared['state']['articles'][0]['operation']['id']==str(operation['id'])
    assert prepared['state']['articles'][0]['operation']['amount_for_precision_test']=='1.234567890123456789'
    response=client.post(prefix+'approve',json={'revision':value['revision'],'confirm':True});assert response.status_code==200,response.text
    assert nonce not in response.text
    response=client.post(prefix+'execute',json={'revision':value['revision'],'confirm':True});assert response.status_code==200,response.text
    result=response.json();assert result['state']['articles'][0]['outcome']['confirmed'] is confirmed
    assert phrase in [m for m in result['messages'] if m['role']=='assistant'][-1]['content']
    assert nonce not in json.dumps(result)
    for action in ['prepare','approve','execute']:
        response=client.post(prefix+action,json={'revision':value['revision'],'confirm':True})
        assert response.status_code==409,response.text
    assert len(calls)==1

def test_pending_analysis_blocks_review_and_write_bridge(fixture,monkeypatch):
    client,_=fixture;value=create(client)
    with chat.db.connection() as conn:
        row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(value['id'],)).fetchone()
        row['state']['_pending']={'id':'synthetic'}
        chat.save_conversation_context(conn,row['owner_id'],value['id'],row['state'])
    for action in ['review','prepare','approve','execute']:
        response=client.post(f"/api/v1/chat/conversations/{value['id']}/articles/{uuid4()}/{action}",json={'revision':value['revision'],'confirm':True})
        assert response.status_code==409 and response.json()['detail']=='analysis_in_progress'
