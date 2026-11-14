"""Stateful Sage chat: scoped memory, grounded deltas, bounded tools and honest drafts."""
import asyncio,copy,hashlib,json,re,secrets,unicodedata,httpx
from time import perf_counter
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timezone
from fastapi.concurrency import run_in_threadpool
from decimal import Decimal
from collections import Counter
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from app.services import business_store as db,chat_model as model,chat_tools as tools,sage_crud as crud,article_agent as legacy,chat_turns
from app.core.config import settings
from app.schemas.sage_crud import Approval,Execution
from app.services import chat_performance as performance
from app.services import chat_semantics as semantics
from app.services import chat_partners as partners
from app.services import chat_experiences as experiences
from app.services import supplier_dialogue
from app.services import ai_provider
from app.services.supplier_sql import security as supplier_security

ROOT=Path(__file__).resolve().parents[3]
PERMITS={}  # Short-lived one-shot credentials stay server-side; restart invalidates them.
ANALYSIS_INSTANCE=str(uuid4())
ACTIVE_ANALYSES=set()
FIELDS=[name for name in model.Patch.model_fields if name!='index']

def migrate():
    body=(ROOT/'backend/migrations/007-conversation-chat.sql').read_text(encoding='utf-8');sha=hashlib.sha256(body.encode()).hexdigest()
    with db.connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('conversation-chat-migration',))
        row=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',('007-conversation-chat',)).fetchone()
        if row:
            if row['sha256']!=sha:raise ValueError('Migration checksum mismatch')
            return False
        conn.execute(body);conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('007-conversation-chat',sha))
    return True

def normalize(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).casefold()
def grounded(field,value,text):
    if field=='unite':
        from app.services.chat_slash_extract import parse_labelled
        slash=parse_labelled(text)
        if slash and slash['unite']==value:return True
    if field=='unite' and value=='UN' and re.search(r'/\s*unit[eé]\s*/',text,re.I):return True
    if field in ('unite','unite_achat','unite_vente'):
        n=normalize(text).strip(' .!')
        # L in "l'article" and UN in "un article" are not unit declarations.
        cue=r'(?:unite|uniter|unitee|unt|u)'
        if field=='unite_achat':cue=r'unite\s+(?:d.\s*)?achat'
        if field=='unite_vente':cue=r'unite\s+(?:de\s+)?vente'
        return n==normalize(value) or bool(re.search(r'\b'+cue+r'\b\s*(?:de\s+(?:stock|articles?)\s+)?(?:est\s+|[:=]\s*)?'+re.escape(normalize(value))+r'(?!\w)',n))
    if field=='gestion_stock':
        n=normalize(text)
        if value=='1' and re.search(r'\bnon\s+(?:gere(?:r|e|s)?|greer|grer)\b',n):return True
        return bool(re.search(r'\bgestion(?:\s+de)?\s+stock\s*[:=]?\s*'+re.escape(str(value))+r'(?!\w)',n))
    cues={'accounting_category':r'(?:categorie|cat|famille)\s+comptable','code_comptable':r'code\s+comptable','compte_general':r'compte\s+(?:general|comptable)','code_tva':r'code\s+(?:tva|taxe)','niveau_taxe':r'niveau\s+(?:de\s+)?taxe'}
    cues.update({'modele_article':r'modele\s+(?:d.\s*)?article','modele_site':r'modele\s+(?:de\s+)?site','modele_fournisseur':r'modele\s+(?:de\s+)?fournisseur','modele_traduction':r'modele\s+(?:de\s+)?traduction','statut_article':r'statut(?:\s+article)?','type_article':r'type\s+(?:d.\s*)?article','flag_fournisseur':r'flag\s+fournisseur'})
    if field in cues:
        direct=cues[field]+r'\s*(?:est|propose|declare|a utiliser)?\s*[:=]?\s*[\'"«]?'+re.escape(normalize(value))+r'(?!\w)'
        inverse=r'(?<!\w)'+re.escape(normalize(value))+r'\s+(?:est|comme)\s+(?:le|la|mon|ma)?\s*'+cues[field]
        if not re.search(direct,normalize(text)) and not re.search(inverse,normalize(text)):return False
    if field in ['code_article','categorie','unite','unite_achat','unite_vente','site','code_fournisseur','code_comptable','code_tva','niveau_taxe','taux_tva','compte_general']:
        return bool(re.search(r'(?<!\w)'+re.escape(normalize(value))+r'(?!\w)',normalize(text)))
    return normalize(value) in normalize(text)
def secret_message(text):
    values=[settings.approval_token.get_secret_value(),settings.sage_soap_password.get_secret_value()]
    return any(v and v in text for v in values) or bool(re.search(r'(password|mot\s+de\s+passe|APPROVAL_TOKEN|SAGE_SOAP_PASSWORD|\bPwd)\s*(?:[:=]|est\b)|Authorization\s*:|\bBearer\s+\S+',text,re.I))
def get_row(conn,owner,identifier,lock=False):
    row=conn.execute('SELECT * FROM chat_conversations WHERE id=%s AND owner_id=%s'+(' FOR UPDATE' if lock else ''),(identifier,owner)).fetchone()
    if not row:raise crud.CrudError('conversation_not_found',404)
    return row
def save_conversation_context(conn,owner,identifier,state):
    from app.services.conversation_state import synchronize
    synchronize(state,identifier)
    context=ai_provider.CONTEXT.get() or {}
    calls=context.get('calls',[]);flushed=context.get('flushed',0)
    if calls[flushed:]:
        state['ai_calls']=(state.get('ai_calls',[])+copy.deepcopy(calls[flushed:]))[-30:]
        context['flushed']=len(calls)
    entities=state.get('partners') or state.get('articles') or []
    title=None
    if entities:
        entity=entities[0];name=entity.get('nom') or entity.get('designation')
        if name:title=('Fournisseur ' if entity.get('kind')=='supplier' else 'Client ' if entity.get('kind')=='customer' else 'Article ')+name
    elif state.get('modification_drafts'):
        draft=state['modification_drafts'][-1]
        title='Modification '+{'article':'article','supplier':'fournisseur','unit':'unité'}.get(draft['resource'],'fiche')+' '+draft['code']
    conn.execute('UPDATE chat_conversations SET state=%s,title=CASE WHEN NOT title_custom AND %s::text IS NOT NULL THEN %s ELSE title END,updated_at=now() WHERE id=%s AND owner_id=%s',(Jsonb(state),title,title,identifier,owner))

def operation_snapshot(value):
    # Service rows include native UUID/datetime/Decimal objects, while chat state
    # is JSONB. Preserve decimal precision and never stringify arbitrary objects.
    return jsonable_encoder(value,custom_encoder={Decimal:str})
def append(conn,identifier,role,content,payload=None):
    payload=dict(payload or {})
    if role=='assistant' and not payload.get('memory_dialogue') and not payload.get('suppress_supplier_snapshot'):
        from app.services.supplier_snapshots import capture as capture_snapshot
        snapshot_state=conn.execute('SELECT state FROM chat_conversations WHERE id=%s',(identifier,)).fetchone()
        snapshots=capture_snapshot(snapshot_state['state']) if snapshot_state else []
        if snapshots:payload['supplier_snapshots']=snapshots
    message_id=conn.execute('INSERT INTO chat_messages(conversation_id,role,content,payload) VALUES (%s,%s,%s,%s) RETURNING id',(identifier,role,content,Jsonb(payload or {}))).fetchone()['id']
    if role=='assistant' and settings.learning_enabled and not (payload or {}).get('memory_dialogue') and not payload.get('document_read') and not payload.get('mcp_read'):
        from app.services.learning import capture
        capture(conn,identifier,message_id,content)
    return message_id
def create(owner,discussion_mode='general'):
    if discussion_mode not in ('general','supplier','supplier_ob','ob'):raise crud.CrudError('Mode de discussion invalide.',422)
    production=discussion_mode in ('supplier_ob','ob')
    if production:discussion_mode='supplier'
    identifier=uuid4()
    with db.connection() as conn:
        conn.execute('INSERT INTO chat_conversations(id,owner_id,title) VALUES (%s,%s,%s)',(identifier,owner,'Nouvelle conversation'))
        if discussion_mode=='supplier':
            conn.execute('UPDATE chat_conversations SET state=state || %s WHERE id=%s',(Jsonb({'discussion_mode':'supplier','supplier_target':'OB' if production else 'TEST'}),identifier))
        if production:conn.execute('UPDATE chat_conversations SET state=state || %s WHERE id=%s',(Jsonb({'discussion_mode':'general','supplier_target':'OB'}),identifier))
        greeting='Bonjour ! Indiquez le nom et les informations du fournisseur. Je préparerai sa fiche dans TEST pour votre confirmation.' if discussion_mode=='supplier' else 'Bonjour ! Décrivez l’article ou le fournisseur souhaité. Je préparerai sa fiche pour votre confirmation. Aucune création ne sera lancée sans votre approbation.'
        if production:greeting='Bonjour ! Décrivez l’article ou le fournisseur souhaité dans Production OB. Je préparerai sa fiche pour votre confirmation. Aucune écriture sans votre approbation.'
        append(conn,identifier,'assistant',greeting)
    return read(owner,identifier)
def read(owner,identifier):
    with db.connection() as conn:
        row=get_row(conn,owner,identifier)
        messages=conn.execute('SELECT id,role,content,payload,created_at FROM chat_messages WHERE conversation_id=%s ORDER BY id',(identifier,)).fetchall()
        if settings.learning_enabled:
            from app.services import learning
            learning.ensure(conn)
            for message in messages:
                payload=message.get('payload') or {}
                if payload.get('memory_id') and not payload.get('memory_items'):
                    message['payload']={**payload,'memory_items':[str(payload['memory_id'])],'memory_dialogue':True}
                    message['content']=message['content'].replace('Validez-la dans « Mémoire et connaissances » avant sa réutilisation.','Validez-la directement ci-dessous avant sa réutilisation.')
            memory_ids={UUID(i) for m in messages for i in m.get('payload',{}).get('memory_items',[])}
            rows=conn.execute('SELECT * FROM learning_items WHERE owner_id=%s AND id=ANY(%s)',(owner,list(memory_ids))).fetchall() if memory_ids else []
            by_id={str(item['id']):item for item in rows}
            for message in messages:
                message['memory_rules']=[by_id[i] for i in message.get('payload',{}).get('memory_items',[]) if i in by_id]
    if settings.sage_powershell_chat_enabled:
        from app.services.sage_powershell_chat import security,creation_blockers
        write_security=security()
        for a in row['state'].get('articles',[]):
            a.setdefault('checks',{})['creation_blockers']=creation_blockers(a)
    else:write_security=crud.security()
    from app.services.article_execution import describe
    for article in row['state'].get('articles',[]):
        article['execution']=describe(article)
        if article['execution']['route']=='general_test':article.setdefault('checks',{})['creation_blockers']=article['execution']['blockers']
    return {'id':row['id'],'title':row['title'],'revision':row['revision'],'state':row['state'],'messages':messages,'security':write_security,
            'supplier_security':supplier_security(folder='OB') if row['state'].get('supplier_target')=='OB' else supplier_security(),'folder':row['state'].get('supplier_target','TEST'),'model':settings.ollama_model}
def history(owner,query=''):
    with db.connection() as conn:return conn.execute('''SELECT id,title,updated_at,revision FROM chat_conversations c WHERE owner_id=%s
        AND (%s='' OR title ILIKE %s OR EXISTS(SELECT 1 FROM chat_messages m WHERE m.conversation_id=c.id AND m.content ILIKE %s))
        ORDER BY updated_at DESC LIMIT 100''',(owner,query,'%'+query+'%','%'+query+'%')).fetchall()

def finish_dialogue(owner,identifier,marker,state,reply,phase='supplier_dialogue'):
    with db.connection() as conn:
        current=get_row(conn,owner,identifier,True)
        if current['state'].get('_pending',{}).get('id')!=marker:raise crud.CrudError('obsolete_analysis_attempt',409)
        state.pop('_pending',None);state['analysis_job']=current['state']['analysis_job']
        state['analysis_job'].update(status='completed',phase=phase,updated_at=datetime.now(timezone.utc).isoformat())
        save_conversation_context(conn,owner,identifier,state)
        if phase=='modification_preview' and state.get('modification_drafts'):
            from app.services.modification_actions import ModificationAuditService
            draft=state['modification_drafts'][-1]
            ModificationAuditService.append(conn,owner,identifier,draft,'prepared' if draft.get('operation',{}).get('status')=='prepared' else 'cancelled' if draft.get('operation',{}).get('status')=='cancelled' else 'blocked')
        current_job=(state.get('analysis_job') or {}).get('id')
        article_focus=(state.get('conversation_focus') or {}).get('resource')=='article'
        supplier_updated=any(event.get('resource')=='supplier' and event.get('turn_id')==current_job for event in state.get('operation_events',[]))
        append(conn,identifier,'assistant',reply,{'supplier_dialogue':True,'sage_writes':0,'not_an_execution_approval':True,'mcp_read':phase=='mcp_read','suppress_supplier_snapshot':article_focus and not supplier_updated or phase in ('modification_preview','welcome_echo','supplier_control','supplier_summary','supplier_duplicate_read','supplier_task_question','supplier_task_clarification','conversation_question')})
    return read(owner,identifier)

