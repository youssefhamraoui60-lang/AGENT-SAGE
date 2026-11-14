"""Explicit enterprise membership and independent review; never shares conversations."""
import re
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.services import business_store as db,learning,sage_crud as crud

def member(conn,owner,company,review=False):
    row=conn.execute("SELECT role FROM learning_memberships WHERE owner_id=%s AND company_id=%s AND folder='TEST' AND active=true",(owner,company)).fetchone()
    if not row or review and row['role']!='reviewer':raise crud.CrudError('Acces entreprise non autorise.',403)

def propose(owner,company,title,content):
    title=learning.clean(title);content=learning.clean(content)
    # Shared content is a human-written procedure, never an imported private turn.
    combined=title+'\n'+content
    if learning.INJECTION.search(combined) or learning.VOLATILE.search(combined) or re.search(r'\d{5,}|@|\bF\d{3,}\b|\b(?:ICE|IF|RC|nom|adresse|telephone)\s*[:=]',combined,re.I):
        raise crud.CrudError('Retirez les donnees personnelles et les valeurs Sage de la methode.',422)
    with db.connection() as conn:
        member(conn,owner,company)
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(str(company)+title,))
        version=conn.execute('SELECT COALESCE(max(version),0)+1 AS n FROM learning_methods WHERE company_id=%s AND title=%s',(company,title)).fetchone()['n']
        return conn.execute("INSERT INTO learning_methods(id,company_id,folder,owner_id,title,content,version) VALUES(%s,%s,'TEST',%s,%s,%s,%s) RETURNING *",(uuid4(),company,owner,title,content,version)).fetchone()

def review(owner,identifier,activate=False,evaluation=None):
    with db.connection() as conn:
        row=conn.execute('SELECT * FROM learning_methods WHERE id=%s FOR UPDATE',(identifier,)).fetchone()
        if not row:raise crud.CrudError('Methode introuvable.',404)
        member(conn,owner,row['company_id'],True)
        evaluation=evaluation or {}
        if activate:
            if row['owner_id']==owner:raise crud.CrudError('Une relecture independante est requise.',409)
            if evaluation.get('passed') is not True or not evaluation.get('suite') or not isinstance(evaluation.get('case_count'),int) or evaluation['case_count']<1:
                raise crud.CrudError('Evaluation independante requise avant activation.',422)
            conn.execute("UPDATE learning_methods SET status='disabled' WHERE company_id=%s AND title=%s AND folder='TEST' AND status='active'",(row['company_id'],row['title']))
        return conn.execute('UPDATE learning_methods SET status=%s,reviewed_by=%s,reviewed_at=now(),evaluation=%s WHERE id=%s RETURNING *',('active' if activate else 'disabled',owner,Jsonb(evaluation),identifier)).fetchone()

def retrieve(conn,owner,text):
    if not conn.execute("SELECT to_regclass('learning_methods') AS name").fetchone()['name']:return []
    return conn.execute("""SELECT x.id,x.title,x.content,x.version,x.source,x.created_at AS source_date,
      x.reviewed_at AS validated_at,'validated' AS status,'company_method' AS kind
      FROM learning_methods x JOIN learning_memberships m ON m.company_id=x.company_id AND m.folder=x.folder
      WHERE m.owner_id=%s AND m.active=true AND x.status='active' AND x.folder='TEST'
      AND to_tsvector('french',x.content) @@ plainto_tsquery('french',%s) LIMIT 3""",(owner,text)).fetchall()
