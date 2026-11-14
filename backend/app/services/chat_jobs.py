"""Read-only async analysis workers with PostgreSQL checkpoints and explicit resume.

Workers never call write actions. Process restart loses tasks, not requests or
extracted drafts; a new authenticated resume gets a new attempt token.
"""
import asyncio
import hashlib
import re
from datetime import datetime,timezone
from uuid import uuid4
from fastapi.concurrency import run_in_threadpool
from app.services import conversation_chat as chat,business_store as db,sage_crud as crud

TASKS={}

def interrupt(owner,identifier,job_id,reason,marker=None):
    """Release a stopped read-only analysis, retaining all drafts/checkpoints."""
    with db.connection() as conn:
        try:row=chat.get_row(conn,owner,identifier,True)
        except crud.CrudError as exc:
            if exc.status==404:return
            raise
        state=row['state'];job=state.get('analysis_job',{})
        if job.get('id')!=str(job_id) or job.get('status') in ('completed','failed','interrupted','verification_incomplete') and not state.get('_pending'):return
        if marker and state.get('_pending',{}).get('id')!=marker:return
        state.pop('_pending',None)
        if job.get('status')=='completed':
            chat.save_conversation_context(conn,owner,identifier,state)
            return
        job.update(status='interrupted',phase='interrupted',error_type=job.get('error_type') or reason,recovery_reason=reason,updated_at=datetime.now(timezone.utc).isoformat())
        chat.save_conversation_context(conn,owner,identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
        chat.append(conn,identifier,'assistant','Le traitement n’a pas pu se terminer. Votre demande et les informations déjà reconnues sont conservées. Vous pouvez poursuivre dans le chat. Aucune création n’a été effectuée.',{'error_type':reason,'sage_writes':0})


def status(owner,identifier,job_id):
    value=chat.read(owner,identifier);job=value['state'].get('analysis_job',{})
    if job.get('id')!=str(job_id):raise crud.CrudError('analysis_job_not_found',404)
    active=(str(job_id) in TASKS and not TASKS[str(job_id)].done()) or value['state'].get('_pending',{}).get('id') in chat.ACTIVE_ANALYSES
    if not active and (job.get('status') in ('queued','extracting','extracted','verifying') or value['state'].get('_pending')):
        interrupt(owner,identifier,job_id,'analysis_worker_stopped')
        value=chat.read(owner,identifier);job=value['state']['analysis_job']
    job['worker_active']=active
    job['resumable']=not active and job.get('status')!='completed'
    return {'job':job,'conversation':value}


async def produce(owner,identifier,job_id):
    marker=None
    try:
        with db.connection() as conn:
            row=chat.get_row(conn,owner,identifier)
            job=row['state']['analysis_job']
            marker=row['state'].get('_pending',{}).get('id')
            message=conn.execute('SELECT content FROM chat_messages WHERE conversation_id=%s AND id=%s',(identifier,job['request_message_id'])).fetchone()
            if not message:raise crud.CrudError('original_request_not_found',409)
        from app.core.config import settings
        result=await asyncio.wait_for(chat.send(owner,identifier,message['content'],row['revision'],_job_id=job_id),timeout=settings.chat_analysis_timeout)
        with db.connection() as conn:
            current=chat.get_row(conn,owner,identifier,True);state=current['state']
            if state.get('analysis_job',{}).get('id')==str(job_id):
                state['analysis_job']['performance']=result.get('performance',{})
                chat.save_conversation_context(conn,owner,identifier,state)
    except (Exception,asyncio.CancelledError) as exc:
        # send persists failures/checkpoints; no blind retry and no Sage writes.
        # A crash before send leaves a resumable queued job.
        from app.services.chat_diagnostics import record
        record(exc,'analysis_worker',identifier,job_id)
        # Retry only persistence, never inference or any Sage operation.
        for attempt in range(4):
            try:
                await run_in_threadpool(interrupt,owner,identifier,job_id,'analysis_deadline_exceeded' if isinstance(exc,TimeoutError) else 'analysis_worker_stopped',marker)
                break
            except Exception as persistence_error:
                record(persistence_error,'analysis_recovery_persistence',identifier,job_id)
                if attempt<3:await asyncio.sleep(min(2**attempt,4))


def launch(owner,identifier,job_id):
    key=str(job_id)
    if key in TASKS and not TASKS[key].done():return
    task=asyncio.create_task(produce(owner,identifier,key));TASKS[key]=task
    def done(completed):
        if TASKS.get(key) is completed:TASKS.pop(key,None)
    task.add_done_callback(done)


async def submit(owner,identifier,text,revision,request_id):
    # Preserve the separate existing EXT_POUDRE child workflow. Its capture
    # performs no Sage write and already owns its message/revision transaction.
    # Do not apply that routing to a mixed article/supplier request mentioning sites.
    from app.core.config import settings
    if settings.sage_powershell_chat_enabled:
        current=await run_in_threadpool(chat.read,owner,identifier)
        previous=current['state'].get('analysis_job',{})
        if previous.get('request_id')==str(request_id):
            if previous.get('request_sha256')!=hashlib.sha256(text.encode()).hexdigest():raise crud.CrudError('request_id_content_mismatch',409)
            return await run_in_threadpool(status,owner,identifier,previous['id'])
        from app.services.sage_article_sites import requested_sites
        existing=[a for a in current['state'].get('articles',[]) if a.get('code_article')=='EXT_POUDRE' and (a.get('outcome') or {}).get('confirmed')]
        from app.services.chat_multi_operations import canonical
        mixed_supplier=bool(re.search(r'\bfournisseur\b',canonical(text),re.I))
        if existing and requested_sites(text) is not None and not mixed_supplier:
            result=await chat.send(owner,identifier,text,revision)
            now=datetime.now(timezone.utc).isoformat()
            job={'id':str(uuid4()),'request_id':str(request_id),'request_sha256':hashlib.sha256(text.encode()).hexdigest(),
                 'status':'completed','phase':'article_site_request_captured','created_at':now,'updated_at':now,'sage_writes':0}
            with db.connection() as conn:
                row=chat.get_row(conn,owner,identifier,True)
                if row['revision']!=result['revision']:raise crud.CrudError('stale_site_capture_response',409)
                row['state']['analysis_job']=job;chat.save_conversation_context(conn,owner,identifier,row['state'])
            return await run_in_threadpool(status,owner,identifier,job['id'])
    job=await run_in_threadpool(chat.reserve_analysis,owner,identifier,text,revision,request_id)
    if job['status']=='queued':launch(owner,identifier,job['id'])
    return await run_in_threadpool(status,owner,identifier,job['id'])


async def resume(owner,identifier,job_id,revision):
    current=status(owner,identifier,job_id)
    if current['job']['worker_active']:raise crud.CrudError('analysis_worker_still_running',409)
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True);state=row['state'];job=state.get('analysis_job',{})
        if job.get('id')!=str(job_id):raise crud.CrudError('analysis_job_not_found',404)
        if job.get('status')=='completed':raise crud.CrudError('analysis_already_completed_no_retry',409)
        if row['revision']!=revision:raise crud.CrudError('stale_analysis_revision',409)
        now=datetime.now(timezone.utc).isoformat()
        state['_pending']={'id':str(uuid4()),'at':now}
        job.update(status='queued',phase='queued',updated_at=now)
        chat.save_conversation_context(conn,owner,identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
    launch(owner,identifier,job_id)
    return await run_in_threadpool(status,owner,identifier,job_id)
