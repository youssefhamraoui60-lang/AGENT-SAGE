"""Owner-scoped app storage. DB triggers enforce atomic quotas on every write path."""
import hashlib
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from app.services import business_store as db,sage_crud as crud

LIMIT=200*1024*1024

def migrate():
    from app.services import learning
    with db.connection() as conn:
        learning.ensure(conn)
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('accounts-storage-009',))
        for version in ('009-accounts-storage','010-storage-reservations','011-derived-file-quota','012-shared-methods','013-document-access','014-improvement-loop','015-document-reading','016-modification-audit','017-ai-provider'):
            path=Path(__file__).resolve().parents[2]/('migrations/'+version+'.sql')
            body=path.read_text(encoding='utf-8');sha=hashlib.sha256(body.encode()).hexdigest()
            old=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',(version,)).fetchone()
            if old:
                if old['sha256']!=sha:raise ValueError('Migration checksum mismatch')
                continue
            conn.execute(body)
            if version=='011-derived-file-quota':
                # Preserve existing exports even if an old owner is already over quota.
                # The exclusive table lock and trigger toggle stay in this transaction.
                conn.execute('ALTER TABLE learning_jobs DISABLE TRIGGER chat_storage_quota')
                for job in conn.execute('SELECT id,owner_id,manifest FROM learning_jobs').fetchall():
                    paths=artifact_paths(job['owner_id'],job['manifest'])
                    size=sum(p.stat().st_size for p in paths if p.is_file())
                    conn.execute('UPDATE learning_jobs SET artifact_bytes=%s WHERE id=%s',(size,job['id']))
                conn.execute('ALTER TABLE learning_jobs ENABLE TRIGGER chat_storage_quota')
                recalculate(conn)
            conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',(version,sha))

def status(owner):
    with db.connection() as conn:
        conn.execute('SELECT 1 FROM chat_storage_usage WHERE owner_id=%s FOR UPDATE',(owner,))
        expired=conn.execute("DELETE FROM chat_storage_reservations WHERE owner_id=%s AND created_at<now()-interval '15 minutes' RETURNING bytes",(owner,)).fetchall()
        if expired:conn.execute('UPDATE chat_storage_usage SET reserved_bytes=reserved_bytes-%s WHERE owner_id=%s',(sum(r['bytes'] for r in expired),owner))
        row=conn.execute('SELECT used_bytes,reserved_bytes,limit_bytes FROM chat_storage_usage WHERE owner_id=%s',(owner,)).fetchone() or {'used_bytes':0,'reserved_bytes':0,'limit_bytes':LIMIT}
    used,limit=int(row['used_bytes'])+int(row['reserved_bytes']),int(row['limit_bytes'])
    return {**row,'data_bytes':int(row['used_bytes']),'used_bytes':used,'remaining_bytes':max(0,limit-used),'percent':round(used*100/limit,2),'warning':used*5>=limit*4,'full':used>=limit}

def artifact_paths(owner,manifest):
    from app.core.config import settings
    base=Path(settings.learning_dataset_directory).resolve();paths=[]
    for item in manifest.get('files',{}).values():
        if not item.get('path'):continue
        p=Path(item['path']).resolve()
        if p.is_relative_to(base) and p.relative_to(base).parts[0]==str(owner) and p.name in ('train.jsonl','test.jsonl'):
            paths.append(p)
    if paths:paths.append(paths[0].parent/'manifest.json')
    return list(dict.fromkeys(paths))

def recalculate(conn):
    totals={}
    # Table names are fixed server code, not request input.
    for table in ('chat_conversations','chat_messages','chat_business_examples','learning_items','learning_turns','learning_feedback','learning_jobs','learning_versions','learning_config'):
        extra='+artifact_bytes' if table=='learning_jobs' else ''
        for r in conn.execute('SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,\'UTF8\'))'+extra+') AS size FROM '+table+' t GROUP BY owner_id').fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    for r in conn.execute('SELECT owner_id,sum(octet_length(content)+octet_length(filename)+octet_length(media_type)+128) AS size FROM chat_files GROUP BY owner_id').fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    if conn.execute("SELECT to_regclass('learning_methods') AS name").fetchone()['name']:
        for r in conn.execute("SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,'UTF8'))) AS size FROM learning_methods t GROUP BY owner_id").fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    if conn.execute("SELECT to_regclass('learning_corrections') AS name").fetchone()['name']:
        for table in ('learning_corrections','learning_auto_methods','learning_auto_runs'):
            for r in conn.execute("SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,'UTF8'))) AS size FROM "+table+" t GROUP BY owner_id").fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    if conn.execute("SELECT to_regclass('chat_document_reads') AS name").fetchone()['name']:
        for r in conn.execute("SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,'UTF8'))) AS size FROM chat_document_reads t GROUP BY owner_id").fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    if conn.execute("SELECT to_regclass('chat_modification_audit') AS name").fetchone()['name']:
        for r in conn.execute("SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,'UTF8'))) AS size FROM chat_modification_audit t GROUP BY owner_id").fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    if conn.execute("SELECT to_regclass('chat_ai_usage') AS name").fetchone()['name']:
        for r in conn.execute("SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,'UTF8'))) AS size FROM chat_ai_usage t WHERE owner_id IS NOT NULL GROUP BY owner_id").fetchall():totals[r['owner_id']]=totals.get(r['owner_id'],0)+int(r['size'])
    for owner,size in totals.items():conn.execute('INSERT INTO chat_storage_usage(owner_id,used_bytes) VALUES(%s,%s) ON CONFLICT(owner_id) DO UPDATE SET used_bytes=excluded.used_bytes',(owner,size))

