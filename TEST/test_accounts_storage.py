"""Real isolated PostgreSQL + authenticated API. Sage calls are forbidden."""
import sys,hashlib,secrets
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import pytest,psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.config import settings
from app.services import business_store as db,conversation_chat as chat,chat_storage as storage,chat_auth as auth,supplier_sql
from app.api.chat import router
from app.api.accounts import router as accounts_router
from app.api.learning import router as learning_router

PASSWORD='Test-only-long-password-2026!'

@pytest.fixture
def setup(monkeypatch,tmp_path):
    schema='test_accounts_'+uuid4().hex[:12]
    monkeypatch.setattr(settings,'business_schema',schema)
    monkeypatch.setattr(settings,'learning_dataset_directory',str(tmp_path))
    monkeypatch.setattr(settings,'approval_token',__import__('pydantic').SecretStr('test-csrf-key-not-a-real-secret'))
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',False)
    monkeypatch.setattr(chat,'supplier_security',lambda:{'ready':False})
    monkeypatch.setattr(chat.crud,'security',lambda:{'ready':False})
    def no_sage(*a,**k):raise AssertionError('Sage forbidden in account/quota tests')
    monkeypatch.setattr(supplier_sql,'run',no_sage)
    db.migrate();chat.migrate();storage.migrate()
    app=FastAPI();app.include_router(router);app.include_router(accounts_router);app.include_router(learning_router)
    def client(email=None):
        c=TestClient(app,headers={'Origin':'http://testserver'})
        if email:
            r=c.post('/api/v1/chat/auth/register',json={'email':email,'display_name':'Utilisateur Test','password':PASSWORD})
            assert r.status_code==201,r.text
            c.headers['X-Chat-CSRF']=r.json()['csrf']
        return c
    yield client
    assert schema.startswith('test_accounts_') and len(schema)==26
    with db.connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def create(c):
    r=c.post('/api/v1/chat/conversations');assert r.status_code==200,r.text;return r.json()

def test_registration_login_logout_password_hash_and_restore_history(setup):
    c=setup('first@example.test');s=create(c)
    session=c.get('/api/v1/chat/session').json();owner=UUID(session['user']['id'])
    with db.connection() as conn:encoded=conn.execute('SELECT password_hash FROM chat_accounts WHERE id=%s',(owner,)).fetchone()['password_hash']
    assert encoded.startswith('scrypt$') and PASSWORD not in encoded
    cookie=c.cookies.get(auth.COOKIE)
    assert c.post('/api/v1/chat/auth/logout').status_code==200
    assert c.get('/api/v1/chat/conversations').status_code==401
    assert c.get('/api/v1/chat/conversations',headers={'Cookie':auth.COOKIE+'='+cookie}).status_code==401
    r=c.post('/api/v1/chat/auth/login',json={'email':'FIRST@example.test','password':PASSWORD})
    assert r.status_code==200 and r.json()['user']['id']==str(owner)
    assert c.cookies.get(auth.COOKIE)!=cookie
    c.headers['X-Chat-CSRF']=r.json()['csrf']
    assert c.get('/api/v1/chat/conversations').json()['conversations'][0]['id']==s['id']
    assert c.get('/api/v1/chat/conversations/'+s['id']).status_code==200

def test_isolation_for_history_search_files_memory_and_mutations(setup):
    a=setup('a@example.test');b=setup('b@example.test');s=create(a);path='/api/v1/chat/conversations/'+s['id']
    assert a.patch(path,json={'title':'Dossier privé Alpha'}).status_code==200
    f=a.post(path+'/files?filename=preuve.txt',content=b'private',headers={'Content-Type':'text/plain'}).json()
    assert b.get('/api/v1/chat/conversations?q=Alpha').json()['conversations']==[]
    for response in [b.get(path),b.patch(path,json={'title':'Vol'}),b.delete(path),b.get(path+'/files'),b.get(path+'/files/'+f['id']),b.delete(path+'/files/'+f['id']),b.post(path+'/files?filename=vol.txt',content=b'x'),b.patch(path+'/partners/'+str(uuid4()),json={'revision':1,'fields':{'nom':'Vol'}})]:assert response.status_code==404,response.text
    item=a.post('/api/v1/chat/learning/items',json={'kind':'rule','title':'Privé','content':'Toujours relire les paramètres du fournisseur.'}).json()
    assert b.post('/api/v1/chat/learning/items/'+item['id']+'/review',json={'status':'validated','confirm':True}).status_code==404
    assert a.get(path).json()['title']=='Dossier privé Alpha'

