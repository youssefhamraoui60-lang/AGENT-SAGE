import os
from copy import deepcopy
from uuid import uuid4
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from app.core.config import settings
from app.services import sage_article_sites as sites, conversation_chat as chat,business_store as db
from app.services.sage_crud import CrudError


def test_multisite_request_is_separate_from_article_edit():
    assert sites.requested_sites('crrer le cette article dnas le article site 202 ET 201')==['201','202']
    assert sites.requested_sites('article-site tous les sites Ould Bouazza')=='all'
    assert sites.requested_sites('le site 201') is None


@pytest.fixture
def workflow(monkeypatch):
    if os.environ.get('RUN_STEP2_INTEGRATION')!='1':pytest.skip('Isolated local DB required')
    schema='article_sites_'+uuid4().hex[:12]
    monkeypatch.setattr(settings,'business_schema',schema)
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    db.migrate();chat.migrate();owner=uuid4();session=chat.create(owner)
    parent={'id':str(uuid4()),'code_article':'EXT_POUDRE','site':'201','designation':'Extincteur à poudre',
        'operation':{'id':'master-id','status':'succeeded','transport':'PowerShell 5.1'},'outcome':{'confirmed':True}}
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',
        (Jsonb({'articles':[parent]}),session['id']))
    monkeypatch.setattr(sites,'catalog',lambda:[{'site':s,'company':'20','name':s} for s in ('201','202','209')])
    calls=[]
    def worker(code,site,mode,**kw):
        calls.append((code,site,mode))
        return {'Code':code,'Site':site,'Digest':'digest-'+site,'DescriptionHash':'desc','Exists':False,
            'ObjectXml':'<PARAM/>','ReadConfirmed':True,'SaveStatus':1,'ReadStatus':1,'State':'CREATED_AND_READ_BACK'}
    monkeypatch.setattr(sites,'worker',worker)
    yield owner,session,parent,calls
    sites.PERMITS.clear()
    with db.connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def capture(workflow,text='créer les article-site 202 et 201'):
    owner,session,parent,calls=workflow
    return sites.capture(owner,session['id'],text,session['revision'])


def act(workflow,value,kind,confirm=False):
    owner,session,parent,calls=workflow
    return sites.action(owner,session['id'],parent['id'],kind,value['revision'],confirm)


def test_created_parent_preserved_and_sites_need_specific_approval(workflow):
    value=capture(workflow)
    a=value['state']['articles'][0]
    assert a['site']=='201' and a['operation']==workflow[2]['operation'] and a['outcome']==workflow[2]['outcome']
    assert a['site_request']['sites']==['201','202'] and workflow[3]==[]
    value=act(workflow,value,'site-prepare')
    with pytest.raises(CrudError):act(workflow,value,'site-execute',True)
    with pytest.raises(CrudError):act(workflow,value,'site-approve',False)
    value=act(workflow,value,'site-approve',True)
    value=act(workflow,value,'site-execute',True)
    assert value['state']['articles'][0]['site_request']['status']=='succeeded'
    assert [c[1] for c in workflow[3] if c[2]=='execute']==['201','202']
    with pytest.raises(CrudError):act(workflow,value,'site-execute',True)
    assert value['state']['articles'][0]['operation']==workflow[2]['operation']


def test_all_sites_excludes_other_company(workflow):
    value=capture(workflow,'article-site tous')
    assert value['state']['articles'][0]['site_request']['sites']==['201','202','209']


def test_other_company_site_is_rejected(workflow):
    with pytest.raises(CrudError,match='sites_not_in'):capture(workflow,'article-site 301')


def test_uncertainty_stops_other_sites_and_forbids_retry(workflow,monkeypatch):
    value=capture(workflow);value=act(workflow,value,'site-prepare');value=act(workflow,value,'site-approve',True)
    def uncertain(code,site,mode,**kw):workflow[3].append((code,site,mode));raise TimeoutError()
    monkeypatch.setattr(sites,'worker',uncertain)
    value=act(workflow,value,'site-execute',True)
    req=value['state']['articles'][0]['site_request']
    assert req['status']=='ambiguous' and req['results']['202']['SaveAttempts']==0
    with pytest.raises(CrudError):act(workflow,value,'site-execute',True)


def test_real_stream_route_captures_sites_before_model(workflow,monkeypatch):
    import json,hashlib
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import chat_auth
    owner,session,parent,calls=workflow
    async def forbidden(*args,**kwargs):raise AssertionError('Site request must bypass model and master editing')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    c=TestClient(app);c.headers['Origin']='http://testserver'
    bootstrap=c.post('/api/v1/chat/session')
    assert bootstrap.status_code==200
    cookie=c.cookies.get(chat_auth.COOKIE)
    with db.connection() as conn:
        conn.execute('UPDATE chat_web_sessions SET owner_id=%s WHERE token_hash=%s',
                     (owner,hashlib.sha256(cookie.encode()).hexdigest()))
    c.headers['X-Chat-CSRF']=bootstrap.json()['csrf']
    r=c.post('/api/v1/chat/conversations/'+str(session['id'])+'/messages/stream',
        json={'content':'crrer le cette article dnas le article site 202 ET 201','revision':session['revision']})
    assert r.status_code==200
    events=[json.loads(block[6:]) for block in r.text.strip().split('\n\n') if block.startswith('data: ')]
    assert not any(e['event']=='error' for e in events),events
    result=next(e['data'] for e in events if e['event']=='result')
    a=result['state']['articles'][0]
    assert a['site_request']['sites']==['201','202']
    assert a['operation']==parent['operation'] and calls==[]