def retained_dialogue_state(owner,identifier):
    with db.connection() as conn:return get_row(conn,owner,identifier)['state']

def explicit_overrides(text,state,delta):
    """Only literal scalar declarations; Qwen still handles entity detection and scope."""
    n=normalize(text);shared=delta.shared.model_dump(exclude_none=True,exclude_unset=True)
    # Do not mistake accounting category for article category.
    if shared.get('accounting_category') and not re.search(r'comptab',n):shared.pop('accounting_category')
    for pattern,field in [(r'\bcode\s+article\b\s*[:=]?\s*([a-z0-9_./-]{1,20})\b','code_article'),
                           (r'\bcode\s*[:=]?\s*([a-z][a-z0-9_./-]*\d[a-z0-9_./-]*)\b','code_article'),
                           (r'\b(?:categorie|catagorie|categ|cat)\b\s*(?:article\s*)?[:=]?\s*([a-z0-9_]{1,5})\b','categorie'),
                           (r'\b(?:unite|uniter|unitee|unt|u)\b\s*(?:de\s+(?:stock|articles?)\s*)?(?:est\s+)?[:=]?\s*([a-z0-9]{1,3})\b','unite'),
                           (r'\bsite\b\s*[:=]?\s*([a-z0-9]{1,5})\b','site')]:
        match=re.search(pattern,n)
        if match and len(match.group(1))<=20 and match.group(1) not in chat_turns.STOP|{'compt','comptab','avec','commence','commencer'}:shared[field]=match.group(1).upper()
    # Multiple per-article category/unit declarations must not become a global override.
    if len(delta.articles)>1:
        for field in ['categorie','unite','accounting_category']:
            if len({getattr(p,field) for p in delta.articles if getattr(p,field)})>1:shared.pop(field,None)
    accounting=re.search(r'(?:cat[eé]gorie|catagorie|cat|famille)\s+comptable\s*[:=]?\s*([^\s,;.\n][^,;.\n]*)',text,re.I)
    if accounting:
        shared['accounting_category']=accounting[1].strip()
    inverse_accounting=re.search(r'(?:^|[.;\n])\s*([^,;.\n]{1,70}?)\s+est\s+(?:la|ma)\s+cat[eé]gorie\s+comptable\b',text,re.I)
    if inverse_accounting:shared['accounting_category']=inverse_accounting[1].strip()
    rate=re.search(r'(?:tva|taxe|taux).{0,30}?(\d{1,2}(?:[.,]\d{1,3})?)\s*%',text,re.I)
    if rate:shared['taux_tva']=rate.group(1).replace(',','.')
    if re.fullmatch(r'\s*\d{2,5}[.\s]*',text) and state.get('articles'):
        pending=state.get('pending',[])
        if any(x.get('field')=='site' for x in pending) or not any(a.get('site') for a in state['articles']):shared['site']=re.sub(r'\D','',text)
    if re.fullmatch(r'\s*[Ff][A-Za-z0-9_-]{1,14}[.\s]*',text):shared['code_fournisseur']=text.strip(' .\n').upper()
    supplier_code=re.search(r'\b(?:fournisseur|frs)\s+(?:code\s+)?(F[A-Z0-9_-]{1,14})\b',text)
    if supplier_code:shared['code_fournisseur']=supplier_code[1]
    if 'site_exclusive' in shared and not re.search(r'uniquement|exclus|plusieurs|tous les sites',n):shared.pop('site_exclusive')
    if re.fullmatch(r'\s*(oui|oui merci|d.accord|ok)[.!\s]*',n) and state.get('pending'):
        pending=state['pending'][0]['field']
        proposals=[a.get('proposals',{}).get(pending) for a in state.get('articles',[])]
        if proposals and all(v and v==proposals[0] for v in proposals):shared[pending]=proposals[0]
    # A scalar patch not grounded in this turn may only repeat an existing value.
    for field,value in list(shared.items()):
        if isinstance(value,bool):continue
        if field=='index':shared.pop(field);continue
        raw=str(value)
        proposed=[a.get('proposals',{}).get(field) for a in state.get('articles',[])]
        accepted_proposal=bool(re.fullmatch(r'\s*(oui|oui merci|d.accord|ok)[.!\s]*',n) and raw in proposed)
        current=state.get('articles',[])
        allowed={str(a.get(field)) for a in current if a.get(field) is not None}
        unchanged=bool(current) and all(str(a.get(field))==raw for a in current)
        context_requested=bool(re.search(r'\bmeme|precedent|identique|comme',n)) and len(allowed)==1 and raw in allowed
        if not grounded(field,raw,text) and not unchanged and not context_requested and not accepted_proposal:
            shared.pop(field)
    return shared

def proposed_code(label):
    simple={'extincteur a poudre':'EXT_POUDRE','extincteur a co2':'EXT_CO2'}
    if normalize(label).strip() in simple:return simple[normalize(label).strip()]
    match=re.fullmatch(r'([A-Za-z]+)\s+([A-Za-z]+)\s+([A-Za-z]+)\s+([A-Za-z])\s+([A-Za-z0-9]+)\s+(\d+)\s*(CM|MM)',label.strip(),re.I)
    if match:
        prefix=''.join(match[i][0].upper() for i in [1,2,3])
        size=int(match[6])*(10 if match[7].upper()=='CM' else 1)
        return f'{prefix}-{match[4].upper()}-{match[5].upper()}-{size}'[:20]
    text=unicodedata.normalize('NFKD',label).encode('ascii','ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+','-',text).strip('-')[:20] or 'AI'+uuid4().hex[:12].upper()
def invalidate(article):
    if (article.get('operation') or {}).get('transport')=='direct_sql_article':
        from app.services import article_sql,chat_article_sql_actions
        if article['operation'].get('status') in article_sql.TERMINAL:raise crud.CrudError('attempted_article_is_immutable_readback_only',409)
        chat_article_sql_actions.PERMITS.pop(article.get('id'),None)
    children=article.get('strict_site_operations',{})
    if any(op.get('status') in ('executing','ambiguous','unverified','succeeded','failed') for op in children.values()):raise crud.CrudError('attempted_article_site_is_immutable_readback_only',409)
    if children:
        from app.services.chat_general_sites import PERMITS as site_permits
        with db.connection() as conn:
            for site,child in children.items():
                if child.get('id'):
                    conn.execute("UPDATE soap_operations SET status='invalidated',updated_at=now() WHERE id=%s AND status IN ('prepared','approved','blocked')",(UUID(child['id']),))
                    conn.execute('UPDATE soap_operation_approvals SET consumed_at=COALESCE(consumed_at,now()) WHERE operation_id=%s',(UUID(child['id']),))
                site_permits.pop(article['id']+':'+site,None)
        article.pop('strict_site_operations',None)
    op=article.get('operation') or {}
    if op.get('transport')=='strict_generic':
        if op.get('status') in ('executing','ambiguous','unverified','succeeded','failed'):raise crud.CrudError('attempted_article_is_immutable_readback_only',409)
        if op.get('id'):
            with db.connection() as conn:
                conn.execute("UPDATE soap_operations SET status='invalidated',updated_at=now() WHERE id=%s AND status IN ('prepared','approved','blocked')",(UUID(op['id']),))
                conn.execute('UPDATE soap_operation_approvals SET consumed_at=COALESCE(consumed_at,now()) WHERE operation_id=%s',(UUID(op['id']),))
        from app.services.chat_general_articles import PERMITS as general_permits
        general_permits.pop(article.get('id'),None)
    if op.get('transport')=='PowerShell 5.1' and op.get('status') in ('executing','ambiguous','succeeded','failed','unverified'):
        raise crud.CrudError('attempted_article_is_immutable_readback_only',409)
    if article.get('legacy_id'):
        with db.connection() as conn:
            row=conn.execute('SELECT operation_id FROM article_agent_drafts WHERE id=%s',(UUID(article['legacy_id']),)).fetchone()
            if row and row['operation_id']:
                operation=conn.execute('SELECT status FROM soap_operations WHERE id=%s',(row['operation_id'],)).fetchone()
                if operation and operation['status'] in ['prepared','approved','blocked']:
                    conn.execute("UPDATE soap_operations SET status='invalidated',updated_at=now() WHERE id=%s",(row['operation_id'],))
                    conn.execute('UPDATE soap_operation_approvals SET consumed_at=COALESCE(consumed_at,now()) WHERE operation_id=%s',(row['operation_id'],))
                    crud.event(conn,row['operation_id'],'chat_revision_invalidated',{'reason':'draft_changed'})
    PERMITS.pop(article.get('id'),None)
    for key in ['legacy_id','operation','reviewed','approved','outcome','write_status']:article.pop(key,None)