def test_csrf_origin_and_role_cannot_be_supplied_by_client(setup):
    guest=setup();assert guest.post('/api/v1/chat/session').status_code==401
    assert guest.post('/api/v1/chat/auth/register',json={'email':'x@example.test','display_name':'Nom','password':PASSWORD,'role':'operator'}).status_code==422
    a=setup('csrf@example.test')
    assert a.post('/api/v1/chat/conversations',headers={'X-Chat-CSRF':'wrong'}).status_code==403
    assert a.post('/api/v1/chat/conversations',headers={'Origin':'https://evil.test'}).status_code==403
    assert guest.post('/api/v1/chat/auth/login',headers={'Origin':'https://REDACTED_CONFIGURE_LOCALLY@example.test','password':PASSWORD}).status_code==403

def test_warning_exact_full_rejection_and_deletion_release_space(setup):
    c=setup('quota@example.test');s=create(c);path='/api/v1/chat/conversations/'+s['id'];owner=UUID(c.get('/api/v1/chat/session').json()['user']['id'])
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=20000 WHERE owner_id=%s',(owner,))
    used=c.get('/api/v1/chat/storage').json()['used_bytes']
    size=16000-used-len('first.txt')-len('text/plain')-128
    assert c.post(path+'/files?filename=first.txt',content=b'a'*size,headers={'Content-Type':'text/plain'}).status_code==201
    usage=c.get('/api/v1/chat/storage').json();assert usage['used_bytes']==16000 and usage['warning'] and not usage['full']
    remaining=usage['remaining_bytes']-len('last.txt')-len('text/plain')-128
    last=c.post(path+'/files?filename=last.txt',content=b'b'*remaining,headers={'Content-Type':'text/plain'});assert last.status_code==201,last.text
    assert c.get('/api/v1/chat/storage').json()['full']
    assert c.post('/api/v1/chat/conversations').status_code==507
    assert c.post(path+'/files?filename=extra',content=b'x').status_code==507
    assert c.get(path).status_code==200
    assert c.delete(path+'/files/'+last.json()['id']).status_code==200
    assert not c.get('/api/v1/chat/storage').json()['full']
    assert c.delete(path).status_code==200
    assert c.get('/api/v1/chat/storage').json()['used_bytes']==0

def test_quota_counts_drafts_and_is_atomic_under_concurrent_uploads(setup):
    c=setup('atomic@example.test');s=create(c);owner=UUID(c.get('/api/v1/chat/session').json()['user']['id'])
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=14000 WHERE owner_id=%s',(owner,))
    before=storage.status(owner)['used_bytes']
    with pytest.raises(psycopg.Error) as exc:
        with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb({'draft':'x'*20000}),UUID(s['id'])))
    assert exc.value.sqlstate=='P2001' and storage.status(owner)['used_bytes']==before
    def upload(index):
        try:storage.upload(owner,UUID(s['id']),str(index)+'.txt','text/plain',b'x'*8000);return True
        except psycopg.Error as exc:assert exc.sqlstate=='P2001';return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(upload,[1,2]))
    assert sum(results)==1 and storage.status(owner)['used_bytes']<=14000

def test_only_valid_legacy_browser_can_adopt_its_own_history(setup):
    c=setup();owner=uuid4();token=secrets.token_urlsafe(32)
    with db.connection() as conn:conn.execute('INSERT INTO chat_web_sessions(token_hash,owner_id,role,expires_at) VALUES(%s,%s,%s,%s)',(hashlib.sha256(token.encode()).hexdigest(),owner,'operator',datetime.now(timezone.utc)+timedelta(days=1)))
    s=chat.create(owner)
    c.cookies.set(auth.COOKIE,token,path='/api/v1/chat')
    assert c.get('/api/v1/chat/session').status_code==401
    r=c.post('/api/v1/chat/auth/register',json={'email':'legacy@example.test','display_name':'Ancien utilisateur','password':PASSWORD})
    assert r.status_code==201,r.text
    assert r.json()['user']['id']==str(owner)
    assert c.get('/api/v1/chat/conversations/'+str(s['id'])).status_code==200
    other=setup('other@example.test');assert other.get('/api/v1/chat/conversations/'+str(s['id'])).status_code==404

def test_login_failures_are_limited_and_invalid_credentials_generic(setup):
    c=setup('limit@example.test')
    for _ in range(10):assert c.post('/api/v1/chat/auth/login',json={'email':'limit@example.test','password':'wrong-password'}).status_code==401
    assert c.post('/api/v1/chat/auth/login',json={'email':'limit@example.test','password':PASSWORD}).status_code==429

