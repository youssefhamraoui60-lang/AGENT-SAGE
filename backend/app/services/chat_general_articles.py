"""General TEST article approvals; no demo-name, category or unit exception."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import UUID
import requests
from app.services import business_store as db,sage_crud as crud,chat_tools as tools
from app.services.sage_gateway import Gateway
from app.services.sage_article_rules import load_rules
from app.services.sage_soap import SageError
from app.services.article_mapping import request as article_request
from app.services.article_readback import compare
from app.services.article_execution import blocked_message,reason
from app.schemas.sage_crud import Approval,Execution

PERMITS={}
TERMINAL={'executing','ambiguous','unverified','succeeded','failed'}


def fingerprint(article):
    from app.services.conversation_chat import FIELDS
    return crud.digest({k:article.get(k) for k in FIELDS+['reference_interne','requested_sites']})


def refresh(article):
    from app.services import conversation_chat as chat
    state={'articles':[deepcopy(article)]};plan,bindings=chat.tool_plan(state)
    results=tools.run(plan.calls);refs=bindings[article['id']]
    offset=len(plan.calls)
    for row in results.get(refs.get('taxes'),{}).get('rows',[]):
        code=str(row.get('VAT_0') or '').strip()
        if code:refs['requested_tax_determination_'+code]=plan.add('get_tax_determination_by_vat',Code=code)
    if len(plan.calls)>offset:results.update(tools.run(plan.calls[offset:]))
    value=chat.prepare_article_draft(state,results,bindings)['articles'][0]
    if not value.get('checks',{}).get('valid_basic'):raise crud.CrudError(blocked_message(value,value['checks'].get('errors',[])),409)
    return value


def action(owner,identifier,article_id,step,revision,confirm=False):
    from app.services import conversation_chat as chat
    if step not in ('prepare','approve','execute'):raise crud.CrudError('unknown_action',422)
    snapshot=None;permit=None
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state'];a=next((a for a in state.get('articles',[]) if a['id']==str(article_id)),None)
        if not a:raise crud.CrudError('article_not_found',404)
        if state.get('_pending') or state.get('workflow')=='cancelled':raise crud.CrudError('article_not_ready',409)
        if not crud.security('articles','create')['ready']:raise crud.CrudError(blocked_message(a,['article_security_pending']),423)
        errors=a.get('checks',{}).get('errors',[])
        if errors:raise crud.CrudError(blocked_message(a,errors),409)
        op=a.get('operation') or {}
        if op.get('status') in TERMINAL:raise crud.CrudError('existing_attempt_requires_readback_no_retry',409)
        if step=='prepare':
            if op and op.get('status')!='invalidated':raise crud.CrudError('article_preparation_already_exists',409)
            fresh=refresh(a);desc=Gateway('articles').describe()
            try:
                rules=load_rules(crud.description_hash(desc));request=article_request(fresh,rules)
                operation=crud.prepare('articles',request)
            except SageError as exc:raise crud.CrudError(blocked_message(a,[exc.code]),exc.status) from None
            if not operation.get('checks',{}).get('security',{}).get('ready') or operation.get('checks',{}).get('blockers'):
                operation['status']='blocked';conn.execute("UPDATE soap_operations SET status='blocked',updated_at=now() WHERE id=%s AND status='prepared'",(operation['id'],))
            a['operation']=chat.operation_snapshot(operation);a['operation']['article_hash']=fingerprint(a)
            a['operation']['transport']='strict_generic';a['approved']=False;PERMITS.pop(a['id'],None)
            a.pop('write_status',None)
            chat.append(conn,identifier,'assistant','Données exactes préparées pour '+a['code_article']+'. Relisez-les puis approuvez explicitement la création dans TEST. Aucun SAVE exécuté.',{'article_id':a['id'],'save_sent':False})
        elif step=='approve':
            if confirm is not True or op.get('status')!='prepared' or op.get('article_hash')!=fingerprint(a):raise crud.CrudError('specific_confirmation_required',409)
            refresh(a)
            permission=crud.approve(UUID(op['id']),Approval(digest=op['digest'],confirm=True,actor='chat:'+str(owner),reason='Approbation spécifique des données exactes article présentées dans le chat'))
            PERMITS[a['id']]={'owner':str(owner),'hash':fingerprint(a),'operation_id':op['id'],'token':permission['approval_token'],'expires_at':datetime.now(timezone.utc)+timedelta(minutes=15)}
            a['reviewed']=True;a['approved']=True;op['status']='approved'
        else:
            permit=PERMITS.get(a['id'])
            if (confirm is not True or not a.get('approved') or not permit or permit['owner']!=str(owner)
                or permit['hash']!=fingerprint(a) or op.get('article_hash')!=fingerprint(a) or permit['operation_id']!=op.get('id')
                or permit['expires_at']<=datetime.now(timezone.utc)):raise crud.CrudError('fresh_specific_approval_required',403)
            refresh(a);PERMITS.pop(a['id'],None);a['approved']=False;op['status']='executing'
            snapshot={'id':a['id'],'operation_id':op['id'],'keys':op['record_keys'],'article':deepcopy(a)}
        chat.save_conversation_context(conn,owner,identifier,state)
    if snapshot:
        try:
            operation=crud.execute('articles','create',snapshot['keys'],Execution(operation_id=snapshot['operation_id'],approval_token=permit['token']))
            outcome=compare(operation,snapshot['article'])
        except Exception:
            operation={'id':snapshot['operation_id'],'resource':'articles','action':'create','status':'ambiguous','record_keys':snapshot['keys'],'result':{'retry_allowed':False}}
            outcome={'confirmed':False,'retry_allowed':False,'site_creation_executed':False}
        code=snapshot['article']['code_article']
        text=("CRÉÉ : l’article "+code+" a été créé avec succès dans Sage X3 TEST. Code : "+code+". La fiche a été relue et vérifiée. Aucune fiche article-site n’a été créée par cette opération.") if outcome.get('confirmed') else "RÉSULTAT INCERTAIN : une tentative a été effectuée pour "+code+", mais la création n’est pas confirmée. Les relectures doivent être examinées avant toute nouvelle tentative."
        with db.connection() as conn:
            row=chat.get_row(conn,owner,identifier,True);state=row['state'];a=next(x for x in state['articles'] if x['id']==snapshot['id'])
            operation['transport']='strict_generic';a['operation']=chat.operation_snapshot(operation);a['outcome']=outcome
            chat.save_conversation_context(conn,owner,identifier,state);chat.append(conn,identifier,'assistant',text,{'article_id':a['id'],'confirmed':bool(outcome.get('confirmed')),'retry_allowed':False})
    return chat.read(owner,identifier)


def maybe_prepare(owner,identifier,new_request=False):
    """Read-only automatic preparation, never approval/execution from model text."""
    from app.services import conversation_chat as chat
    from app.services.article_execution import legacy_scope
    value=chat.read(owner,identifier);state=value['state']
    if state.get('workflow')=='cancelled' or state.get('_pending'):return value
    requested=state.get('creation_request',{}).get('article_ids',[])
    if not requested and not new_request:return value
    for article in state.get('articles',[]):
        if requested and article['id'] not in requested:continue
        if legacy_scope(article) or article.get('operation') or article.get('checks',{}).get('errors'):continue
        if not crud.security('articles','create')['ready']:continue
        try:value=action(owner,identifier,article['id'],'prepare',value['revision'])
        except (crud.CrudError,SageError,requests.RequestException) as exc:
            message=(blocked_message(article,['article_connection_unavailable']) if isinstance(exc,requests.RequestException)
                     else exc.code if isinstance(exc,crud.CrudError) else blocked_message(article,[exc.code]))
            with db.connection() as conn:
                row=chat.get_row(conn,owner,identifier,True);current=row['state']
                selected=next(a for a in current['articles'] if a['id']==article['id'])
                selected['write_status']={'status':'blocked','message':message,'save_sent':False}
                chat.save_conversation_context(conn,owner,identifier,current);chat.append(conn,identifier,'assistant',message,{'article_id':article['id'],'save_sent':False})
            value=chat.read(owner,identifier)
    return value