def _merge(state,delta,text):
    state=copy.deepcopy(state);articles=state.setdefault('articles',[])
    turn=chat_turns.analyse(text,state)
    state['last_turn']={'kind':turn.kind,'readonly':turn.readonly,'restricted':turn.restricted,'explicit_values':turn.values,'lookups':turn.lookups}
    state.setdefault('lookup_requests',{}).update(turn.lookups)
    if re.search(r'comptab|\btva\b|fisc',normalize(text)):state['research_finance']=True
    if turn.kind=='cancellation':
        state['workflow']='cancelled'
        state.pop('awaiting_confirmation',None)
        if state.get('modification_drafts'):
            from app.services.modification_actions import PERMITS as modification_permits
            from app.services.erp_modification import TERMINAL as modification_terminal
            for draft in state['modification_drafts']:
                if draft.get('operation',{}).get('status') in modification_terminal:continue
                modification_permits.pop(draft['id'],None);draft['approved']=False;draft['sensitive_approved']=False
                draft['operation']={'status':'cancelled','message':'Modification annulée. Toute reprise exige une nouvelle préparation et confirmation.'}
        for article in articles:invalidate(article)
    if turn.readonly:return state
    if turn.clear_fields and articles and not re.search(r'\b(?:creer?|nouveaux|nouvel)\b',normalize(text)):
        # Explicit removal is not an omitted/null model value. Never resurrect
        # the previous supplier from the model's memory or a learned example.
        selection=re.search(r'\b(premier|deuxieme|second|article\s+[1-9])\b',normalize(text))
        indices=list(range(len(articles)))
        if selection:
            word=selection[1]
            index=0 if word=='premier' else 1 if word in ('deuxieme','second') else int(word.split()[-1])-1
            if index>=len(articles):raise ValueError('invalid_article_target')
            indices=[index]
        for index in indices:
            a=articles[index];invalidate(a)
            for field in turn.clear_fields:
                a[field]=None;a.setdefault('sources',{})[field]='user_explicitly_removed'
                a.setdefault('proposals',{}).pop(field,None)
            if a.get('sources',{}).get('reference_interne')=='internal_proposal_not_supplier_reference':
                a.pop('reference_interne',None);a['sources'].pop('reference_interne',None)
            a['supplier_intent']='none'
        state['pending']=[q for q in state.get('pending',[]) if q.get('field') not in turn.clear_fields]
        state['last_turn']['cleared_fields']=turn.clear_fields
        # Other explicit corrections in the same message must also survive.
        for index in indices:
            for field,value in turn.values.items():
                articles[index][field]=value;articles[index]['sources'][field]='user_declared'
        return state
    if state.get('workflow')=='cancelled':state['workflow']='draft'
    if re.search(r'comptab|\btva\b|fisc',normalize(text)):state['research_finance']=True
    common=dict(turn.values) if turn.restricted else explicit_overrides(text,state,delta)
    # Critical references require a value declaration, never a following word.
    for field in ['site','code_fournisseur']:
        common.pop(field,None)
        if field in turn.values:common[field]=turn.values[field]
    common.update(turn.values)
    patches=[] if turn.restricted else list(delta.articles)
    for field in ('site','code_fournisseur','categorie','unite'):
        if len({getattr(p,field) for p in patches if getattr(p,field)})>1:
            common.pop(field,None)
    # Preserve an explicitly labelled designation when the model omits it.
    # This copies user text for one initial article; it invents no business value.
    explicit_labels=re.findall(r'\bd[eé]signation\s*[:=]?\s*([^,;\n]{1,70})(?=[,;\n]|$)',text,re.I)
    if not articles and not turn.restricted and len(explicit_labels)==1 and len(patches)<=1:
        label=explicit_labels[0].strip().rstrip('.')
        if patches and not patches[0].designation:
            patches=[patches[0].model_copy(update={'designation':label})]
        elif not patches:
            patches=[model.Patch(designation=label)]
    # Qwen sometimes echoes existing articles when asked to generate their codes.
    # Context echoes are neither new objects nor permission to replace a draft.
    known_labels={normalize(a.get('designation','')) for a in articles}
    if articles and patches and all(p.index is None and p.designation and normalize(p.designation) in known_labels and normalize(p.designation) not in normalize(text) for p in patches):
        patches=[]
    if not articles and not patches and common.get('designation'):
        patches=[model.Patch(designation=common.pop('designation'))]
    if not articles and not patches:
        # An explicit single-article declaration remains a draft even if Qwen
        # incorrectly returns an empty lookup. Never infer several unnamed objects.
        labels=re.findall(r'(?:\bun\s+article|\bbesoin\s+(?:d.un\s+)?article)\s+([^,;.\n]+)',text,re.I)
        if len(labels)==1 and 0<len(labels[0].strip())<=70:patches=[model.Patch(designation=labels[0].strip())]
    literal=re.search(r'\b(?:cr[eé]ation\s+demand[eé]e|d[eé]signation)\s*[:=]\s*([^,;.\n]+)',text,re.I)
    if not articles and literal and len(literal[1].strip())<=70:
        if not patches:patches=[model.Patch(designation=literal[1].strip())]
        elif len(patches)==1 and not patches[0].designation:patches=[patches[0].model_copy(update={'designation':literal[1].strip()})]
    new=bool(patches and any(p.designation and p.index is None for p in patches) and (not articles or delta.intent in ('new','other')))
    targets=semantics.targets(text) or turn.targets or delta.targets or list(range(1,len(articles)+1))
    if common.get('site') and any(i>len(articles) for i in targets) and re.search(r'\bsite\b|^\s*\d+[.\s]*$',normalize(text)):
        targets=list(range(1,len(articles)+1))
    if any(i<1 or i>len(articles) for i in targets) and not new:raise ValueError('invalid_article_target')
    if new:
        if len(articles)+len(patches)>20:raise ValueError('maximum_twenty_articles')
        for patch in patches:
            values=patch.model_dump(exclude_none=True,exclude_unset=True);values.pop('index',None)
            if not values.get('designation'):continue
            if len(patches)==1:
                literal=re.search(r'(?:\bun\s+article|\bbesoin\s+(?:d.un\s+)?article)\s+([^,;.\n]+)',text,re.I)
                if literal and len(literal[1].strip())<=70 and normalize(literal[1].strip()).startswith(normalize(values['designation'])):
                    values['designation']=literal[1].strip()
            if normalize(values['designation']) not in normalize(text) and values['designation'] not in semantics.expanded_designations(text):
                raise ValueError('designation_not_grounded')
            if values.get('accounting_category') and not re.search('comptab',normalize(text)):values.pop('accounting_category')
            if 'site_exclusive' in values and not re.search(r'uniquement|exclus|plusieurs|tous les sites',normalize(text)):values.pop('site_exclusive')
            for key,value in list(values.items()):
                if isinstance(value,str) and key!='designation' and not grounded(key,value,text):values.pop(key)
                elif key in ('site','code_fournisseur') and (key not in turn.values or value!=turn.values[key]):
                    scope=semantics.literal_scope(text,values['designation'],[p.designation for p in patches if p.designation])
                    local=chat_turns.analyse(scope,{})
                    if local.values.get(key)!=value:values.pop(key)
            item={k:None for k in FIELDS};item.update(common);item.update(values)
            item.update(id=str(uuid4()),sources={k:'user_declared' for k in {**common,**values}})
            # Preserve explicit common category even when the model mislabels it as accounting.
            if common.get('categorie') and not patch.categorie:item['categorie']=common['categorie'];item['sources']['categorie']='user_declared'
            articles.append(item)
    else:
        for i in targets:
            article=articles[i-1]
            changed={k:v for k,v in common.items() if article.get(k)!=v}
            if changed:invalidate(article)
            article.update(changed);article.setdefault('sources',{}).update({k:'user_declared' for k in changed})
        for patch in patches:
            if patch.index is None:continue
            if patch.index>len(articles):raise ValueError('invalid_article_target')
            article=articles[patch.index-1];values=patch.model_dump(exclude_none=True,exclude_unset=True);values.pop('index',None)
            values={k:v for k,v in values.items() if not isinstance(v,str) or grounded(k,v,text) or v==article.get(k)}
            values={k:v for k,v in values.items() if k not in ('site','code_fournisseur') or (k in turn.values and v==turn.values[k])}
            if any(article.get(k)!=v for k,v in values.items()):invalidate(article)
            article.update(values);article.setdefault('sources',{}).update({k:'user_declared' for k in values})
    for article in articles:
        if article.get('fournisseur_nom') or article.get('code_fournisseur'):
            article.pop('supplier_intent',None)
        if not article.get('code_article'):
            code=proposed_code(article.get('designation') or '')
            if any(a is not article and a.get('code_article')==code for a in articles):code=code[:15]+'-'+uuid4().hex[:4].upper()
            article['code_article']=code;article['sources']['code_article']='application_proposal_not_reserved'
        if article.get('code_fournisseur') and (not article.get('reference_interne') or article['sources'].get('reference_interne')=='internal_proposal_not_supplier_reference'):
            short=article['code_article'].replace('-XPS','')
            reference=(article['code_fournisseur']+'-'+short)[:50]
            if article.get('reference_interne') and article['reference_interne']!=reference:
                article.setdefault('obsolete_derived_values',[]).append({'field':'reference_interne','value':article['reference_interne'],'reason':'supplier_or_article_code_changed','obsolete':True})
            article['reference_interne']=reference
            article['sources']['reference_interne']='internal_proposal_not_supplier_reference'
    offer=state.get('awaiting_confirmation')
    if offer and (offer['field'] in turn.values) and turn.kind in ('confirmation','correction','declaration'):
        state.pop('awaiting_confirmation',None)
        state.get('lookup_requests',{}).pop('categorie',None)
    return state

def merge(state,delta,text):
    before=copy.deepcopy(state)
    issue=semantics.clarification(text,state,delta)
    if issue:
        result=copy.deepcopy(state);result['turn_clarifications']=[issue]
        result['last_turn']={'kind':'clarification','readonly':True,'restricted':False,'explicit_values':{},'lookups':{}}
        return result
    if state.get('articles') and delta.intent!='new' and not (delta.fournisseurs or delta.clients):
        clauses=re.split(r'[;\n]|\.\s+|\s+et\s+(?=pour\b)',text,flags=re.I)
        scoped=[(part,semantics.targets(part)) for part in clauses if semantics.targets(part)]
        if len(scoped)>1 and len(scoped)==len([p for p in clauses if p.strip()]):
            claimed=[i for _,indices in scoped for i in indices]
            if len(set(claimed))==len(claimed):
                result=copy.deepcopy(state)
                for part,indices in scoped:
                    sub=delta.model_copy(update={'targets':indices,'articles':[p for p in delta.articles if p.index in indices]})
                    result=merge(result,sub,part)
                return result
    if (delta.fournisseurs or delta.clients) and not delta.articles and not delta.shared.model_dump(exclude_unset=True):
        result=copy.deepcopy(state);result.setdefault('articles',[])
        turn=chat_turns.analyse(text,state)
        result['last_turn']={'kind':turn.kind,'readonly':turn.readonly,'restricted':turn.restricted,'explicit_values':{},'lookups':turn.lookups}
    else:result=_merge(state,delta,text)
    if not result.get('last_turn',{}).get('readonly'):
        decision=semantics.supplier_decision(text)
        if decision=='optional':result['supplier_requirement']='optional'
        if decision=='none':
            selected=semantics.targets(text) or delta.targets or list(range(1,len(result['articles'])+1))
            for index in selected:
                if index>len(result['articles']):raise ValueError('invalid_article_target')
                article=result['articles'][index-1]
                if any(article.get(f) for f in ('fournisseur_nom','code_fournisseur','reference_fournisseur')):invalidate(article)
                for field in ('fournisseur_nom','code_fournisseur','reference_fournisseur'):
                    article[field]=None;article.setdefault('sources',{})[field]='user_explicitly_removed'
                article['supplier_intent']='none'
        semantics.apply_naming(result,text,invalidate)
    result.pop('turn_clarifications',None)
    from app.services.chat_article_requests import apply as apply_article_request
    result=apply_article_request(result,text,delta)
    result=partners.merge(result,delta,text)
    previous_partners={p['id']:p for p in before.get('partners',[])}
    for partner in result.get('partners',[]):
        old=previous_partners.get(partner['id'],{})
        if old.get('nom') and old['nom']!=partner.get('nom'):
            for article in result.get('articles',[]):
                if article.get('supplier_dependency',{}).get('partner_id')==partner['id'] and article.get('fournisseur_nom')==old['nom']:
                    invalidate(article);article['fournisseur_nom']=partner['nom']
                    article.setdefault('sources',{})['fournisseur_nom']='user_declared_partner_correction'
    return semantics.record_changes(before,result,text,FIELDS+['requested_sites'])

def tool_plan(state):
    plan=tools.Plan();bindings={}
    if state.get('lookup_requests',{}).get('catalogue_categories'):
        plan.add('get_article_categories',Category='',Label='',Site='')
    for a in state['articles']:
        refs={};cat=a.get('categorie') or '';label=a.get('designation') or ''
        term='XPS' if re.search(r'\bXPS\b',label,re.I) else ' '.join(label.split()[:2])[:70]
        refs['similar']=tools.search_articles(plan,term,cat)
        refs['recent']=tools.get_recent_articles(plan,cat)
        refs['duplicate']=tools.check_article_duplicate(plan,a.get('code_article') or '')
        refs['category']=tools.get_article_categories(plan,cat,site=a.get('site') or '')
        if state.get('lookup_requests',{}).get('categorie'):
            refs['category_candidates']=tools.get_article_categories(plan,'',label=state['lookup_requests']['categorie'],site=a.get('site') or '')
        unit=a.get('unite') or '';buy=a.get('unite_achat') or unit;sale=a.get('unite_vente') or unit
        refs['units']=tools.get_units(plan,unit,buy)
        refs['sales_unit']=tools.get_units(plan,sale)
        if buy and unit and buy!=unit:refs['buy_conversion']=plan.add('get_unit_conversions',Unit=buy,Unit2=unit)
        if sale and unit and sale!=unit:refs['sale_conversion']=plan.add('get_unit_conversions',Unit=sale,Unit2=unit)
        refs['site']=tools.get_sites(plan,a.get('site') or '')
        for selected_site in a.get('requested_sites',[]):
            refs['requested_site_'+selected_site]=tools.get_sites(plan,selected_site)
            refs['requested_category_'+selected_site]=tools.get_article_categories(plan,cat,site=selected_site)
            refs['requested_child_'+selected_site]=plan.add('get_article_site',Code=a['code_article'],Site=selected_site)
        if a.get('site'):
            refs['article_site']=plan.add('get_article_site',Code=a['code_article'],Site=a['site'])
        if a.get('fournisseur_nom') or a.get('code_fournisseur'):
            refs['supplier']=tools.search_suppliers(plan,a.get('fournisseur_nom') or '',a.get('code_fournisseur') or '')
            if a.get('code_fournisseur') and a.get('fournisseur_nom'):refs['supplier_by_name']=tools.search_suppliers(plan,a['fournisseur_nom'])
        if a.get('code_fournisseur'):refs['supplier_refs']=tools.get_supplier_article_references(plan,a['code_fournisseur'])
        if a.get('accounting_category') or a.get('code_comptable'):
            refs['accounting']=tools.get_accounting_categories(plan,a.get('accounting_category') or '',a.get('code_comptable') or '')
        if a.get('taux_tva') or state.get('research_finance'):refs['taxes']=tools.get_tax_rules(plan,a.get('taux_tva') or '')
        bindings[a['id']]=refs
    return plan,bindings

