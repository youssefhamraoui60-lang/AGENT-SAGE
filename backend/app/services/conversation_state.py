"""Versioned business context for a conversation; never execution authority.

The authoritative records remain in the authenticated PostgreSQL conversation.
This projection is persisted with them, supplied to the model, and downloadable
as JSON. It contains no credentials, permits, SQL plans or provider prompts.
"""
import copy
import json
from datetime import datetime,timezone

VERSION=1
FINISHED={'cancelled','succeeded','executing','failed','ambiguous','unverified'}


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    from app.services.ai_provider import safe
    from app.services.learning import SECRET
    if isinstance(value,str):return SECRET.sub('[REDACTED]',safe(value))
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if value is None or type(value) in (bool,int,float):return value
    return str(value)


def fields(item,names):
    return clean({key:copy.deepcopy(item[key]) for key in names if key in item and item[key] is not None})


def route(state,name,args,result):
    """Record a validated tool outcome, never the model's unvalidated text."""
    if not result.get('ok'):return
    focus=copy.deepcopy(state.get('conversation_focus') or {})
    resource=getattr(args,'resource',None)
    intent={'prepare_draft':'create','select_for_modification':'modify','prepare_modification':'modify',
            'read_sage':'search','search_categories':'search','list_suppliers':'search',
            'get_recent_suppliers':'search','read_live_stock':'stock','cancel_request':'cancel'}.get(name)
    if name=='respond':
        if args.intent!='CHAT':intent=args.intent.lower()
        if args.expected_fields:focus['expected_fields']=list(args.expected_fields)
        resource=resource or ('supplier' if 'SUPPLIER' in args.intent else 'article' if 'ARTICLE' in args.intent else None)
    if intent:
        focus={'intent':intent,'resource':resource,'operation_id':result.get('draft_id'),
               'expected_fields':list(getattr(args,'expected_fields',[])),'source':'validated_tool'}
    if focus:state['conversation_focus']=focus
    event={'at':now(),'turn_id':(state.get('analysis_job') or {}).get('id'),'tool':name,
           'resource':resource,'intent':intent,'operation_id':result.get('draft_id'),
           'code':getattr(args,'code',None),'query':getattr(args,'name',None) or getattr(args,'query',None),
           'status':result.get('status'),'expected_fields':focus.get('expected_fields',[]),'sage_writes':0}
    if name=='prepare_draft':event['parameters']={fact.field:fact.value for fact in args.fields}
    if name=='prepare_modification':event['parameters']={change.field:change.value for change in args.changes}
    state['operation_events']=(state.get('operation_events',[])+[clean(event)])[-100:]