def artifacts(owner,identifier=None,delete=False):
    with db.connection() as conn:
        if identifier is None:return conn.execute('SELECT id,created_at,artifact_bytes AS size_bytes FROM learning_jobs WHERE owner_id=%s AND artifact_bytes>0 ORDER BY created_at DESC',(owner,)).fetchall()
        row=conn.execute('SELECT id,owner_id,manifest,training_performed FROM learning_jobs WHERE id=%s AND owner_id=%s FOR UPDATE',(identifier,owner)).fetchone()
        if not row:raise crud.CrudError('Fichiers introuvables.',404)
        if row['training_performed']:raise crud.CrudError('Ces fichiers font partie d’une version entraînée à conserver.',409)
        if delete:
            for path in artifact_paths(owner,row['manifest']):path.unlink(missing_ok=True)
            conn.execute('DELETE FROM learning_jobs WHERE id=%s AND owner_id=%s',(identifier,owner))

@contextmanager
def execution_space(user,conversation,amount=1024*1024):
    """Reserve result space before any confirmed Sage execution, across its DB commits."""
    if 'email' not in user:yield;return  # Controlled unit-test transports have no account.
    from app.services.storage_context import RESERVATION
    owner=user['owner_id'];identifier=uuid4()
    with db.connection() as conn:
        owned(conn,owner,conversation)
        row=conn.execute('UPDATE chat_storage_usage SET reserved_bytes=reserved_bytes+%s WHERE owner_id=%s AND used_bytes+reserved_bytes+%s<=limit_bytes RETURNING owner_id',(amount,owner,amount)).fetchone()
        if not row:raise HTTPException(507,'Espace insuffisant pour conserver le résultat Sage. Libérez au moins 1 Mo avant de confirmer.')
        conn.execute('INSERT INTO chat_storage_reservations(id,owner_id,bytes) VALUES(%s,%s,%s)',(identifier,owner,amount))
    token=RESERVATION.set(identifier)
    try:yield
    finally:
        RESERVATION.reset(token)
        with db.connection() as conn:
            conn.execute('SELECT 1 FROM chat_storage_usage WHERE owner_id=%s FOR UPDATE',(owner,))
            row=conn.execute('DELETE FROM chat_storage_reservations WHERE id=%s AND owner_id=%s RETURNING bytes',(identifier,owner)).fetchone()
            if row:conn.execute('UPDATE chat_storage_usage SET reserved_bytes=reserved_bytes-%s WHERE owner_id=%s',(row['bytes'],owner))

def owned(conn,owner,conversation,lock=False):
    from app.services.conversation_chat import get_row
    return get_row(conn,owner,conversation,lock)

def files(owner,conversation):
    with db.connection() as conn:
        owned(conn,owner,conversation)
        return conn.execute('SELECT id,filename,media_type,octet_length(content) AS size_bytes,created_at FROM chat_files WHERE owner_id=%s AND conversation_id=%s ORDER BY created_at',(owner,conversation)).fetchall()

def upload(owner,conversation,filename,media_type,data):
    filename=filename.replace('\\','/').split('/')[-1].replace('\x00','').replace('\r','').replace('\n','').strip()[:150]
    if not filename:raise HTTPException(422,'Nom de fichier requis.')
    with db.connection() as conn:
        owned(conn,owner,conversation,True)
        identifier=uuid4()
        conn.execute('INSERT INTO chat_files(id,owner_id,conversation_id,filename,media_type,content) VALUES (%s,%s,%s,%s,%s,%s)',(identifier,owner,conversation,filename,media_type[:100],data))
    return {'id':identifier,'filename':filename,'size_bytes':len(data)}

def file(owner,conversation,identifier,delete=False):
    with db.connection() as conn:
        owned(conn,owner,conversation)
        row=conn.execute('SELECT * FROM chat_files WHERE owner_id=%s AND conversation_id=%s AND id=%s',(owner,conversation,identifier)).fetchone()
        if not row:raise crud.CrudError('Fichier introuvable.',404)
        if delete:conn.execute('DELETE FROM chat_files WHERE owner_id=%s AND id=%s',(owner,identifier))
        return row

def rename(owner,conversation,title):
    with db.connection() as conn:
        owned(conn,owner,conversation,True)
        conn.execute('UPDATE chat_conversations SET title=%s,title_custom=true,revision=revision+1,updated_at=now() WHERE owner_id=%s AND id=%s',(title,owner,conversation))

def delete(owner,conversation):
    with db.connection() as conn:
        row=owned(conn,owner,conversation,True)
        if any((p.get('operation') or {}).get('status')=='executing' for p in row['state'].get('partners',[])+row['state'].get('articles',[])):
            raise crud.CrudError('Une création est en cours. Attendez son résultat avant de supprimer la conversation.',409)
        conn.execute('DELETE FROM chat_conversations WHERE id=%s AND owner_id=%s',(conversation,owner))

def release_failed_analysis(owner,conversation):
    """Quota failures must not leave a pending marker or try to append more data."""
    with db.connection() as conn:
        row=owned(conn,owner,conversation,True);state=row['state'];job=state.get('analysis_job',{})
        state.pop('_pending',None)
        state['analysis_job']={key:job[key] for key in ('id','request_message_id','request_id','request_sha256','created_at') if key in job}
        state['analysis_job'].update(status='failed',error_type='storage_quota_exceeded',phase='storage',checkpoint=None,sage_writes=0)
        conn.execute('UPDATE chat_conversations SET state=%s,revision=revision+1 WHERE id=%s AND owner_id=%s',(Jsonb(state),conversation,owner))