def validate_article_draft(a,refs):
    errors=[];notes=[];verified={}
    def result(name):return refs.get(name,{'ok':False,'rows':[]})
    for field in ['designation','categorie','unite','site']:
        if not a.get(field):errors.append('missing:'+field)
    if not re.fullmatch(r'[A-Za-z0-9_./ -]{1,20}',a.get('code_article','')):errors.append('invalid_article_code')
    if any(not r.get('ok') for r in refs.values()):errors.append('sql_checks_incomplete')
    if result('duplicate')['rows']:errors.append('duplicate_article_code')
    for field,name in [('categorie','category'),('site','site')]:
        if a.get(field):
            if result(name)['ok'] and result(name)['rows']:verified[field]=True
            elif result(name)['ok']:errors.append('unknown:'+field)
    if 'unknown:categorie' in errors and result('category_all_sites')['rows']:
        errors.remove('unknown:categorie');errors.append('category_not_applicable_for_site')
    unitrows=result('units')['rows']+result('sales_unit')['rows'];units={r['UOM_0'].strip() for r in unitrows}
    for field in ['unite','unite_achat','unite_vente']:
        value=a.get(field)
        if value and value not in units:errors.append('unknown:'+field)
        elif value:verified[field]=True
    if not a.get('unite_achat') or not a.get('unite_vente'):notes.append('purchase_sales_units_require_category_defaults_review')
    for name in ['buy_conversion','sale_conversion']:
        if name in refs and not result(name)['rows']:errors.append('conversion_not_found:'+name)
    if a.get('code_fournisseur'):
        if not result('supplier')['ok']:errors.append('supplier_lookup_unavailable')
        elif not result('supplier')['rows']:errors.append('supplier_code_not_verified')
        else:
            verified['code_fournisseur']=True
            if a.get('fournisseur_nom') and not any(normalize(a['fournisseur_nom']) in normalize((r.get('BPRNAM_0') or '')+' '+(r.get('BPRNAM_1') or '')) for r in result('supplier')['rows']):errors.append('supplier_name_code_mismatch')
    elif a.get('fournisseur_nom'):
        rows=result('supplier')['rows'];errors.append('supplier_lookup_unavailable' if not result('supplier')['ok'] else 'supplier_ambiguous' if len(rows)>1 else 'supplier_confirmation_required' if rows else 'supplier_not_found')
    if a.get('code_comptable'):
        if result('accounting')['rows']:verified['code_comptable_exists']=True
        else:errors.append('accounting_code_not_verified')
    if a.get('accounting_category') and not result('accounting')['rows']:notes.append('accounting_label_not_resolved')
    if a.get('taux_tva'):
        if result('taxes')['rows']:verified['tax_rate_candidates_found']=True
        notes.append('tax_applicability_requires_company_regime_date_review')
    notes += ['historical_examples_are_not_business_rules','conditional_business_rules_not_certified']
    if result('article_site')['rows']:verified['article_site_already_exists']=True
    selections=[]
    for code in a.get('requested_sites',[]):
        proof=result('requested_site_'+code);category_proof=result('requested_category_'+code)
        present=proof.get('ok') and any(r.get('FCY_0','').strip()==code for r in proof.get('rows',[]))
        if proof.get('ok') and not present:errors.append('unknown:requested_site:'+code)
        applicable=bool(a.get('categorie') and category_proof.get('ok') and any(r.get('TCLCOD_0','').strip()==a['categorie'] for r in category_proof.get('rows',[])))
        if a.get('categorie') and category_proof.get('ok') and not applicable:errors.append('category_not_applicable_for_requested_site:'+code)
        selections.append({'site':code,'exists':bool(present),'category_verified':applicable,
            'article_site_exists':bool(result('requested_child_'+code)['rows']),'fields_compared':False,'creation_executed':False})
    return {'valid_basic':not errors,'errors':sorted(set(errors)),'notes':notes,'verified':verified,'tools':refs,'sage_created':False,
            'requested_site_checks':selections,
            'supplier_reference_official':False,'site_exclusive':a.get('site_exclusive'),
            'article_site_dependency':{'parent_exists':bool(result('duplicate')['rows']),'site_exists':bool(result('site')['rows']),'creation_executed':False},
            'article_site_workflow':{'folder':'TEST','article':a.get('code_article'),'site':a.get('site'),
                'status':'existing_uncompared' if result('article_site')['rows'] else 'not_prepared',
                'parent_exists':bool(result('duplicate')['rows']),'fields_verified':False,
                'separate_approval_required':True,'creation_executed':False,
                'connector_scope_supported':a.get('code_article')=='EXT_POUDRE',
                'steps':['verify_parent_and_site','prepare_child_fields_and_xml','approve_exact_child_data','create_child_once','read_back_and_compare_child_fields']},
            'coding_conventions':{'observed_codes':[r['ITMREF_0'] for r in result('recent')['rows']],
                'proposal_max_length':20,'global_naming_rule_certified':False,'examples_are_not_rules':True}}

def prepare_article_draft(state,results,bindings):
    state=copy.deepcopy(state)
    code_counts=Counter((a.get('code_article') or '').casefold() for a in state['articles'])
    for a in state['articles']:
        refs={name:results.get(key,{'ok':False,'rows':[]}) for name,key in bindings[a['id']].items()}
        supplier=refs.get('supplier',{})
        if a.get('fournisseur_nom') and not a.get('code_fournisseur') and supplier.get('ok'):
            exact=[r for r in supplier.get('rows',[]) if normalize(' '.join((r.get(k) or '').strip() for k in ['BPRNAM_0','BPRNAM_1'])).strip()==normalize(a['fournisseur_nom']).strip()]
            if len(exact)==1:
                refs['supplier']={**supplier,'rows':exact,'exact_name_match':True}
        a['checks']=validate_article_draft(a,refs)
        if a.get('code_article') and code_counts[a['code_article'].casefold()]>1:
            a['checks']['errors'].append('duplicate_code_in_drafts');a['checks']['valid_basic']=False
        from app.services.article_execution import describe
        a['checks']['creation_blockers']=describe(a)['blockers']
        a['proposals']={}
        categories=refs.get('category',{}).get('rows',[])
        applicable=[r for r in categories if r.get('STOFCY_0','').strip()==(a.get('site') or '')] or [r for r in categories if not r.get('STOFCY_0','').strip()]
        units={r.get('STU_0','').strip() for r in applicable if r.get('STU_0','').strip()}
        if not a.get('unite') and len(units)==1:a['proposals']['unite']=next(iter(units))
        suppliers=refs.get('supplier',{}).get('rows',[])
        if not a.get('code_fournisseur') and len(suppliers)==1:a['proposals']['code_fournisseur']=suppliers[0]['BPSNUM_0'].strip()
        if a.get('code_fournisseur') and len(suppliers)==1 and 'supplier_name_code_mismatch' in a['checks']['errors']:
            if suppliers[0].get('BPRNAM_0'):a['proposals']['fournisseur_nom']=suppliers[0]['BPRNAM_0'].strip()
        candidates=refs.get('category_candidates',{}).get('rows',[])
        codes={r['TCLCOD_0'].strip() for r in candidates}
        if len(codes)==1:
            code=next(iter(codes));a['proposals']['categorie']=code
            if a.get('categorie')!=code:state['awaiting_confirmation']={'field':'categorie','value':code,'label':next((r.get('TCLDES_0','').strip() for r in candidates if r['TCLCOD_0'].strip()==code),''),'article_ids':[x['id'] for x in state['articles']],'source':'TEST.ITMCATEG','confidence':'label_candidate_requires_confirmation'}
        similar=refs.get('similar',{}).get('rows',[])+refs.get('similar_other_categories',{}).get('rows',[])
        evidence=[]
        for r in similar:
            code=(r.get('ACCCOD_0') or '').strip();level=(r.get('VACITM_0') or '').strip()
            tax_rows=refs.get('suggested_tax_level_'+level,{}).get('rows',[])
            evidence.append({'article':r['ITMREF_0'],'categorie':r.get('TCLCOD_0'),'unite':r.get('STU_0'),'code_comptable':code,'niveau_taxe':level,
                'accounting_reference':refs.get('suggested_accounting_'+code,{}).get('rows',[]),
                'tax_determination':tax_rows,'tax_rates':[rate for tx in tax_rows for rate in refs.get('suggested_tax_code_'+tx.get('VAT_0','').strip(),{}).get('rows',[])],
                'confidence':'medium' if (r.get('STU_0') or '').strip()==a.get('unite') else 'low',
                'confidence_reason':'historical_comparison_not_business_rule','source':'TEST.ITMMASTER','applied':False})
        a['suggestions']=evidence
        site_rows=refs.get('site',{}).get('rows',[])
        a['checks']['site_stock_capability_observed']=any(r.get('WRHFLG_0')==2 for r in site_rows)
        a['checks']['site_permissions_verified']=False
    return state

def questions(state):
    pending=[]
    pending.extend({'field':'clarification','text':text} for text in state.get('turn_clarifications',[]))
    if any('duplicate_code_in_drafts' in a.get('checks',{}).get('errors',[]) for a in state.get('articles',[])):
        pending.append({'field':'code_article','text':'Plusieurs brouillons utilisent le même code article. Indiquez un code distinct pour chaque article concerné.'})
    offer=state.get('awaiting_confirmation')
    if offer and any(a.get(offer['field'])!=offer['value'] for a in state['articles']):
        pending.append({'field':offer['field'],'text':f"J’ai trouvé {offer['value']} — {offer.get('label','')} dans TEST. Confirmez-vous cette catégorie à la place de la catégorie actuelle ?"})
    for field,text in [('site','Sur quel site souhaitez-vous rattacher ces articles ?'),('unite','Quelle unité de stock faut-il utiliser ?'),('categorie','Quelle catégorie article faut-il utiliser ?')]:
        if any(not a.get(field) for a in state['articles']):
            if field=='unite':
                values={a.get('proposals',{}).get('unite') for a in state['articles']}
                if len(values)==1 and None not in values:text=f"La catégorie propose l’unité {next(iter(values))}. Souhaitez-vous la retenir ?"
            pending.append({'field':field,'text':text})
    if any(a.get('fournisseur_nom') and not a.get('code_fournisseur') and a.get('supplier_dependency',{}).get('status')!='absent_draft_only' for a in state['articles']):
        ambiguous=any('supplier_ambiguous' in a.get('checks',{}).get('errors',[]) for a in state['articles'])
        proposed={a.get('proposals',{}).get('code_fournisseur') for a in state['articles']}
        question='Plusieurs fournisseurs correspondent. Quel code Sage faut-il retenir ?' if ambiguous else f"J’ai trouvé le fournisseur {next(iter(proposed))}. Est-ce celui-ci ?" if len(proposed)==1 and None not in proposed else 'Connaissez-vous le code Sage du fournisseur indiqué ? Je ne l’inventerai pas.'
        pending.append({'field':'code_fournisseur','text':question})
    for field,error,label in [('categorie','unknown:categorie','catégorie'),('site','unknown:site','site')]:
        invalid={a.get(field) for a in state['articles'] if error in a.get('checks',{}).get('errors',[])}
        if invalid and not any(q['field']==field for q in pending):
            rows=[r for a in state['articles'] for r in a.get('checks',{}).get('tools',{}).get('available_sites' if field=='site' else 'available_categories',{}).get('rows',[])]
            choices=sorted({r['FCY_0' if field=='site' else 'TCLCOD_0'].strip() for r in rows})
            pending.append({'field':field,'text':f"Le code {label} déclaré ({', '.join(sorted(invalid))}) n’est pas retrouvé dans TEST."+(f" Codes retournés : {', '.join(choices)}." if choices else '')+" Souhaitez-vous le conserver non vérifié ou indiquer un autre code ?"})
    mismatches={a.get('proposals',{}).get('fournisseur_nom') for a in state['articles'] if 'supplier_name_code_mismatch' in a.get('checks',{}).get('errors',[])}
    if len(mismatches)==1 and None not in mismatches:
        pending.append({'field':'fournisseur_nom','text':f"Le code fournisseur indiqué porte le nom « {next(iter(mismatches))} » dans TEST. Confirmez-vous ce fournisseur, ou faut-il corriger le code ?"})
    if not settings.sage_powershell_chat_enabled and not pending and any(a.get('site') and not a.get('requested_sites') and a.get('site_exclusive') is None for a in state['articles']):
        pending.append({'field':'site_exclusive','text':'Le site indiqué est retenu. Le rattachement doit-il être limité à ce site ou concerner plusieurs sites ?'})
    return pending

