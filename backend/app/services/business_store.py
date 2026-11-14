"""Synchronous PostgreSQL access; async API calls dispatch it to a worker thread."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import hashlib
import re
from time import perf_counter
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from app.core.config import settings
from app.services import chat_performance as performance

class TimedCursor(psycopg.Cursor):
    def execute(self,query,params=None,**kwargs):
        start=perf_counter()
        try:return super().execute(query,params,**kwargs)
        finally:
            elapsed=(perf_counter()-start)*1000
            performance.add('pg_query_ms',elapsed)
            performance.add('pg_read_ms' if isinstance(query,str) and query.lstrip().upper().startswith('SELECT') else 'pg_write_ms',elapsed)
            performance.add('pg_queries',1)

class NotFound(Exception): pass
class Conflict(Exception): pass
class BusinessBlocked(Exception): pass

def schema_name():
    name=settings.business_schema
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,62}',name): raise ValueError('Invalid project schema')
    return name

@contextmanager
def connection():
    start=perf_counter()
    with psycopg.connect(settings.database_url,connect_timeout=5,row_factory=dict_row,cursor_factory=TimedCursor) as conn:
        performance.add('pg_connect_ms',(perf_counter()-start)*1000)
        conn.execute('SELECT set_config(\'search_path\', %s, true)',(f'"{schema_name()}",public',))
        from app.services.storage_context import RESERVATION
        reservation=RESERVATION.get()
        if reservation:conn.execute("SELECT set_config('chat.quota_reservation',%s,true)",(str(reservation),))
        yield conn

def migrate():
    script=Path(__file__).resolve().parents[2]/'migrations/003-business.sql'
    body=script.read_text(encoding='utf-8')
    checksum=hashlib.sha256(body.encode()).hexdigest()
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('agent-sage-step2-migration',))
        conn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema_name())))
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())')
        row=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',('003-business',)).fetchone()
        if row:
            if row['sha256']!=checksum: raise ValueError('Applied migration checksum mismatch')
            return False
        conn.execute(body)
        conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('003-business',checksum))
        return True

def references(conn,include_synthetic=False):
    return conn.execute('SELECT * FROM reference_entries WHERE validated=true AND (synthetic=false OR %s) ORDER BY id',
        (include_synthetic or settings.allow_synthetic_references,)).fetchall()

def event(conn,request_id,event_type,actor,revision,payload):
    conn.execute('INSERT INTO request_events(request_id,event_type,actor,revision,payload) VALUES (%s,%s,%s,%s,%s)',
        (request_id,event_type,actor,revision,Jsonb(payload)))

def create_request(text,provenance):
    request_id=uuid4()
    with connection() as conn:
        conn.execute('INSERT INTO requests(id,original_text,provenance,status) VALUES (%s,%s,%s,%s)',
            (request_id,text,Jsonb(provenance),'processing'))
        event(conn,request_id,'received','system',1,{'execution_sage_autorisee':False})
    return request_id

def complete_request(request_id,proposal,evaluation,provenance):
    status='needs_clarification' if proposal['ambigu'] or proposal['intention'] in ('unknown','update_article_request') else 'pending_approval'
    with connection() as conn:
        conn.execute('UPDATE requests SET initial_extraction=%s,current_extraction=%s,evaluated_result=%s,provenance=%s,status=%s,updated_at=now() WHERE id=%s',
            (Jsonb(proposal),Jsonb(proposal),Jsonb(evaluation),Jsonb(provenance),status,request_id))
        event(conn,request_id,'analyzed','system',1,{'proposition':proposal,'controle':evaluation,'provenance':provenance})

def fail_request(request_id,code):
    with connection() as conn:
        conn.execute("UPDATE requests SET status='analysis_failed',updated_at=now() WHERE id=%s",(request_id,))
        event(conn,request_id,'analysis_failed','system',1,{'error_code':code})

def read_request(request_id,conn=None):
    def read(active):
        row=active.execute('SELECT * FROM requests WHERE id=%s',(request_id,)).fetchone()
        if not row: raise NotFound()
        events=active.execute('SELECT event_type,actor,revision,payload,created_at FROM request_events WHERE request_id=%s ORDER BY id',(request_id,)).fetchall()
        return {'id':row['id'],'statut':row['status'],'revision':row['revision'],
            'demande_originale':row['original_text'],'extraction_initiale':row['initial_extraction'],
            'proposition':row['current_extraction'],'controle':row['evaluated_result'],
            'provenance':row['provenance'],'historique':events,'execution_sage_autorisee':False}
    if conn is not None: return read(conn)
    with connection() as active: return read(active)
