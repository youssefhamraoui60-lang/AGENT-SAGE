import copy
from app.schemas.business import Proposal
from app.services import business_store as store
from app.services.business_rules import evaluate,duplicate_candidates
from app.services.knowledge import retrieve,suspicious
from psycopg.types.json import Jsonb

def context(text):
    with store.connection() as conn:
        rag=retrieve(text,conn)
        examples=conn.execute("SELECT id,original_text,current_extraction FROM requests WHERE status='approved_locally' ORDER BY updated_at DESC LIMIT 3").fetchall()
        return rag,[{'request_id':str(row['id']),'demande':row['original_text'],'proposition':row['current_extraction']}
            for row in examples if not suspicious(row['original_text'])]

def validate(proposal):
    with store.connection() as conn:
        return evaluate(proposal,store.references(conn))

def duplicates(label,kind,limit):
    with store.connection() as conn:
        refs=store.references(conn)
    return {'candidats':duplicate_candidates(label,refs,kind,limit),'scope':'local_only',
        'sage_x3_checked':False,'reference_count':sum(r['kind']==kind for r in refs),
        'avertissement':'Aucun resultat local ne prouve une absence dans Sage X3.'}

def correct(request_id,body):
    with store.connection() as conn:
        row=conn.execute('SELECT * FROM requests WHERE id=%s FOR UPDATE',(request_id,)).fetchone()
        if not row: raise store.NotFound()
        if row['revision']!=body.revision_attendue: raise store.Conflict('stale_revision')
        if row['status'] not in ('pending_approval','needs_clarification'): raise store.Conflict('request_not_editable')
        value=copy.deepcopy(row['current_extraction'])
        for kind,updates in [('articles',body.articles),('fournisseurs',body.fournisseurs)]:
            for update in updates:
                if update.index>=len(value[kind]): raise store.BusinessBlocked('correction_index_out_of_range')
                value[kind][update.index].update(update.champs.model_dump(exclude_unset=True))
        if body.lever_ambiguite:
            value['ambigu']=False
            value['questions']=[]
        proposal=Proposal.model_validate(value)
        evaluation=evaluate(proposal,store.references(conn))
        revision=row['revision']+1
        status='needs_clarification' if proposal.ambigu else 'pending_approval'
        conn.execute('UPDATE requests SET current_extraction=%s,evaluated_result=%s,revision=%s,status=%s,updated_at=now() WHERE id=%s',
            (Jsonb(proposal.model_dump()),Jsonb(evaluation),revision,status,request_id))
        store.event(conn,request_id,'human_correction',body.acteur,revision,
            {'reason':body.raison,'before':row['current_extraction'],'after':proposal.model_dump(),
                'authentication':'local_approval_token','execution_sage_autorisee':False})
        return store.read_request(request_id,conn)

def decide(request_id,body):
    with store.connection() as conn:
        row=conn.execute('SELECT * FROM requests WHERE id=%s FOR UPDATE',(request_id,)).fetchone()
        if not row: raise store.NotFound()
        if row['revision']!=body.revision_attendue: raise store.Conflict('stale_revision')
        if row['status'] not in ('pending_approval','needs_clarification'): raise store.Conflict('request_not_decidable')
        evaluation=(evaluate(Proposal.model_validate(row['current_extraction']),store.references(conn))
            if body.decision=='approve' else row['evaluated_result'])
        if body.decision=='approve' and not evaluation['business_valid']:
            raise store.BusinessBlocked('unresolved_business_checks')
        status='approved_locally' if body.decision=='approve' else 'rejected'
        revision=row['revision']+1
        conn.execute('UPDATE requests SET status=%s,revision=%s,evaluated_result=%s,updated_at=now() WHERE id=%s',
            (status,revision,Jsonb(evaluation),request_id))
        store.event(conn,request_id,'human_decision',body.acteur,revision,
            {'decision':body.decision,'reason':body.raison,'validated_result':row['current_extraction'],
             'authentication':'local_approval_token','execution_sage_autorisee':False})
        return store.read_request(request_id,conn)