def compose(state,new=False,previous=None):
    articles=state['articles']
    catalogue=state.get('catalogue_results')
    catalogue_text=''
    if catalogue is not None:
        if not catalogue.get('ok'):catalogue_text='Le catalogue des catégories est indisponible ; aucune catégorie n’a été remplacée.'
        else:
            entries=sorted({(r['TCLCOD_0'].strip(),r.get('TCLDES_0','').strip()) for r in catalogue.get('rows',[])})
            catalogue_text='Catégories retournées par TEST :\n'+'\n'.join('- '+code+' : '+label for code,label in entries)
            if not entries:catalogue_text='Aucune catégorie retournée par cette consultation TEST ; les valeurs déclarées restent conservées.'
    if not articles:
        return '\n\n'.join(x for x in (catalogue_text,partners.compose(state)) if x) or 'Décrivez les articles, fournisseurs ou clients à préparer et les informations connues. Je conserverai les réponses au fil de la conversation.'
    if state.get('last_turn',{}).get('kind')=='confirmation' and not state.get('last_turn',{}).get('explicit_values'):
        pending=questions(state)
        if pending and pending[0]['field']=='site':
            state['pending']=pending
            return 'Un « oui » ne précise pas le site. Indiquez son code, par exemple « Site déclaré 202 ». Les brouillons précédents sont conservés ; aucun SAVE n’est envoyé.'
    count={1:'un article',2:'deux articles',3:'trois articles',4:'quatre articles',10:'dix articles'}.get(len(articles),str(len(articles))+' articles')
    readonly=state.get('last_turn',{}).get('readonly')
    lines=[f"J’ai identifié {count}{' distincts' if len(articles)>1 else ''}." if new else 'J’ai conservé les valeurs déclarées et vérifié les données disponibles.' if readonly else 'J’ai mis à jour les brouillons en conservant les informations précédentes.']
    if state.get('last_turn',{}).get('creation_requested'):
        from app.services.article_execution import describe,blocked_message
        for article in articles:
            if (article.get('outcome') or {}).get('confirmed'):
                lines.append('DÉJÀ CRÉÉ ET VÉRIFIÉ : '+article['code_article']+'. Aucune nouvelle création de cette fiche.')
                continue
            info=describe(article)
            if info['route']=='general_test':
                if info['blockers']:lines.append(blocked_message(article,info['blockers']))
                else:lines.append('APPROBATION REQUISE : préparez les données exactes de '+article['code_article']+' puis approuvez cette version avant tout enregistrement.')
        lines.append('Vous demandez la création des fiches déjà décrites. Les brouillons sont conservés sans nouvelle fiche ni doublon. La relecture confirme les données ; la création nécessite ensuite une préparation valide et une approbation exacte dans le parcours autorisé. Les blocages ci-dessous restent applicables.')
    if state.get('last_turn',{}).get('presentation_requested'):
        lines.append('Affichage des articles en '+('tableau' if state.get('presentation',{}).get('article_view')=='table' else 'fiches')+' ; les valeurs et validations sont conservées.')
    if state.get('workflow')=='cancelled':lines.append('La demande est annulée ; les brouillons sont conservés pour l’historique et les approbations sont invalidées.')
    before={a['id']:a for a in (previous or {}).get('articles',[])}
    labels={'categorie':'Catégorie article déclarée','unite':'Unité déclarée','site':'Site retenu pour les articles concernés','code_fournisseur':'Code fournisseur déclaré','taux_tva':'TVA proposée (%)','accounting_category':'Catégorie comptable déclarée'}
    summary=[]
    for field,label in labels.items():
        values={str(a[field]) for a in articles if a.get(field) and a.get(field)!=before.get(a['id'],{}).get(field)}
        if values:summary.append(label+' : '+', '.join(sorted(values))+'.')
    if summary:lines.append(' '.join(summary))
    if state.get('last_turn',{}).get('cleared_fields'):
        lines.append('J’ai retiré le fournisseur des brouillons concernés, comme demandé. Je ne demanderai plus son code ; les articles, catégories, unités et sites sont conservés.')
    confirmed_categories=sorted({a['categorie'] for a in articles if a.get('checks',{}).get('verified',{}).get('categorie')})
    if confirmed_categories:lines.append('Catégories retrouvées dans le référentiel TEST : '+', '.join(confirmed_categories)+'.')
    confirmed_units=sorted({a['unite'] for a in articles if a.get('checks',{}).get('verified',{}).get('unite')})
    from app.services.article_execution import tax_review
    for article in articles:
        tax=tax_review(article)
        if tax['default_differs_from_rate_code'] and not tax['applicability_verified']:
            lines.append('TVA demandée : '+str(tax['requested_rate'])+' %. Le défaut de catégorie est '+', '.join(tax['category_defaults'])+' ; le référentiel propose aussi '+', '.join(tax['candidate_levels'])+' pour ce taux. Le seul défaut ne prouve pas une incompatibilité. Décision métier nécessaire : faire valider le niveau fiscal applicable à cet article pour le site et la société concernés. Aucun code fiscal remplacé automatiquement.')
    if confirmed_units:lines.append('Unités retrouvées dans TEST : '+', '.join(confirmed_units)+'.')
    site_proofs={}
    for a in articles:
        proofs=a.get('checks',{}).get('tools',{})
        site_rows=proofs.get('site',{}).get('rows',[])+[r for key,value in proofs.items() if key.startswith('requested_site_') for r in value.get('rows',[])]
        for r in site_rows:
            if r.get('CPYNAM_0'):
                site_proofs[r['FCY_0'].strip()]=(r.get('FCYNAM_0','').strip(),r['LEGCPY_0'].strip(),r['CPYNAM_0'].strip())
    for code,(name,company,label) in sorted(site_proofs.items()):
        lines.append(f'Dans TEST, le site {code} « {name} » appartient à la société {company} « {label} ».')
    def cell(value):return str(value or 'À préciser').replace('|','／').replace('\n',' ')
    table=['| Code proposé | Désignation | Catégorie déclarée | Unité | Fournisseur déclaré | Gestion stock | Site déclaré | TVA demandée (%) |', '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for a in articles:
        stock={'1':'Non géré','2':'Géré','3':'Géré titre'}.get(a.get('gestion_stock'),'À préciser')
        supplier='Sans fournisseur' if a.get('supplier_intent')=='none' else a.get('fournisseur_nom') or a.get('code_fournisseur')
        table.append('| '+' | '.join(cell(v) for v in [a.get('code_article'),a.get('designation'),a.get('categorie'),a.get('unite'),supplier,stock,', '.join(a.get('requested_sites') or []) or a.get('site'),a.get('taux_tva')])+' |')
    lines.append('\n'.join(table))
    lines += ['', 'Codes proposés, non réservés : leur disponibilité et les valeurs métier restent soumises aux contrôles TEST.']
    if any(a.get('gestion_stock')=='1' for a in articles):lines.append('« Non géré » concerne uniquement les brouillons concernés ; aucun paramétrage général de catégorie n’est modifié.')
    if any(a.get('checks',{}).get('verified',{}).get('code_fournisseur') for a in articles):lines.append('Le code fournisseur a été retrouvé dans TEST ; les correspondances sont consultables dans les vérifications.')
    errors={e for a in articles for e in a.get('checks',{}).get('errors',[])}
    if 'sql_checks_incomplete' in errors:lines.append('Certaines recherches SQL sont indisponibles : je ne peux pas déclarer ces données vérifiées.')
    if 'unknown:categorie' in errors:lines.append('La catégorie déclarée n’a pas été retrouvée dans TEST ; je la conserve comme valeur à vérifier, sans la remplacer.')
    if 'category_not_applicable_for_site' in errors:lines.append('La catégorie existe dans TEST, mais aucune valeur générale ni déclinaison pour le site déclaré n’a été retrouvée. Je conserve la déclaration sans la valider pour ce site.')
    if 'unknown:site' in errors:
        sites=sorted({r['FCY_0'].strip() for a in articles for r in a.get('checks',{}).get('tools',{}).get('available_sites',{}).get('rows',[])})
        declared=sorted({a['site'] for a in articles if a.get('site')})
        lines.append('J’ai conservé le site '+', '.join(declared)+'. La recherche exacte dans TEST.FACILITY n’a retourné aucune ligne pour ce code ; cela ne prouve pas son absence de tout Sage.'+(' Les sites retournés dans TEST sont '+', '.join(sites)+'.' if sites else ''))
    if 'supplier_code_not_verified' in errors or 'supplier_not_found' in errors:lines.append('Le fournisseur déclaré n’a pas été retrouvé dans TEST. Son code ou son nom doit être rapproché du référentiel ; aucun code n’a été inventé.')
    if 'supplier_name_code_mismatch' in errors:lines.append('Le nom déclaré et le code fournisseur trouvé ne correspondent pas : cette association est bloquée.')
    for code in sorted({a['code_fournisseur'] for a in articles if a.get('code_fournisseur')}):
        matching=[a for a in articles if a.get('code_fournisseur')==code];result=matching[0].get('checks',{}).get('tools',{}).get('supplier',{})
        if result.get('ok') and result.get('rows'):lines.append('Le code '+code+' correspond à « '+(result['rows'][0].get('BPRNAM_0') or 'identité non renseignée').strip()+' » dans TEST. Je conserve le code fourni'+(' ; il ne correspond pas au nom demandé.' if any('supplier_name_code_mismatch' in a['checks']['errors'] for a in matching) else '.'))
        elif result.get('ok'):lines.append('Le code fournisseur '+code+' n’est pas retrouvé dans TEST ; je le conserve non vérifié.')
        else:lines.append('Le code fournisseur '+code+' est conservé, mais la consultation est indisponible.')
    examples={r['article']:r for a in articles for r in a.get('suggestions',[])}
    if examples:
        lines.append('Articles comparables consultés : '+' ; '.join(r['article']+' ('+str(r.get('categorie'))+', '+str(r.get('unite'))+')' for r in list(examples.values())[:3])+'. Ce sont des exemples, pas des valeurs appliquées automatiquement.')
        accounts=sorted({r['code_comptable']+' ('+(acc.get('DES_0') or 'libellé non renseigné').strip()+')' for r in examples.values() for acc in r.get('accounting_reference',[])})
        if accounts and state.get('research_finance'):lines.append('Codes comptables retrouvés dans le référentiel : '+', '.join(accounts)+'. Leur applicabilité reste à confirmer ; aucun compte général n’est déduit de leur forme.')
        taxes=sorted({str(r.get('VAT_0','')).strip()+' : '+str(r.get('VATRAT_0'))+' %' for e in examples.values() for r in e.get('tax_rates',[])})
        if taxes and state.get('research_finance'):lines.append('Taux trouvés dans la configuration fiscale : '+', '.join(taxes)+'. Ces taux dépendent aussi du régime, de la société et de la date ; ils ne sont pas appliqués automatiquement au brouillon.')
    if 'duplicate_article_code' in errors:lines.append('Un code article existe déjà : aucune nouvelle création n’est proposée pour cette clé.')
    if any(a.get('taux_tva') for a in articles):lines.append('La TVA indiquée reste une proposition : trouver un taux dans SQL ne prouve pas son applicabilité fiscale ni son code de détermination.')
    if any('accounting_label_not_resolved' in a.get('checks',{}).get('notes',[]) for a in articles):lines.append('Le libellé comptable déclaré n’est pas encore rapproché d’un code applicable dans TEST ; je n’en déduis aucun compte général.')
    state['pending']=questions(state)
    asked=set(state.get('asked',[]));fresh=[]
    for q in state['pending']:
        signature=q['field']+':'+','.join(str(a.get(q['field']) or '') for a in articles)
        if signature not in asked and len(fresh)<2:fresh.append(q['text']);asked.add(signature)
    state['asked']=sorted(asked)
    lines+=fresh
    if not fresh and state['pending']:
        lines.append('Pour continuer : complétez les points déjà signalés dans les brouillons ; les autres informations sont conservées.')
    if state.get('naming_convention'):
        lines.append('Convention de code conservée pour cette conversation ; les codes proposés restent à vérifier dans Sage.')
    if state.get('naming_errors'):
        lines.append('La convention ne peut pas être appliquée à tous les codes : catégorie manquante ou longueur maximale de 20 caractères dépassée. Les codes concernés sont conservés.')
    if not state['pending']:
        blockers={b for a in articles for b in a.get('checks',{}).get('creation_blockers',[])}
        explanations={'test_article_code_required':'Le parcours de test exige un code commençant par TEST ; le code proposé est conservé sans modification.',
            'supplier_write_mapping_not_supported':'Le fournisseur peut être confirmé et vérifié, mais son association en écriture n’est pas encore prise en charge par le parcours PowerShell.',
            'stock_write_mapping_not_supported':'Le choix « Non géré » est conservé ; son mapping en écriture n’est pas encore pris en charge par ce parcours.',
            'site_201_explicit_required':('Le site 201 figure bien parmi les sites demandés. Le connecteur actuel ne traite pas cette demande multi-site ; les sites demandés restent conservés.' if any('201' in a.get('requested_sites',[]) for a in articles) else 'Le site 201 doit être explicitement indiqué.'),
            'web_test_requires_NEG_UN':'Le parcours de test accepte uniquement la catégorie NEG et les unités UN.'}
        if blockers:
            from app.services.article_execution import reason
            lines.append('Préparation de création bloquée : '+' '.join(explanations.get(b,reason(b)) for b in sorted(blockers)))
            if 'article_security_pending' in blockers:
                from app.services.article_execution import security_controls
                lines.extend(c['label']+' Action : '+c['action'] for c in security_controls(crud.security('articles','create')))
        elif all(a.get('checks',{}).get('valid_basic') for a in articles):
            from app.services.article_execution import legacy_scope
            if any(not legacy_scope(a) for a in articles):
                lines.append('Les informations du brouillon sont vérifiées. La préparation des données exactes reste soumise aux règles métier, puis à une approbation spécifique. Un « oui » dans le chat ne déclenche pas de SAVE.')
            else:lines.append('Les informations sont vérifiées. Utilisez « Confirmer ce brouillon », puis « Préparer la création ». Un « oui » dans le chat ne déclenche pas de SAVE.')
    created=[a['code_article'] for a in articles if (a.get('outcome') or {}).get('confirmed')]
    if created:lines.append('Fiches déjà créées et vérifiées conservées : '+', '.join(created)+'. Les autres préparations ne constituent pas des créations confirmées.')
    elif any((a.get('operation') or {}).get('status') in ('executing','ambiguous','unverified','failed') for a in articles):lines.append('Une tentative antérieure reste à vérifier. Aucune nouvelle tentative automatique.')
    else:lines.append('Les fiches restent des brouillons. Aucune création Sage X3 n’a été exécutée.')
    if state.get('partners'):lines.append(partners.compose(state))
    from app.services.chat_multi_operations import compose as compose_operations
    operations=compose_operations(state)
    if operations:lines.append(operations)
    if catalogue_text:lines.append(catalogue_text)
    return '\n\n'.join(lines)

def validate_message(text):
    if secret_message(text):raise crud.CrudError('Ne transmettez aucun mot de passe ou jeton dans le chat.',422)
    if settings.learning_enabled:
        from app.services.learning import SECRET
        if SECRET.search(text):raise crud.CrudError('Ne transmettez aucun mot de passe, clé ou jeton dans le chat.',422)
    from app.services.knowledge import suspicious
    if suspicious(text):
        # A quoted malicious sentence explicitly presented as untrusted mail
        # data is not a request to obey it. Secrets remain rejected above.
        outside=re.sub(r'«[^»]*»|“[^”]*”|"[^"]*"','[citation]',text)
        quoted_data=outside!=text and re.search(r'\b(?:mail|document|phrase|texte)\b',normalize(text)) and re.search(r'\b(?:pas un ordre|pas une instruction|comme du texte|comme des donnees|n.execute|ne.*execut|ne.*suis|traite.la)\b',normalize(text))
        if not quoted_data or suspicious(outside):raise crud.CrudError('Instruction technique non autorisée : reformulez uniquement la demande métier.',422)


def reserve_analysis(owner,identifier,text,revision,request_id=None):
    validate_message(text)
    marker=str(uuid4())
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True)
        state=row['state'];previous=state.get('analysis_job',{})
        request_hash=hashlib.sha256(text.encode()).hexdigest()
        if request_id and previous.get('request_id')==str(request_id):
            if previous.get('request_sha256')!=request_hash:raise crud.CrudError('request_id_content_mismatch',409)
            return previous
        if row['revision']!=revision:raise crud.CrudError('Conversation modifiée : rechargez-la.',409)
        if state.get('_pending'):
            from app.services.chat_jobs import TASKS
            previous_task=TASKS.get(str(previous.get('id')))
            active=state['_pending'].get('id') in ACTIVE_ANALYSES or previous_task is not None and not previous_task.done()
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(state['_pending']['at'])).total_seconds()
            just_reserved=previous.get('worker_instance')==ANALYSIS_INSTANCE and age<5 and previous.get('status') in ('queued','extracting')
            if active or just_reserved:raise crud.CrudError('Une réponse est déjà en cours.',409)
            state.pop('_pending',None)
            state['last_analysis_recovery']={'job_id':previous.get('id'),'reason':'inactive_read_only_analysis','at':datetime.now(timezone.utc).isoformat()}
        now=datetime.now(timezone.utc).isoformat()
        message_id=append(conn,identifier,'user',text)
        job={'id':str(uuid4()),'request_id':str(request_id or uuid4()),'request_sha256':request_hash,
             'request_message_id':message_id,'status':'queued','phase':'queued','attempts':0,
             'checkpoint':None,'created_at':now,'updated_at':now,'sage_writes':0,'worker_instance':ANALYSIS_INSTANCE}
        state['analysis_job']=job;state['_pending']={'id':marker,'at':now}
        save_conversation_context(conn,owner,identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
        return job


def checkpoint_analysis(owner,identifier,marker,phase,changed=None,delta=None,provenance=None):
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True);state=row['state']
        if state.get('_pending',{}).get('id')!=marker:raise crud.CrudError('obsolete_analysis_attempt',409)
        job=state['analysis_job'];job.update(phase=phase,status=phase,updated_at=datetime.now(timezone.utc).isoformat())
        if delta is not None:job.update(checkpoint='extracted',delta=delta.model_dump(exclude_none=True,exclude_unset=True),provenance=provenance)
        if changed is not None:
            changed['analysis_job']=job;changed['_pending']=state['_pending'];state=changed
        save_conversation_context(conn,owner,identifier,state)


