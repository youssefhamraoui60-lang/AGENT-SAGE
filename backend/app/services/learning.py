"""Persistent owner-scoped TEST knowledge. No Sage connector, no write permits."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID,uuid4
from difflib import SequenceMatcher
from psycopg.types.json import Jsonb
from app.services import business_store as db,sage_crud as crud
from app.core.config import settings
from fastapi.encoders import jsonable_encoder

ROOT=Path(__file__).resolve().parents[3]
DOCUMENT_ACCESS="""EXISTS(SELECT 1 FROM learning_document_access a WHERE a.document_id=d.id AND a.folder='TEST'
 AND (a.owner_id=%s OR EXISTS(SELECT 1 FROM learning_memberships m WHERE m.owner_id=%s AND m.active=true AND m.company_id=a.company_id AND m.folder=a.folder)))"""
SECRET=re.compile(r'''(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:password|passwd|pwd|mot\s+de\s+passe|api[_ -]?key|secret|authorization|bearer|token)["']?\s*(?:[:=]|\best\b|\bis\b)\s*\S+|\bBearer\s+\S+|\b(?:sk-|ghp_)[a-z0-9_-]{12,}|\bAKIA[A-Z0-9]{16}|\beyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+|[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s@]+@''')
VOLATILE=re.compile(r'\b(stock|stocks|solde|soldes|disponible|disponibles|disponibilit[eé]|num[eé]ro\s+suivant|code\s+libre)\b|\bcodes?\b.{0,50}\b(existe|utilis[eé]|libre)\b',re.I)
INJECTION=re.compile(r'ignore.{0,35}(instruction|r[eè]gle|system)|system\s*prompt|<\|(?:system|im_start)|autorise.{0,30}(sans confirmation|production)',re.I)

def clean(text):
    if not isinstance(text,str) or not text.strip() or len(text)>20000:raise crud.CrudError('Contenu vide ou trop long.',422)
    if SECRET.search(text):raise crud.CrudError('Ce contenu contient un secret et ne peut pas être mémorisé.',422)
    return text.strip()

def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def normalized(value):return ' '.join(value.casefold().split())
def excerpt(content,query):
    positions=[content.casefold().find(word) for word in re.findall(r'\w{3,}',query.casefold())]
    found=[p for p in positions if p>=0];start=max(0,min(found)-200) if found else 0
    return content[start:start+1400]

def ensure(conn):
    if conn.execute("SELECT to_regclass('learning_items') AS name").fetchone()['name']:return
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':learning-008'))")
    if conn.execute("SELECT to_regclass('learning_items') AS name").fetchone()['name']:return
    body=(ROOT/'backend/migrations/008-learning.sql').read_text(encoding='utf-8')
    conn.execute(body)
    conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('008-learning',digest(body)))

def create_item(owner,kind,title,content,source='user',payload=None):
    title=clean(title);content=clean(content);source=clean(source)
    if kind not in ('preference','rule','correction','document','example'):raise crud.CrudError('Type de mémoire invalide.',422)
    if INJECTION.search(content):raise crud.CrudError('Ce contenu tente de modifier les contrôles de sécurité.',422)
    if kind!='document' and VOLATILE.search(content):raise crud.CrudError('Les stocks, soldes et codes disponibles doivent être consultés en direct, pas mémorisés comme des faits.',422)
    payload=payload or {};clean(json.dumps(payload,ensure_ascii=False))
    if payload.get('expected_delta') is not None:
        from app.services.chat_model import Delta
        payload['expected_delta']=Delta.model_validate(payload['expected_delta']).model_dump(exclude_none=True,exclude_unset=True)
    with db.connection() as conn:
        ensure(conn);identifier=uuid4()
        row=conn.execute('''INSERT INTO learning_items(id,owner_id,kind,title,content,source,payload,sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner_id,kind,sha256) DO UPDATE SET title=learning_items.title RETURNING *''',
            (identifier,owner,kind,title,content,source,Jsonb(payload),digest(normalized(content)))).fetchone()
    return row

def review(owner,identifier,status):
    if status not in ('validated','rejected','superseded'):raise crud.CrudError('Décision invalide.',422)
    with db.connection() as conn:
        ensure(conn)
        row=conn.execute('UPDATE learning_items SET status=%s,validated_at=now(),validated_by=%s WHERE id=%s AND owner_id=%s RETURNING *',
                         (status,owner,identifier,owner)).fetchone()
        if not row:raise crud.CrudError('Mémoire introuvable.',404)
    return row

def retrieve(owner,text):
    query=clean(text)
    search=re.sub(r'\b(comment|quel|quels|quelle|quelles|bonjour|merci|explique|expliquer|voudrais|souhaite|puis|peux)\b',' ',query,flags=re.I)
    with db.connection() as conn:
        ensure(conn)
        rows=conn.execute('''SELECT id,kind,title,content,source,source_date,status,validated_at,payload,sha256,
            ts_rank_cd(to_tsvector('french',content),plainto_tsquery('french',%s)) AS score
            FROM learning_items WHERE owner_id=%s AND folder='TEST' AND status='validated'
            AND (kind='preference' OR to_tsvector('french',content) @@ plainto_tsquery('french',%s)
                OR payload->>'input_normalized'=%s)
            ORDER BY score DESC,validated_at DESC LIMIT 8''',(search,owner,search,normalized(query))).fetchall()
        from app.services.learning_methods import retrieve as shared_retrieve
        methods=shared_retrieve(conn,owner,search)
        from app.services.learning_auto import retrieve as automatic_retrieve
        methods+=automatic_retrieve(conn,owner,query)
        # Existing reviewed documents retain their original provenance and index date.
        legacy=conn.execute('''SELECT p.content,d.source_path AS source,d.indexed_at AS source_date,d.reviewed,
            d.sha256 FROM knowledge_passages p JOIN knowledge_documents d ON d.id=p.document_id
            WHERE d.synthetic=false AND d.reviewed=true AND '''+DOCUMENT_ACCESS+''' AND to_tsvector('french',p.content) @@ plainto_tsquery('french',%s)
            ORDER BY ts_rank_cd(to_tsvector('french',p.content),plainto_tsquery('french',%s)) DESC LIMIT 3''',(owner,owner,search,search)).fetchall()
        previous=conn.execute('''SELECT id,snapshot,created_at FROM chat_business_examples WHERE owner_id=%s
            AND snapshot->'_experience'->>'validated_by_human'='true'
            AND to_tsvector('french',snapshot::text) @@ plainto_tsquery('french',%s)
            ORDER BY created_at DESC LIMIT 2''',(owner,search)).fetchall()
    safe_rows=[r for r in rows if not SECRET.search(r['content']) and not INJECTION.search(r['content'])]
    docs=[r for r in legacy if not SECRET.search(r['content']) and not INJECTION.search(r['content'])]
    for row in safe_rows+docs:row['content']=excerpt(row['content'],query)
    history=[{'kind':'example','title':'Exemple relu précédemment','content':excerpt('\n'.join(k.replace('_',' ')+' : '+str(v) for k,v in r['snapshot'].items() if not k.startswith('_') and isinstance(v,(str,int,float))),query),
        'source':'chat_business_examples:'+str(r['id']),'source_date':r['created_at'],'status':'validated','validated_at':r['created_at']}
        for r in previous if not SECRET.search(json.dumps(r['snapshot']))]
    return jsonable_encoder({'memory':[r for r in safe_rows if r['kind']!='document']+history+methods,
            'documents':[r for r in safe_rows if r['kind']=='document']+[
                {**r,'status':'validated' if r['reviewed'] else 'pending','kind':'document'} for r in docs],
            'requires_live_data':bool(VOLATILE.search(query)),'used_by_model':False,'training_performed':False,
            'scope':'TEST','retrieval_method':'postgresql_french_full_text','authority':'context_only_never_execution_approval'})

def exact_delta(context,text):
    if context.get('requires_live_data'):return None
    for item in context.get('memory',[]):
        payload=item.get('payload') or {}
        if item.get('kind')=='correction' and item.get('status')=='validated' and payload.get('input_normalized')==normalized(text) and payload.get('expected_delta'):
            from app.services.chat_model import Delta
            context['used_correction_source']=item['source']
            return Delta.model_validate(payload['expected_delta'])
    return None

def capture(conn,conversation_id,message_id,answer):
    ensure(conn)
    row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(conversation_id,)).fetchone()
    user=conn.execute("SELECT content FROM chat_messages WHERE conversation_id=%s AND role='user' AND id<%s ORDER BY id DESC LIMIT 1",(conversation_id,message_id)).fetchone()
    if not user or SECRET.search(user['content']+'\n'+answer):return
    state=row['state'];proposal=state.get('analysis_job',{}).get('delta') or {}
    attempted=any(p.get('operation',{}).get('status') in ('executing','succeeded','ambiguous') for p in state.get('partners',[])+state.get('articles',[]))
    eligible=not attempted and not VOLATILE.search(user['content']+' '+answer) and not INJECTION.search(user['content']+' '+answer)
    conn.execute('''INSERT INTO learning_turns(id,owner_id,conversation_id,message_id,user_text,answer,proposal,eligible)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(message_id) DO NOTHING''',
       (uuid4(),row['owner_id'],conversation_id,message_id,user['content'][:12000],answer[:20000],Jsonb(proposal),eligible))
    conn.execute('INSERT INTO learning_config(owner_id) VALUES (%s) ON CONFLICT DO NOTHING',(row['owner_id'],))

def feedback(owner,message_id,verdict,expected='',confirm=False):
    if confirm is not True or verdict not in ('correct','incorrect'):raise crud.CrudError('Validation explicite requise.',422)
    with db.connection() as conn:
        ensure(conn)
        turn=conn.execute('SELECT * FROM learning_turns WHERE owner_id=%s AND message_id=%s',(owner,message_id)).fetchone()
        if not turn:
            old=conn.execute("SELECT m.content,m.conversation_id,m.payload FROM chat_messages m JOIN chat_conversations c ON c.id=m.conversation_id WHERE m.id=%s AND c.owner_id=%s AND m.role='assistant'",(message_id,owner)).fetchone()
            if old and (old['payload'].get('document_read') or old['payload'].get('mcp_read')):raise crud.CrudError('Une lecture de document ou de Sage ne devient pas automatiquement un exemple validé. Corrigez les informations utiles dans le chat.',422)
            if old:
                capture(conn,old['conversation_id'],message_id,old['content'])
                turn=conn.execute('SELECT * FROM learning_turns WHERE owner_id=%s AND message_id=%s',(owner,message_id)).fetchone()
        if not turn:raise crud.CrudError('Réponse introuvable ou exclue de la mémoire.',404)
        target=clean(expected) if verdict=='incorrect' else clean(turn['answer'])
        clean(turn['user_text'])
        conn.execute('''INSERT INTO learning_feedback(id,owner_id,turn_id,verdict,expected,confirmed)
            VALUES (%s,%s,%s,%s,%s,true) ON CONFLICT(owner_id,turn_id) DO UPDATE SET verdict=EXCLUDED.verdict,expected=EXCLUDED.expected,confirmed=true,created_at=now()''',
            (uuid4(),owner,turn['id'],verdict,target))
        content=turn['user_text']+'\nCorrection validée : '+target
        conn.execute("UPDATE learning_items SET status='superseded' WHERE owner_id=%s AND kind IN ('example','correction') AND source=%s",(owner,'chat-message:'+str(message_id)))
        if turn['eligible'] and not INJECTION.search(content) and not VOLATILE.search(content):
            conn.execute('''INSERT INTO learning_items(id,owner_id,kind,title,content,source,status,payload,sha256,validated_at,validated_by)
                VALUES (%s,%s,'example',%s,%s,%s,'validated',%s,%s,now(),%s)
                ON CONFLICT(owner_id,kind,sha256) DO UPDATE SET status='validated',validated_at=now(),validated_by=EXCLUDED.validated_by''',
                (uuid4(),owner,'Retour utilisateur validé',content,'chat-message:'+str(message_id),
                 Jsonb({'input_normalized':normalized(turn['user_text']),'target':target}),digest(normalized(content)),owner))
            if verdict=='incorrect':
                from app.services.supplier_chat_flow import extract
                try:parsed=extract('Créer un fournisseur\n'+target,{})
                except ValueError:parsed=None
                if parsed and parsed[0].fournisseurs:
                    declared=parsed[0].fournisseurs[0].model_dump(exclude_none=True,exclude_unset=True)
                    if declared.get('nom') and all(normalized(str(value)) in normalized(turn['user_text']) for value in declared.values()):
                        payload={'input_normalized':normalized(turn['user_text']),'expected_delta':parsed[0].model_dump(exclude_none=True,exclude_unset=True)}
                        conn.execute('''INSERT INTO learning_items(id,owner_id,kind,title,content,source,status,payload,sha256,validated_at,validated_by)
                            VALUES (%s,%s,'correction',%s,%s,%s,'validated',%s,%s,now(),%s)
                            ON CONFLICT(owner_id,kind,sha256) DO UPDATE SET status='validated',validated_at=now(),validated_by=EXCLUDED.validated_by''',
                            (uuid4(),owner,'Correction de lecture fournisseur validée',content,'chat-message:'+str(message_id),Jsonb(payload),digest(normalized(content)),owner))
    return {'recorded':True,'validated_by_user':True,'training_performed':False,'eligible_for_dataset':turn['eligible']}

def memory_request(owner,text):
    match=re.match(r'^(?:retiens|mémorise|memorise)\s+(?:que\s+)?(.+)$',text.strip(),re.I|re.S)
    if not match:return None
    return create_item(owner,'preference','Préférence déclarée dans le chat',match[1],source='user_explicit_memory_request')

def document_answer(context,text):
    if context.get('requires_live_data') or not re.match(r'^(?:comment|quelle|quelles|quel|quels|explique|proc[eé]dure)\b',text.strip(),re.I):return None
    for item in context.get('memory',[]):
        payload=item.get('payload') or {}
        if item.get('kind')=='example' and payload.get('input_normalized')==normalized(text) and payload.get('target'):
            context['used_example_source']=item['source']
            return payload['target']+'\n\nSource : correction validée par vous ('+str(item['source_date'])+').'
    docs=[d for d in context.get('documents',[]) if d.get('status')=='validated'][:2]
    if not docs:return None
    context['used_document_sources']=[d['source'] for d in docs]
    return 'Voici les passages pertinents des documents validés :\n\n'+'\n\n'.join(d['content']+'\nSource : '+d['source']+' · '+str(d['source_date']) for d in docs)

def status(owner):
    from app.services.learning_training import capability
    cap=capability()
    with db.connection() as conn:
        ensure(conn)
        if cap.get('digest') and cap['digest']!='unverified':
            conn.execute('''INSERT INTO learning_versions(id,owner_id,model_name,digest,status,metadata)
                VALUES (%s,%s,%s,%s,'baseline',%s) ON CONFLICT DO NOTHING''',
                (uuid4(),owner,cap['model'],cap['digest'],Jsonb({'source':'ollama_installed','activation_changed':False})))
        items=conn.execute('SELECT * FROM learning_items WHERE owner_id=%s ORDER BY created_at DESC LIMIT 100',(owner,)).fetchall()
        turns=conn.execute('SELECT count(*) AS n FROM learning_turns WHERE owner_id=%s',(owner,)).fetchone()['n']
        jobs=conn.execute('SELECT * FROM learning_jobs WHERE owner_id=%s ORDER BY created_at DESC LIMIT 10',(owner,)).fetchall()
        versions=conn.execute('SELECT * FROM learning_versions WHERE owner_id=%s ORDER BY created_at DESC',(owner,)).fetchall()
        config=conn.execute('SELECT * FROM learning_config WHERE owner_id=%s',(owner,)).fetchone()
        automatic_methods=conn.execute('SELECT id,family,version,status,evaluation,created_at FROM learning_auto_methods WHERE owner_id=%s ORDER BY created_at DESC LIMIT 30',(owner,)).fetchall()
        corpus=conn.execute('SELECT d.id,d.source_path,d.indexed_at,d.reviewed FROM knowledge_documents d WHERE d.synthetic=false AND '+DOCUMENT_ACCESS+' ORDER BY d.indexed_at DESC LIMIT 100',(owner,owner)).fetchall()
    return {'items':items,'corpus':corpus,'captured_turns':turns,'training_jobs':jobs,'versions':versions,'capability':cap,'automatic_methods':automatic_methods,
        'training_performed':any(j['training_performed'] for j in jobs),'config':config or {'enabled':True,'min_examples':50,'interval_hours':168}}

def import_document(owner,identifier):
    with db.connection() as conn:
        row=conn.execute('SELECT d.* FROM knowledge_documents d WHERE d.id=%s AND d.synthetic=false AND '+DOCUMENT_ACCESS,(identifier,owner,owner)).fetchone()
        if not row:raise crud.CrudError('Document introuvable.',404)
        passages=conn.execute('SELECT content FROM knowledge_passages WHERE document_id=%s ORDER BY ordinal',(identifier,)).fetchall()
    content='\n\n'.join(p['content'] for p in passages)
    if len(content)>20000:raise crud.CrudError('Document trop long ; importez les sections utiles séparément.',422)
    return create_item(owner,'document',Path(row['source_path'].split('#')[0]).name,content,row['source_path'],{'original_indexed_at':row['indexed_at'].isoformat()})