def project(state,identifier=None):
    from app.core.config import settings
    from app.schemas.conversation_entities import SupplierPatch
    from app.services.chat_model import Patch
    folder=state.get('supplier_target','TEST')
    operations={}
    collections=[('partners','create'),('articles','create'),('modification_drafts','modify'),('batch_modification_requests','modify'),('category_drafts','create')]
    containers=[]
    for key in ('supplier_archives','article_archives'):
        containers.extend(a for a in state.get(key,[]) if isinstance(a,dict))
    # Current records supersede their archived versions, keyed by stable draft ID.
    for container in [*containers,state]:
        for collection,kind in collections:
            for item in container.get(collection,[]):
                if not item.get('id'):continue
                resource=item.get('resource') if kind=='modify' else 'article' if collection=='articles' else 'category' if collection=='category_drafts' else item.get('kind','supplier')
                names=SupplierPatch.model_fields if resource in ('supplier','customer') else Patch.model_fields if resource=='article' else ('code','designation','nom_court','modele','unite','code_comptable','taxe')
                if collection=='batch_modification_requests':names=('query','unit','unit_scope')
                operation=item.get('operation') or {}
                changes=fields(item.get('changes') or {},(item.get('changes') or {}).keys())
                action='deactivate' if changes.get('deactivate') else 'activate' if changes.get('activate') else kind
                if type(changes.get('enabled')) is bool:action='activate' if changes['enabled'] else 'deactivate'
                record={'id':str(item['id']),'resource':resource,'action':action,
                        'folder':item.get('dossier_cible',item.get('folder',folder)),
                        'status':operation.get('status','draft'),'parameters':fields(item,names),
                        'target_code':item.get('code') or item.get('code_article'),
                        'changes':changes,'unknown_fields':list(item.get('unknown_fields') or []),
                        'sources':fields(item.get('sources') or {},names),
                        'blockers':clean(item.get('sql_blockers') or ([operation['message']] if operation.get('message') else []))}
                if item.get('declared_site_codes'):record['declared_site_codes']=list(item['declared_site_codes'])
                if kind=='modify':record['current_values']=clean(item.get('current') or {})
                if kind=='modify' and item.get('unit_conversion_requests'):record['unit_conversion_requests']=clean(item['unit_conversion_requests'])
                if kind=='modify' and item.get('unit_conversion_conflicts'):record['unit_conversion_conflicts']=clean(item['unit_conversion_conflicts'])
                if kind=='modify' and item.get('unit_conversion_history'):record['unit_conversion_history']=clean(item['unit_conversion_history'])
                operations[record['id']]=record
    focus=copy.deepcopy(state.get('conversation_focus') or {})
    if state.get('workflow')=='cancelled':focus={'intent':'cancel','resource':None,'operation_id':None,'expected_fields':[],'source':'server'}
    expected=(state.get('_supplier_dialogue') or {}).get('expected_field')
    if expected:focus['expected_fields']=[expected]
    pending=state.get('modification_pending_target')
    if pending:
        focus.update(intent='modify',resource=pending.get('resource'),expected_fields=['target'] if not pending.get('code') and not pending.get('name_query') else focus.get('expected_fields',[]))
    if not focus:
        active=[record for record in operations.values() if record['status'] not in FINISHED]
        if active:
            item=active[-1];focus={'intent':item['action'],'resource':item['resource'],'operation_id':item['id'],'expected_fields':[],'source':'server'}
        elif state.get('article_intake_pending'):focus={'intent':'create','resource':'article','operation_id':None,'expected_fields':['designation'],'source':'server'}
    if focus.get('resource') and not focus.get('operation_id') and focus.get('intent') not in ('search','stock','cancel'):
        candidates=[item for item in operations.values() if item['resource']==focus['resource'] and item['status'] not in FINISHED]
        if len(candidates)==1:focus['operation_id']=candidates[0]['id']
    previous=state.get('operation_context') or {}
    result={'schema_version':VERSION,'conversation_id':str(identifier) if identifier else previous.get('conversation_id'),
            'folder':folder,'authority':'context_only_no_execution_permission',
            'objective':focus,'operations':list(operations.values()),'events':clean(state.get('operation_events',[])),
            'engine':{'configured_provider':settings.ai_provider,
                      'mode':state.get('ai_mode','auto'),'last_provider':(state.get('tool_orchestration') or {}).get('provider'),
                      'fallback_reason':(state.get('tool_orchestration') or {}).get('fallback_reason')},
            'pending_creation':clean(state.get('pending_creation')),
            'pending_modification':fields(pending or {},('resource','code','name_query')),
            'references':{kind:fields(result,('folder','kind','query','rate','choices','total','has_more')) for kind,result in (state.get('article_reference_choices') or {}).items()}}
    comparable=lambda obj:{k:v for k,v in obj.items() if k not in ('updated_at','context_revision')}
    changed=comparable(result)!=comparable(previous)
    result['context_revision']=int(previous.get('context_revision',0))+int(changed)
    result['updated_at']=now() if changed else previous.get('updated_at',now())
    return result


def synchronize(state,identifier=None):
    state['operation_context']=project(state,identifier)
    return state['operation_context']


def export(owner,identifier):
    from app.services import business_store,conversation_chat
    with business_store.connection() as conn:
        row=conversation_chat.get_row(conn,owner,identifier)
    return json.dumps(project(row['state'],identifier),ensure_ascii=False,indent=2)