@ai_provider.scoped
@performance.measured
async def send(owner,identifier,text,revision,_job_id=None):
    service_started=perf_counter()
    validate_message(text)
    if not _job_id and settings.sage_powershell_chat_enabled:
        from app.services.sage_article_sites import capture
        captured=await run_in_threadpool(capture,owner,identifier,text,revision)
        if captured is not None:return captured
    if not _job_id:
        reserved=await run_in_threadpool(reserve_analysis,owner,identifier,text,revision)
        _job_id=reserved['id']
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True);state=row['state'];job=state.get('analysis_job',{})
        if job.get('id')!=str(_job_id) or job.get('status')!='queued':raise crud.CrudError('analysis_job_not_queued',409)
        marker=state['_pending']['id'];job.update(status='extracting',phase='extracting',attempts=job.get('attempts',0)+1,worker_instance=ANALYSIS_INSTANCE)
        ai_provider.CONTEXT.get()['mode']=state.get('ai_mode','auto')
        save_conversation_context(conn,owner,identifier,state)
        history_rows=conn.execute("SELECT role,content FROM chat_messages WHERE conversation_id=%s AND role IN ('user','assistant') ORDER BY id DESC LIMIT 24",(identifier,)).fetchall()[::-1]
        example_rows=conn.execute("SELECT snapshot FROM chat_business_examples WHERE owner_id=%s ORDER BY ts_rank_cd(to_tsvector('simple',snapshot::text),plainto_tsquery('simple',%s)) DESC,id DESC LIMIT 30",(owner,text)).fetchall()
        examples=experiences.relevant(text,example_rows)
    ACTIVE_ANALYSES.add(marker)
    try:
        state.pop('conversation_analysis',None)
        state.pop('native_fallback_reply',None)
        from app.services.conversation_guardrails import welcome_echo
        if welcome_echo(text):
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Vous avez recopié le message d’accueil. Que souhaitez-vous faire : créer, modifier ou rechercher une fiche ?','welcome_echo')
        if state.get('discussion_mode')=='supplier' and state.get('supplier_target','TEST')!='OB' and re.search(r'\b(?:creer?|ajouter?|prepare|preparer)\b.{0,35}\b(?:articles?|clients?)\b',normalize(text)):
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Cette conversation est réservée aux fournisseurs. Utilisez « Nouvelle conversation » pour préparer un article ou un client.')
        if settings.sage_article_sql_enabled and not (settings.conversation_deepseek_primary_enabled and settings.conversation_tool_calling_enabled and ai_provider.cloud_enabled()):
            from app.services.conversation_tools import intake_turn
            literal=await intake_turn(owner,identifier,text,state,history_rows)
            state=literal['state']
            if literal.get('reply'):return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,literal['reply'],literal['phase'])
        if settings.conversation_tool_calling_enabled and settings.ai_provider=='deepseek':
            if settings.learning_enabled:
                from app.services import learning
                state['learning_context']=await run_in_threadpool(learning.retrieve,owner,text)
            from app.services.conversation_tools import turn as tool_turn
            orchestrated=await tool_turn(owner,identifier,text,state,history_rows)
            if orchestrated and (orchestrated.get('fallback') or orchestrated.get('delegate')):state=orchestrated['state']
            elif orchestrated:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,orchestrated['state'],orchestrated['reply'],orchestrated['phase'])
            if settings.conversation_deepseek_primary_enabled and (not orchestrated or orchestrated.get('fallback')):
                from app.services.conversation_tools import intake_turn
                recovered=await intake_turn(owner,identifier,text,state,history_rows)
                state=recovered['state']
                if recovered.get('reply'):return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,recovered['reply'],recovered['phase'])
        if state.get('supplier_target')=='OB':
            if not re.search(r'\b(?:modifi\w*|chang\w*|desactiv\w*|reactiv\w*|activ\w*|cherch\w*|consult\w*|verifi\w*)\b',normalize(text)) and (state.get('active_supplier_task') or 'create')=='create':
                from app.services import supplier_dialogue as production_dialogue
                recovered=await run_in_threadpool(production_dialogue.handle,text,state,history_rows)
                if not recovered:
                    # Production must reach the same literal email/form reader
                    # as TEST when the native provider delegates or is unavailable.
                    from app.services.supplier_chat_flow import extract as supplier_extract
                    from app.services.chat_partners import merge as merge_suppliers
                    literal_supplier=await run_in_threadpool(supplier_extract,text,state,history_rows)
                    if literal_supplier and literal_supplier[0].fournisseurs and not literal_supplier[0].articles and not literal_supplier[0].clients:
                        changed=merge_suppliers(state,literal_supplier[0],literal_supplier[1])
                        recovered={'state':changed,'prepare':True}
                if recovered:
                    from app.services.supplier_chat_flow import prepare_state
                    changed=recovered['state'];reply=recovered.get('reply')
                    if recovered.get('prepare'):reply=await run_in_threadpool(prepare_state,changed)
                    return await run_in_threadpool(finish_dialogue,owner,identifier,marker,changed,reply,'production_supplier_fallback')
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,state.get('native_fallback_reply') or 'Le service IA ne permet pas de terminer cette demande dans Production OB. Vos brouillons sont conserves. Aucune operation ne sera reportee dans TEST. Vous pouvez reessayer dans cette conversation.','production_scope_fallback')
        short=normalize(text).strip(' .!?')
        from app.services.conversation_transitions import turn as transition_turn
        transition=await run_in_threadpool(transition_turn,text,state)
        if transition:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,transition['state'],transition['reply'],'conversation_question')
        if re.fullmatch(r'(?:cv|ca va|comment ca va)',short):
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Ça va, merci ! Et vous ?','conversation_question')
        if re.fullmatch(r'(?:bonjour[, ]+)?(?:je (?:veux|souhaite|voudrais) |merci de )?(?:creer|ceer|crrer|ajouter|preparer) (?:un |une |le |des? )?articles?',short):
            if state.get('discussion_mode')=='supplier' and state.get('supplier_target','TEST')!='OB':
                return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Ouvrez une nouvelle conversation pour préparer un article ; celle-ci est réservée aux fournisseurs.','conversation_question')
            state['pending_creation']={'resource':'article','expected':['code_article','designation'],'source':'user_explicit'}
            if state.get('supplier_tasks'):state['active_supplier_task']='idle';state['supplier_tasks']['active']='idle'
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Quel est le code et la désignation de l’article à créer ?','conversation_question')
        if settings.learning_enabled:
            from app.services import learning
            state['learning_context']=await run_in_threadpool(learning.retrieve,owner,text)
            if state['learning_context']['requires_live_data']:tools.invalidate_cache()
        from app.services import supplier_tasks
        task_turn=await run_in_threadpool(supplier_tasks.route,text,state,history_rows)
        if task_turn:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,task_turn['state'],task_turn['reply'],task_turn['phase'])
        if settings.sage_modification_enabled and supplier_tasks.existing_update_target(text,state):
            from app.services.modification_dialogue import turn as modification_turn
            modification=await run_in_threadpool(modification_turn,owner,identifier,text,state,history_rows)
            if modification:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,modification['state'],modification['reply'],'modification_preview')
        if settings.conversation_analysis_enabled and settings.ai_provider=='deepseek' and state.get('conversation_analysis',{}).get('reason')!='native_provider_unavailable':
            from app.services.conversation_analysis import analyse
            state['conversation_analysis']=await analyse(text,state,history_rows)
        if state.get('supplier_tasks') and state.get('conversation_analysis',{}).get('analysis',{}).get('intent') not in ('CREATE_ARTICLE','UPDATE_ARTICLE'):
            task_turn=await run_in_threadpool(supplier_tasks.apply_analysis,text,state)
            if task_turn:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,task_turn['state'],task_turn['reply'],task_turn['phase'])
        mcp_result=None
        if settings.sage_mcp_enabled:
            from app.mcp_sage.client import turn as mcp_turn
            mcp_result=await mcp_turn(owner,identifier,text,state,history_rows)
        if mcp_result:
            from app.mcp_sage.client import references as mcp_references
            state['last_mcp_read']={'calls':mcp_result['calls'],'tools':[r.get('tool') for r in mcp_result['results']],'references':mcp_references(mcp_result['results']),'authority':'data_only','writes':0,'elapsed_ms':mcp_result.get('elapsed_ms')}
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,mcp_result['reply'],'mcp_read')
        if settings.sage_modification_enabled:
            from app.services.supplier_multiturn import explicit_supplier_creation
            if explicit_supplier_creation(text):state.pop('modification_pending_target',None)
            from app.services.modification_dialogue import turn as modification_turn
            modification=await run_in_threadpool(modification_turn,owner,identifier,text,state,history_rows)
            if modification:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,modification['state'],modification['reply'],'modification_preview')
        if settings.sage_article_sql_enabled:
            from app.services.article_sql_dialogue import category_turn
            category_result=await run_in_threadpool(category_turn,text,state)
            if category_result:return await run_in_threadpool(finish_dialogue,owner,identifier,marker,category_result['state'],category_result['reply'],'category_sql_preview')
        from app.services import chat_documents
        document_turn=await run_in_threadpool(chat_documents.turn,owner,identifier,text,state)
        if document_turn:
            changed=document_turn['state'];reply=document_turn.get('reply')
            if document_turn.get('prepare'):
                from app.services.supplier_chat_flow import prepare_state
                await run_in_threadpool(checkpoint_analysis,owner,identifier,marker,'verifying',changed)
                reply=await run_in_threadpool(prepare_state,changed)
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,changed,reply,'document_review')
        from app.services import learning_corrections
        dialogue=await run_in_threadpool(learning_corrections.resolve,text,state)
        if not dialogue:dialogue=await run_in_threadpool(learning_corrections.handle,text,state)
        if not dialogue and state.get('conversation_analysis',{}).get('status')=='validated':
            from app.services.conversation_analysis import supplier_turn
            try:dialogue=await run_in_threadpool(supplier_turn,text,state)
            except ValueError as exc:
                from app.services.chat_diagnostics import record
                state['conversation_analysis'].update(status='rejected',diagnostic_id=record(exc,'semantic_supplier_merge',identifier,_job_id))
        if not dialogue:dialogue=await run_in_threadpool(supplier_dialogue.handle,text,state,history_rows)
        if dialogue:
            from app.services.supplier_chat_flow import prepare_state
            changed=dialogue['state'];reply=dialogue.get('reply')
            chat_documents.reconcile(changed)
            if settings.learning_enabled:
                from app.services.learning_signals import record as correction_signal
                await run_in_threadpool(correction_signal,owner,identifier,state,changed,text)
            if dialogue.get('prepare'):
                await run_in_threadpool(checkpoint_analysis,owner,identifier,marker,'verifying',changed)
                reply=chat_documents.question(changed) if (changed.get('document_review') or {}).get('items') else await run_in_threadpool(prepare_state,changed)
                from app.services.conversation_analysis import checked_supplier_reply
                reply=checked_supplier_reply(changed,reply)
            if settings.sage_article_sql_enabled and changed.get('articles') and not changed.get('partners'):
                from app.services.article_sql_dialogue import prepare_state as prepare_sql_articles
                reply=await run_in_threadpool(prepare_sql_articles,changed,text,state)
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,changed,reply)
        if settings.learning_enabled:
            from app.services.learning_chat import turn as memory_turn
            memory_result=await run_in_threadpool(memory_turn,owner,identifier,text)
        else:memory_result=None
        document_reply=learning.document_answer(state.get('learning_context',{}),text) if settings.learning_enabled else None
        if settings.learning_enabled:
            from app.services.learning_live import answer as live_answer
            live_reply=await run_in_threadpool(live_answer,text)
            if live_reply:document_reply=live_reply
        if memory_result or document_reply:
            with db.connection() as conn:
                current=get_row(conn,owner,identifier,True);saved=current['state']
                if saved.get('_pending',{}).get('id')!=marker:raise crud.CrudError('obsolete_analysis_attempt',409)
                saved.pop('_pending',None);saved['learning_context']=state.get('learning_context',{})
                saved['analysis_job'].update(status='completed',phase='memory_dialogue' if memory_result else 'validated_document_response')
                if memory_result and memory_result.get('items') and not memory_result.get('listing'):saved['memory_focus']=str(memory_result['items'][-1]['id'])
                save_conversation_context(conn,owner,identifier,saved)
                reply=memory_result['text'] if memory_result else document_reply
                append(conn,identifier,'assistant',reply,{'memory_items':[str(i['id']) for i in memory_result.get('items',[])] if memory_result else [],'memory_dialogue':bool(memory_result),'training_performed':False})
            return read(owner,identifier)
        if settings.ai_provider=='deepseek':
            from app.services import natural_dialogue
            if natural_dialogue.eligible(text,state) and state.get('conversation_analysis',{}).get('reason')!='native_provider_unavailable':
                reply=await natural_dialogue.reply(text,state,history_rows)
                return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,reply,'natural_conversation')
        if job.get('checkpoint')=='extracted':
            delta=model.Delta.model_validate(job['delta']);provenance=job.get('provenance',{});changed=copy.deepcopy(state)
            performance.put('extraction_route','persisted_checkpoint_resume')
            if not state.get('partners') and not state.get('articles') and 'fournisseur' in normalize(text):
                from app.services.supplier_chat_flow import extract as supplier_extract
                recovered=supplier_extract(text,state,history_rows)
                if not recovered:
                    with db.connection() as conn:
                        originals=conn.execute("SELECT role,content FROM chat_messages WHERE conversation_id=%s AND role='user' AND content ILIKE %s AND content ILIKE %s ORDER BY id DESC LIMIT 4",(identifier,'%ice%','%fournisseur%')).fetchall()[::-1]
                    recovered=supplier_extract(text,state,originals)
                if recovered:
                    delta,grounding=recovered;changed=merge(state,delta,grounding)
                    await run_in_threadpool(checkpoint_analysis,owner,identifier,marker,'extracted',changed,delta,provenance)
        else:
            start=perf_counter()
            from app.services.supplier_chat_flow import extract as supplier_extract
            supplier_turn=supplier_extract(text,state,history_rows)
            article_sql_turn=None
            if settings.sage_article_sql_enabled:
                from app.services.article_sql_dialogue import initial as sql_article_initial
                article_sql_turn=sql_article_initial(text,state)
            if settings.learning_enabled:
                remembered=learning.exact_delta(state.get('learning_context',{}),text)
                if remembered is not None:supplier_turn=(remembered,text)
            if not supplier_turn and not state.get('partners') and re.fullmatch(r'(?:une |la )?nouvelle fiche fournisseur[.!\s]*',normalize(text).strip()):
                # Recover the original labelled request even after several clarification turns.
                with db.connection() as conn:
                    original_rows=conn.execute("SELECT role,content FROM chat_messages WHERE conversation_id=%s AND role='user' AND content ILIKE %s AND content ILIKE %s ORDER BY id DESC LIMIT 4",(identifier,'%ice%','%fournisseur%')).fetchall()[::-1]
                supplier_turn=supplier_extract(text,state,original_rows)
            merge_text=text
            if article_sql_turn and (not supplier_turn or article_sql_turn[0].intent=='update'):
                delta,merge_text=article_sql_turn;provenance={'route':'article_sql_literal','real_model_called':False}
            elif supplier_turn:
                delta,merge_text=supplier_turn;provenance={'route':'supplier_preserved_literal','real_model_called':False}
            else:
                if state.get('conversation_analysis',{}).get('status') in ('fallback','rejected'):
                    from app.services.ai_recovery import recover
                    preserved,reply=recover(text,state)
                    # A free-form local reply has not executed or validated
                    # business tools. Keep the grounded recovery for ERP work.
                    business_context=bool(state.get('articles') or state.get('partners') or state.get('article_intake_pending') or re.search(r'\b(?:articles?|fourn\w*|sage|categorie|catigonier)\b',normalize(text)))
                    if not business_context:reply=state.get('native_fallback_reply') or reply
                    return await run_in_threadpool(finish_dialogue,owner,identifier,marker,preserved,reply,'ai_recovery')
                delta,provenance=await model.extract(text,state,history_rows,examples)
            if state.get('discussion_mode')=='supplier' and state.get('supplier_target','TEST')!='OB' and (delta.articles or delta.clients):
                return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,'Cette conversation est réservée aux fournisseurs. Utilisez « Nouvelle conversation » pour préparer un article ou un client.')
            if state.get('discussion_mode')=='supplier' and state.get('supplier_target','TEST')!='OB' and delta.intent=='other' and not delta.fournisseurs and not delta.shared.model_dump(exclude_none=True,exclude_unset=True):
                from app.services.supplier_discourse import OFF_TOPIC_REPLY
                return await run_in_threadpool(finish_dialogue,owner,identifier,marker,state,OFF_TOPIC_REPLY)
            performance.add('extraction_ms',(perf_counter()-start)*1000)
            changed=merge(state,delta,merge_text)
            chat_documents.reconcile(changed)
            supplier_dialogue.remember_changes(state,changed,text)
            if settings.learning_enabled:
                from app.services.learning_signals import record as correction_signal
                await run_in_threadpool(correction_signal,owner,identifier,state,changed,text)
            await run_in_threadpool(checkpoint_analysis,owner,identifier,marker,'extracted',changed,delta,provenance)
        if changed.get('partners') and not changed.get('articles') and all(p.get('kind')=='supplier' for p in changed['partners']):
            from app.services.supplier_chat_flow import prepare_state
            response=chat_documents.question(changed) if (changed.get('document_review') or {}).get('items') else await run_in_threadpool(prepare_state,changed)
            changed.pop('_pending',None)
            with db.connection() as conn:
                current=get_row(conn,owner,identifier,True)
                if current['state'].get('_pending',{}).get('id')!=marker:raise crud.CrudError('obsolete_analysis_attempt',409)
                changed['analysis_job']=current['state']['analysis_job']
                changed['analysis_job'].update(status='completed',phase='supplier_sql_prepared',updated_at=datetime.now(timezone.utc).isoformat())
                save_conversation_context(conn,owner,identifier,changed)
                append(conn,identifier,'assistant',response,{'supplier_sql_preview_only':True,'sage_writes':0})
            return read(owner,identifier)
        names=[a.get('designation','') for a in changed.get('articles',[])]
        await performance.emit('understanding',{'text':'Demande comprise : '+', '.join(names)+'. Vérification des référentiels Sage X3…','validation_pending':True})
        if re.search(r'\b(?:actualise|rafra.chis)\b',text,re.I):tools.invalidate_cache()
        await run_in_threadpool(checkpoint_analysis,owner,identifier,marker,'verifying')
        if settings.sage_article_sql_enabled and changed.get('articles') and not changed.get('partners') and not changed.get('last_turn',{}).get('readonly'):
            from app.services.article_sql_dialogue import prepare_state as prepare_sql_articles
            reply=await run_in_threadpool(prepare_sql_articles,changed,text,state)
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,changed,reply,'article_sql_preview')
        plan,bindings=tool_plan(changed)
        partner_bindings=partners.tool_plan(changed,plan)
        results=await run_in_threadpool(tools.run,plan.calls)
        if changed.get('lookup_requests',{}).get('catalogue_categories'):
            key=tools.key('get_article_categories',{'Category':'','Label':'','Site':''})
            changed['catalogue_results']=results.get(plan.cache[key],{'ok':False,'rows':[]})
            changed['lookup_requests'].pop('catalogue_categories',None)
        else:changed.pop('catalogue_results',None)
        offset=len(plan.calls)
        for a in changed['articles']:
            previous=results.get(bindings[a['id']]['duplicate'],{})
            readonly_turn=changed.get('last_turn',{}).get('readonly') or changed.get('last_turn',{}).get('restricted')
            if previous.get('ok') and previous.get('rows') and a['sources'].get('code_article')=='application_proposal_not_reserved' and not readonly_turn:
                invalidate(a);a['code_article']=a['code_article'][:15]+'-'+uuid4().hex[:4].upper()
                bindings[a['id']]['duplicate']=tools.check_article_duplicate(plan,a['code_article'])
                if a.get('code_fournisseur'):
                    a['reference_interne']=(a['code_fournisseur']+'-'+a['code_article'].replace('-XPS',''))[:50]
        if len(plan.calls)>offset:results.update(await run_in_threadpool(tools.run,plan.calls[offset:]))
        offset=len(plan.calls)
        for article in changed['articles']:
            refs=bindings[article['id']]
            if article.get('taux_tva'):
                for tax_rate_row in results.get(refs.get('taxes'),{}).get('rows',[]):
                    code=str(tax_rate_row.get('VAT_0') or '').strip()
                    if code:refs['requested_tax_determination_'+code]=plan.add('get_tax_determination_by_vat',Code=code)
        if len(plan.calls)>offset:results.update(await run_in_threadpool(tools.run,plan.calls[offset:]))
        # Resolve contextual references from actual category/site rows, without
        # treating a matching tax rate or historical account as an applicable rule.
        offset=len(plan.calls)
        for a in changed['articles']:
            refs=bindings[a['id']]
            category=results.get(refs['category'],{}).get('rows',[])
            levels={r.get('VACITM_0','').strip() for r in category if r.get('VACITM_0','').strip()}
            if a.get('niveau_taxe'):levels={a['niveau_taxe']}
            if len(levels)==1:refs['tax_determination']=plan.add('get_tax_determination',Level=next(iter(levels)))
            site=results.get(refs['site'],{}).get('rows',[])
            if a.get('taux_tva') and a.get('site') and len(site)==1:
                refs['taxes_for_company']=tools.get_tax_rules(plan,a['taux_tva'],site[0].get('LEGCPY_0','').strip())
            if a.get('categorie') and not results.get(refs['similar'],{}).get('rows'):
                term='XPS' if re.search(r'\bXPS\b',a.get('designation',''),re.I) else ' '.join(a.get('designation','').split()[:2])[:70]
                refs['similar_other_categories']=tools.search_articles(plan,term)
            if a.get('categorie') and not category:
                refs['category_all_sites']=tools.get_article_categories(plan,a['categorie'])
                refs['available_categories']=tools.get_article_categories(plan,'',site=a.get('site') or '')
            if a.get('site') and not site:refs['available_sites']=tools.get_sites(plan,'')
        if len(plan.calls)>offset:results.update(await run_in_threadpool(tools.run,plan.calls[offset:]))
        offset=len(plan.calls)
        for a in changed['articles']:
            refs=bindings[a['id']]
            rows=results.get(refs['similar'],{}).get('rows',[])+results.get(refs.get('similar_other_categories'),{}).get('rows',[])
            for r in rows:
                code=(r.get('ACCCOD_0') or '').strip();level=(r.get('VACITM_0') or '').strip()
                if code:refs['suggested_accounting_'+code]=tools.get_accounting_categories(plan,code=code)
                if level:refs['suggested_tax_level_'+level]=plan.add('get_tax_determination',Level=level)
        if len(plan.calls)>offset:results.update(await run_in_threadpool(tools.run,plan.calls[offset:]))
        offset=len(plan.calls)
        for a in changed['articles']:
            refs=bindings[a['id']]
            levels=[key for key in refs if key.startswith('suggested_tax_level_')]
            for key in levels:
                for tax_row in results.get(refs[key],{}).get('rows',[]):
                    code=(tax_row.get('VAT_0') or '').strip()
                    if code:refs['suggested_tax_code_'+code]=tools.get_tax_rules(plan,code=code)
        if len(plan.calls)>offset:results.update(await run_in_threadpool(tools.run,plan.calls[offset:]))
        await performance.emit('drafts',{'text':'Préparation des brouillons à partir des résultats vérifiés…'})
        changed=prepare_article_draft(changed,results,bindings)
        changed=partners.validate(changed,results,partner_bindings)
        from app.services.chat_multi_operations import plan as dependency_plan
        changed=dependency_plan(changed)
        compose_start=perf_counter()
        response=compose(changed,delta.intent=='new',state);changed.pop('_pending',None)
        performance.add('response_compose_ms',(perf_counter()-compose_start)*1000)
        with db.connection() as conn:
            current=get_row(conn,owner,identifier,True)
            if current['state'].get('_pending',{}).get('id')!=marker:raise crud.CrudError('Réponse obsolète ignorée.',409)
            changed['analysis_job']=current['state']['analysis_job']
            incomplete=any(not result.get('ok') for result in results.values())
            changed['analysis_job'].update(status='verification_incomplete' if incomplete else 'completed',phase='verification_incomplete' if incomplete else 'review_required',updated_at=datetime.now(timezone.utc).isoformat(),
                performance=dict(performance.CURRENT.get() or {}))
            save_conversation_context(conn,owner,identifier,changed)
            if row['title']=='Nouvelle conversation':conn.execute('UPDATE chat_conversations SET title=%s WHERE id=%s',(text[:80],identifier))
            append(conn,identifier,'tool','Consultations SQL contrôlées',{'calls':plan.calls,'results':results,'writes':0,'real_sql':bool(results) and all(r.get('source') in ('SQL TEST','SQL OB') for r in results.values())})
            append(conn,identifier,'assistant',response,{'delta':delta.model_dump(exclude_none=True,exclude_unset=True),'provenance':provenance,'articles':changed['articles'],'historical_examples_not_rules':len(examples)})
        from app.services.chat_general_articles import maybe_prepare
        return await run_in_threadpool(maybe_prepare,owner,identifier,delta.intent=='new' and not changed.get('last_turn',{}).get('readonly'))
    except (Exception,asyncio.CancelledError) as exc:
        from app.services.chat_diagnostics import record
        diagnostic_id=record(exc,state.get('analysis_job',{}).get('phase','unknown'),identifier,_job_id)
        if getattr(exc,'sqlstate',None)=='P2001':
            from app.services.chat_storage import release_failed_analysis
            await run_in_threadpool(release_failed_analysis,owner,identifier)
            raise
        if isinstance(exc,(ValueError,httpx.HTTPError,asyncio.CancelledError)) and supplier_dialogue.supplier_intent(text,state):
            import logging
            diagnostic=diagnostic_id
            logging.getLogger('agent_sage.chat').warning('supplier_dialogue_fallback diagnostic=%s error=%s',diagnostic,type(exc).__name__)
            retained=await run_in_threadpool(retained_dialogue_state,owner,identifier)
            preserved,reply=supplier_dialogue.fallback(text,retained)
            preserved['dialogue_diagnostic']=diagnostic
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,preserved,reply+' Référence : '+diagnostic,'supplier_followup_required')
        if isinstance(exc,(ValueError,httpx.HTTPError)):
            from app.services.ai_recovery import recover
            retained=await run_in_threadpool(retained_dialogue_state,owner,identifier)
            preserved,reply=recover(text,retained)
            return await run_in_threadpool(finish_dialogue,owner,identifier,marker,preserved,reply,'ai_recovery')
        performance.put('fastapi_service_ms',round((perf_counter()-service_started)*1000,3))
        with db.connection() as conn:
            row=get_row(conn,owner,identifier,True);state=row['state']
            if state.get('_pending',{}).get('id')==marker:
                state.pop('_pending',None)
                phase=state.get('analysis_job',{}).get('phase','extracting')
                state.setdefault('analysis_job',{}).update(status='interrupted' if isinstance(exc,asyncio.CancelledError) else 'failed',
                    failed_phase=phase,error_type=type(exc).__name__,diagnostic_id=diagnostic_id,timeout_phase=getattr(exc,'phase',None),performance=dict(performance.CURRENT.get() or {}),updated_at=datetime.now(timezone.utc).isoformat())
                save_conversation_context(conn,owner,identifier,state)
                failure={'error_type':type(exc).__name__,'diagnostic_id':diagnostic_id,'phase':phase,'performance':dict(performance.CURRENT.get() or {})}
                if 'delta' in locals():
                    failure['delta']=delta.model_dump(exclude_none=True,exclude_unset=True)
                    failure['provenance']=provenance
                message='Le traitement n’a pas pu se terminer. Votre demande et les informations reconnues sont conservées. Vous pouvez continuer dans le chat.'
                append(conn,identifier,'assistant',message+' Aucune écriture Sage n’a été effectuée.',failure)
        raise
    finally:ACTIVE_ANALYSES.discard(marker)