def test_file_download_is_attachment_and_owner_private(setup):
    c=setup('file@example.test');s=create(c);path='/api/v1/chat/conversations/'+s['id']
    r=c.post(path+'/files?filename=../../note.html',content=b'<script>alert(1)</script>',headers={'Content-Type':'text/html'})
    assert r.status_code==201,r.text
    value=c.get(path+'/files/'+r.json()['id'])
    assert value.headers['content-disposition'].startswith('attachment;') and value.headers['x-content-type-options']=='nosniff'
    assert value.headers['content-type']=='application/octet-stream'

def test_result_reservation_cannot_be_consumed_by_other_writes(setup):
    c=setup('reserve@example.test');s=create(c);owner=UUID(c.get('/api/v1/chat/session').json()['user']['id'])
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=20000 WHERE owner_id=%s',(owner,))
    before=storage.status(owner)['used_bytes']
    with storage.execution_space({'owner_id':owner,'email':'reserve@example.test'},UUID(s['id']),8000):
        assert storage.status(owner)['reserved_bytes']==8000
        def other_write():
            with pytest.raises(psycopg.Error) as exc:storage.upload(owner,UUID(s['id']),'too-big.txt','text/plain',b'x'*14000)
            assert exc.value.sqlstate=='P2001'
        with ThreadPoolExecutor(max_workers=1) as pool:pool.submit(other_write).result()
        storage.upload(owner,UUID(s['id']),'result.txt','text/plain',b'x'*6000)
        assert storage.status(owner)['reserved_bytes']<8000
    after=storage.status(owner)
    assert after['reserved_bytes']==0 and after['used_bytes']>before and after['used_bytes']<=20000

def test_quota_failure_releases_analysis_pending_marker(setup):
    c=setup('pending@example.test');s=create(c);owner=UUID(c.get('/api/v1/chat/session').json()['user']['id'])
    state={'articles':[],'partners':[{'id':str(uuid4()),'kind':'supplier','nom':'Conservé'}], '_pending':{'id':'test-pending'},'analysis_job':{'id':str(uuid4()),'request_message_id':42,'status':'extracting','delta':'x'*5000}}
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(state),UUID(s['id'])))
    usage=storage.status(owner)
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=%s WHERE owner_id=%s',(usage['used_bytes'],owner))
    storage.release_failed_analysis(owner,UUID(s['id']))
    value=c.get('/api/v1/chat/conversations/'+s['id']).json()
    assert '_pending' not in value['state'] and value['state']['partners'][0]['nom']=='Conservé'
    assert value['state']['analysis_job']['error_type']=='storage_quota_exceeded'
    assert value['state']['analysis_job']['request_message_id']==42

def test_prepared_files_are_counted_owner_scoped_and_deletable(setup):
    c=setup('prepared@example.test');owner=UUID(c.get('/api/v1/chat/session').json()['user']['id']);other=setup('other-files@example.test')
    identifier=uuid4();folder=Path(settings.learning_dataset_directory)/str(owner)/'test-hash';folder.mkdir(parents=True)
    path=folder/'train.jsonl';path.write_bytes(b'x'*512)
    before=storage.status(owner)['used_bytes']
    with db.connection() as conn:conn.execute('INSERT INTO learning_jobs(id,owner_id,dataset_sha,manifest,status,artifact_bytes) VALUES(%s,%s,%s,%s,%s,%s)',(identifier,owner,'test-hash',Jsonb({'files':{'train':{'path':str(path)}}}),'blocked_training_environment',512))
    assert storage.status(owner)['used_bytes']>=before+512
    assert c.get('/api/v1/chat/storage/prepared-files').json()['files'][0]['id']==str(identifier)
    assert other.delete('/api/v1/chat/storage/prepared-files/'+str(identifier)).status_code==404 and path.is_file()
    assert c.delete('/api/v1/chat/storage/prepared-files/'+str(identifier)).status_code==200
    assert not path.exists() and storage.status(owner)['used_bytes']==before

def test_full_quota_cannot_be_bypassed_by_exporting_files(setup,monkeypatch):
    from app.services import learning_training
    monkeypatch.setattr(learning_training,'capability',lambda:{'model':'test-qwen','digest':'test','missing':[]})
    c=setup('export-full@example.test');s=create(c);owner=UUID(c.get('/api/v1/chat/session').json()['user']['id']);usage=storage.status(owner)
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=%s WHERE owner_id=%s',(usage['used_bytes'],owner))
    response=c.post('/api/v1/chat/learning/export')
    assert response.status_code==507,response.text
    assert not list(Path(settings.learning_dataset_directory).rglob('*.jsonl'))
