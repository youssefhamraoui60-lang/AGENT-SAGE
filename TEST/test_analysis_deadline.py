import asyncio
from contextlib import contextmanager
from copy import deepcopy
from uuid import uuid4
import pytest
from test_supplier_nova import parsed as unused
from app.services import chat_jobs as jobs

@pytest.fixture
def worker(monkeypatch):
    owner=uuid4();identifier=uuid4();jobid=str(uuid4());messages=[]
    record={'revision':1,'state':{'partners':[{'id':'draft','kind':'supplier','nom':'Conservé','ice':'012345678901234'}],
      '_pending':{'id':'attempt'},'analysis_job':{'id':jobid,'status':'extracting','request_message_id':7,'checkpoint':'extracted','delta':{'intent':'new'}}}}
    class Connection:
        def execute(self,query,args):
            if query.startswith('UPDATE'):record['revision']+=1
            return self
        def fetchone(self):return {'content':'demande conservée'}
    @contextmanager
    def connection():yield Connection()
    monkeypatch.setattr(jobs.db,'connection',connection)
    monkeypatch.setattr(jobs.chat,'read',lambda *a:deepcopy(record))
    monkeypatch.setattr(jobs.chat,'get_row',lambda *a:deepcopy(record))
    monkeypatch.setattr(jobs.chat,'save_conversation_context',lambda c,o,i,s:record.update(state=deepcopy(s)))
    monkeypatch.setattr(jobs.chat,'append',lambda *a:messages.append(a))
    monkeypatch.setattr(jobs,'TASKS',{})
    monkeypatch.setattr(jobs.chat,'ACTIVE_ANALYSES',set())
    return owner,identifier,jobid,record,messages

def test_orphan_worker_releases_ui_once_and_preserves_checkpoint(worker):
    owner,identifier,jobid,record,messages=worker
    result=jobs.status(owner,identifier,jobid)
    assert result['job']['status']=='interrupted' and result['job']['resumable']
    assert '_pending' not in record['state']
    assert record['state']['partners'][0]['ice']=='012345678901234'
    assert result['job']['checkpoint']=='extracted' and result['job']['delta']=={'intent':'new'}
    jobs.status(owner,identifier,jobid)
    assert len(messages)==1 and record['revision']==2

def test_running_worker_is_not_marked_orphan(worker):
    owner,identifier,jobid,record,messages=worker
    jobs.chat.ACTIVE_ANALYSES.add('attempt')
    assert jobs.status(owner,identifier,jobid)['job']['worker_active']
    assert '_pending' in record['state'] and not messages

def test_timeout_is_terminal_and_preserves_draft(worker,monkeypatch):
    from app.core.config import settings
    owner,identifier,jobid,record,messages=worker
    async def stalled(*a,**k):await asyncio.sleep(60)
    monkeypatch.setattr(jobs.chat,'send',stalled)
    monkeypatch.setattr(settings,'chat_analysis_timeout',.01)
    asyncio.run(jobs.produce(owner,identifier,jobid))
    assert record['state']['analysis_job']['error_type']=='analysis_deadline_exceeded'
    assert '_pending' not in record['state'] and len(messages)==1
    assert record['state']['partners'][0]['nom']=='Conservé'

def test_old_attempt_cannot_interrupt_new_attempt(worker):
    owner,identifier,jobid,record,messages=worker
    jobs.interrupt(owner,identifier,jobid,'old_worker','different-attempt')
    assert '_pending' in record['state'] and not messages

def test_failed_checkpoint_cannot_leave_send_locked(worker):
    owner,identifier,jobid,record,messages=worker
    record['state']['analysis_job'].update(status='failed',error_type='ValidationError')
    result=jobs.status(owner,identifier,jobid)
    assert '_pending' not in record['state']
    assert result['job']['error_type']=='ValidationError' and len(messages)==1

def test_postgresql_outage_retries_only_checkpoint_persistence(worker,monkeypatch):
    owner,identifier,jobid,record,messages=worker
    from psycopg import OperationalError
    attempts=[];inference=[]
    async def fail_once(*a,**kw):
        inference.append(1)
        raise OperationalError('simulated DB disconnect')
    original=jobs.interrupt
    def unavailable_then_restore(*a,**kw):
        attempts.append(1)
        if len(attempts)<3:raise OperationalError('simulated temporary outage')
        return original(*a,**kw)
    monkeypatch.setattr(jobs.chat,'send',fail_once)
    monkeypatch.setattr(jobs,'interrupt',unavailable_then_restore)
    asyncio.run(jobs.produce(owner,identifier,jobid))
    assert len(inference)==1 and len(attempts)==3
    assert '_pending' not in record['state'] and len(messages)==1
    assert record['state']['partners'][0]['ice']=='012345678901234'

def test_complete_postgresql_outage_recovers_on_next_status(worker,monkeypatch):
    owner,identifier,jobid,record,messages=worker
    from psycopg import OperationalError
    original=jobs.db.connection
    def unavailable():raise OperationalError('simulated database offline')
    monkeypatch.setattr(jobs.db,'connection',unavailable)
    with pytest.raises(OperationalError):jobs.status(owner,identifier,jobid)
    assert record['state']['_pending'] and not messages
    monkeypatch.setattr(jobs.db,'connection',original)
    jobs.status(owner,identifier,jobid)
    assert '_pending' not in record['state'] and len(messages)==1