def review_partner(owner,identifier,partner_id,revision):
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state']
        if state.get('_pending') or state.get('workflow')=='cancelled':raise crud.CrudError('draft_not_reviewable',409)
        p=next((p for p in state.get('partners',[]) if p['id']==str(partner_id)),None)
        if not p:raise crud.CrudError('partner_not_found',404)
        if p.get('reviewed'):raise crud.CrudError('already_reviewed',409)
        if not p.get('checks',{}).get('valid_basic'):raise crud.CrudError('partner_checks_incomplete',409)
        p['reviewed']=True
        for value in p.get('field_states',{}).values():
            if value.get('status')=='declared':value['status']='confirmed'
        conn.execute('INSERT INTO chat_business_examples(owner_id,conversation_id,snapshot) VALUES (%s,%s,%s)',(owner,identifier,Jsonb(experiences.snapshot(p,state,partners.FIELDS,settings.ollama_model))))
        save_conversation_context(conn,owner,identifier,state)
        append(conn,identifier,'system','Interprétation du brouillon tiers relue ; aucune création autorisée.',{'partner_id':str(partner_id),'human_review_not_write_approval':True})
    return read(owner,identifier)


def review(owner,identifier,article_id,revision):
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state'];a=next((a for a in state['articles'] if a['id']==str(article_id)),None)
        if state.get('_pending'):raise crud.CrudError('analysis_in_progress',409)
        if state.get('workflow')=='cancelled':raise crud.CrudError('Demande annulée : reprise explicite requise.',409)
        if not a:raise crud.CrudError('article_not_found',404)
        if a.get('reviewed'):raise crud.CrudError('Brouillon déjà relu pour cette version.',409)
        if not a.get('checks',{}).get('valid_basic'):raise crud.CrudError('Corrigez les informations non vérifiées avant de valider le brouillon.',409)
        a['reviewed']=True
        conn.execute('INSERT INTO chat_business_examples(owner_id,conversation_id,snapshot) VALUES (%s,%s,%s)',(owner,identifier,Jsonb(experiences.snapshot(a,state,FIELDS,settings.ollama_model))))
        save_conversation_context(conn,owner,identifier,state)
        append(conn,identifier,'system','Brouillon relu par l’opérateur ; ce n’est pas une autorisation d’écriture.',{'article_id':str(article_id),'source':'human_reviewed_example_not_rule'})
    return read(owner,identifier)

def write_action(owner,identifier,article_id,action,revision,confirm=False,site=None):
    if settings.sage_mcp_enabled and action in ('approve','execute','site-approve','site-execute'):
        raise crud.CrudError('Pilote MCP en lecture seule : aucune écriture Sage autorisée.',423)
    with db.connection() as conn:
        if get_row(conn,owner,identifier)['state'].get('pending_correction'):
            raise crud.CrudError('Confirmez ou refusez la correction proposée dans le chat avant toute création.',423)
    if action.startswith('site-'):
        value=read(owner,identifier)
        article=next((a for a in value['state'].get('articles',[]) if a['id']==str(article_id)),None)
        if settings.sage_article_sql_enabled and article and article.get('operation',{}).get('transport')=='direct_sql_article':
            raise crud.CrudError('Les sites font partie du plan article confirmé. Aucune fiche site supplémentaire ne sera créée par cet ancien parcours.',423)
        if article and article.get('code_article')!='EXT_POUDRE':
            from app.services.chat_general_sites import action as generic_site_action
            return generic_site_action(owner,identifier,article_id,action,revision,confirm,site)
        from app.services.sage_article_sites import action as site_action
        return site_action(owner,identifier,article_id,action,revision,confirm)
    current=read(owner,identifier)
    selected=next((a for a in current['state'].get('articles',[]) if a['id']==str(article_id)),None)
    if selected and selected.get('operation',{}).get('transport')=='direct_sql_article' and not settings.sage_article_sql_enabled:
        raise crud.CrudError('Service SQL articles désactivé. Le brouillon et son résultat sont conservés ; aucun basculement automatique vers une autre méthode.',423)
    if settings.sage_article_sql_enabled and selected and (selected.get('operation',{}).get('transport')=='direct_sql_article' or selected.get('operation',{}).get('status') not in ('executing','succeeded','ambiguous','unverified','failed')):
        from app.services.chat_article_sql_actions import action as sql_article_action
        return sql_article_action(owner,identifier,article_id,action,revision,confirm)
    from app.services.article_execution import legacy_scope
    if selected and not legacy_scope(selected):
        from app.services.chat_general_articles import action as general_action
        return general_action(owner,identifier,article_id,action,revision,confirm)
    if settings.sage_powershell_chat_enabled:
        from app.services.sage_powershell_chat import write_action as powershell_action
        return powershell_action(owner,identifier,article_id,action,revision,confirm)
    if action not in ('prepare','approve','execute'):raise crud.CrudError('unknown_action',422)
    with db.connection() as conn:
        row=get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state'];a=next((a for a in state['articles'] if a['id']==str(article_id)),None)
        if state.get('_pending'):raise crud.CrudError('analysis_in_progress',409)
        if state.get('workflow')=='cancelled':raise crud.CrudError('Demande annulée : reprise explicite requise.',409)
        if not a:raise crud.CrudError('article_not_found',404)
        if not crud.security()['ready']:raise crud.CrudError('Création en attente de configuration Sage',423)
        if a.get('outcome') is not None or (a.get('operation') or {}).get('status') in ['executing','ambiguous','unverified','succeeded','failed']:
            raise crud.CrudError('existing_attempt_requires_readback_no_retry',409)
        if not a.get('reviewed'):raise crud.CrudError('human_review_required',409)
        if a.get('code_fournisseur') or a.get('taux_tva') or a.get('code_tva'):
            raise crud.CrudError('Mapping fournisseur/fiscal et applicabilité métier à valider avant écriture.',409)
        if a.get('compte_general') or (a.get('accounting_category') and not a.get('code_comptable')) or a.get('niveau_taxe'):
            raise crud.CrudError('Correspondance comptable/fiscale de ces champs à valider dans le mapping Sage.',409)
        if any(a.get(k) and a[k]!=a.get('unite') for k in ['unite_achat','unite_vente']):
            raise crud.CrudError('Conversions et mapping des unités distinctes à valider avant écriture.',409)
        if action=='prepare':
            snapshot={**a,'unite':a.get('unite') or ''}
            request_id=db.create_request('Brouillon relu : '+json.dumps(snapshot,ensure_ascii=False),{'source':'chat_human_review'})
            legacy.create(request_id,{'intention':'create_article','articles':[snapshot]})
            d=legacy.Draft(**{k:(snapshot.get(k) or '') for k in legacy.Draft.model_fields})
            legacy.update(request_id,1,d);legacy.validate(request_id,2,True);value=legacy.prepare(request_id,2)
            a['legacy_id']=str(request_id);a['operation']=operation_snapshot(value['operation'])
        elif action=='approve':
            if not confirm or not a.get('legacy_id'):raise crud.CrudError('specific_confirmation_required',409)
            value=legacy.read(UUID(a['legacy_id']));op=value['operation']
            permit=legacy.approve(UUID(a['legacy_id']),value['revision'],Approval(digest=op['digest'],confirm=True,actor='chat:'+str(owner),reason='Confirmation humaine explicite du brouillon affiché dans le chat'))
            checksum=crud.digest({k:a.get(k) for k in FIELDS+['reference_interne']})
            PERMITS[a['id']]={'token':permit['approval_token'],'owner':str(owner),'article_hash':checksum,'operation_id':op['id']}
            a['approved']=True
        else:
            permit=PERMITS.pop(a['id'],None)
            checksum=crud.digest({k:a.get(k) for k in FIELDS+['reference_interne']})
            if not confirm or not permit or permit['owner']!=str(owner) or permit['article_hash']!=checksum:raise crud.CrudError('fresh_specific_approval_required',403)
            value=legacy.read(UUID(a['legacy_id']))
            result=legacy.execute(UUID(a['legacy_id']),value['revision'],Execution(operation_id=permit['operation_id'],approval_token=permit['token']))
            a['outcome']=operation_snapshot(result['outcome']);a['operation']=operation_snapshot(result['operation']);a['approved']=False
            outcome=a['outcome'];operation=a['operation'];code=a.get('code_article','')
            if outcome.get('confirmed') is True:
                message=f'Création confirmée : article {code}, dossier TEST. SOAP read et SQL SELECT concordent. Vérification dans Sage : TEST → GESITM.'
            elif operation.get('status')=='failed':
                message=f'Création refusée par Sage pour {code}, dossier TEST. Consultez les messages et les relectures. Aucun nouvel envoi automatique.'
            else:
                message=f'Création non confirmée pour {code}, dossier TEST. L’article peut avoir été enregistré : vérifiez les relectures Sage et SQL. Aucun nouvel envoi automatique.'
            append(conn,identifier,'assistant',message,{'article_id':a['id'],'confirmed':outcome.get('confirmed') is True,'operation_id':str(operation.get('id','')),'retry_allowed':False})
        save_conversation_context(conn,owner,identifier,state)
        append(conn,identifier,'system','Opération contrôlée : '+action,{'article_id':a['id'],'action':action,'revision':revision})
    return read(owner,identifier)
