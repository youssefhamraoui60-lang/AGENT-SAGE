"""Separate strict article-site creation from reviewed per-site TEST templates."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import UUID
from app.services import business_store as db,sage_crud as crud,chat_tools as tools
from app.services.sage_gateway import Gateway
from app.services.sage_article_rules import load_rules
from app.schemas.sage_crud import Preparation,Approval,Execution

PERMITS={}
TERMINAL={'executing','ambiguous','unverified','succeeded','failed'}


def read_sql(code,site):
    return tools.run([{'id':'parent','tool':'get_article_record','args':{'Code':code}},
        {'id':'site','tool':'get_sites','args':{'Site':site}},
        {'id':'child','tool':'get_article_site_record','args':{'Code':code,'Site':site}}])


def action(owner,identifier,article_id,step,revision,confirm=False,site=None):
    from app.services import conversation_chat as chat
    if step not in ('site-prepare','site-approve','site-execute'):raise crud.CrudError('unknown_action',422)
    snapshot=None;permit=None
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state'];a=next((a for a in state.get('articles',[]) if a['id']==str(article_id)),None)
        if not a or state.get('_pending') or state.get('workflow')=='cancelled':raise crud.CrudError('article_not_ready',409)
        if not crud.security('article-sites','create')['ready']:raise crud.CrudError('BLOQUÉ : fiche article-site non créée. Action : valider les droits et la sécurité Sage du parcours article-site.',423)
        site=site or (a.get('requested_sites') or [a.get('site')])[0]
        if not site:raise crud.CrudError('article_site_required',409)
        code=a['code_article'];key=a['id']+':'+site
        children=a.setdefault('strict_site_operations',{});op=children.get(site,{})
        if op.get('status') in TERMINAL:raise crud.CrudError('existing_attempt_requires_readback_no_retry',409)
        if step=='site-prepare':
            if op:raise crud.CrudError('article_site_already_prepared',409)
            checks=read_sql(code,site)
            if not all(checks.get(k,{}).get('ok') for k in ('parent','site','child')):raise crud.CrudError('article_site_sql_checks_incomplete',409)
            if len(checks['parent']['rows'])!=1 or not Gateway('articles').read({'ITMREF':code}).get('exists'):raise crud.CrudError('parent_article_missing',409)
            if checks['child']['rows']:raise crud.CrudError('article_site_already_exists_read_only_review',409)
            desc=Gateway('article-sites').describe();rules=load_rules(crud.description_hash(desc),resource='article-sites')
            template=rules.get('sites',{}).get(site)
            if not template or len(checks['site']['rows'])!=1 or str(checks['site']['rows'][0].get('LEGCPY_0','')).strip()!=template.get('company'):raise crud.CrudError('article_site_rules_unverified',409)
            fields=template.get('fields',{});mapping=template.get('sql_mapping',{})
            if not fields or not all(isinstance(v,str) for v in fields.values()) or not set(template.get('required_fields',[]))<=set(fields) or not set(fields)<=set(mapping):raise crud.CrudError('article_site_fields_unverified',409)
            if not all('.' in p and '[' not in p and '.' not in column for p,column in mapping.items()):raise crud.CrudError('article_site_mapping_unverified',409)
            request=Preparation(action='create',keys={'ITMREF':code,'STOFCY':site},fields=[{'group':p.split('.')[0],'name':p.split('.')[1],'value':v} for p,v in fields.items()])
            operation=crud.prepare('article-sites',request)
            if not operation.get('checks',{}).get('security',{}).get('ready'):operation['status']='blocked'
            operation=chat.operation_snapshot(operation);operation['site_template']=template;operation['template_digest']=crud.digest(template)
            children[site]=operation
        elif step=='site-approve':
            if confirm is not True or op.get('status')!='prepared' or op.get('record_keys')!={'ITMREF':code,'STOFCY':site}:raise crud.CrudError('specific_confirmation_required',409)
            permission=crud.approve(UUID(op['id']),Approval(digest=op['digest'],confirm=True,actor='chat:'+str(owner),reason='Approbation spécifique de cette fiche article-site dans TEST'))
            PERMITS[key]={'owner':str(owner),'operation_id':op['id'],'token':permission['approval_token'],'expires_at':datetime.now(timezone.utc)+timedelta(minutes=15)}
            op['status']='approved'
        else:
            permit=PERMITS.get(key)
            if confirm is not True or op.get('status')!='approved' or op.get('record_keys')!={'ITMREF':code,'STOFCY':site} or not permit or permit['owner']!=str(owner) or permit['operation_id']!=op['id'] or permit['expires_at']<=datetime.now(timezone.utc):raise crud.CrudError('fresh_specific_approval_required',403)
            rules=load_rules(crud.description_hash(Gateway('article-sites').describe()),resource='article-sites')
            if crud.digest(rules.get('sites',{}).get(site))!=op['template_digest']:raise crud.CrudError('article_site_rules_changed',409)
            checks=read_sql(code,site)
            if not all(checks.get(k,{}).get('ok') for k in ('parent','site','child')) or not checks['parent']['rows'] or checks['child']['rows']:raise crud.CrudError('article_site_changed_since_approval',409)
            PERMITS.pop(key,None);op['status']='executing';snapshot={'id':a['id'],'site':site,'code':code,'operation':deepcopy(op)}
        chat.save_conversation_context(conn,owner,identifier,state)
    if snapshot:
        try:
            operation=crud.execute('article-sites','create',{'ITMREF':code,'STOFCY':site},Execution(operation_id=snapshot['operation']['id'],approval_token=permit['token']))
            checks=read_sql(code,site);rows=checks.get('child',{}).get('rows',[]);record=rows[0] if len(rows)==1 else {}
            comparisons={'ITMREF_0':record.get('ITMREF_0')==code,'STOFCY_0':record.get('STOFCY_0')==site}
            template=snapshot['operation']['site_template']
            for path,value in template['fields'].items():
                column=template['sql_mapping'][path];comparisons[column]=record.get(column) is not None and str(record[column]).strip()==str(value).strip()
            verified=operation.get('status')=='succeeded' and operation.get('after_record',{}).get('exists') is True and checks.get('child',{}).get('source')=='SQL TEST' and checks.get('child',{}).get('ok') is True and all(comparisons.values())
        except Exception:operation={'status':'ambiguous'};comparisons={};verified=False
        with db.connection() as conn:
            row=chat.get_row(conn,owner,identifier,True);state=row['state'];a=next(a for a in state['articles'] if a['id']==snapshot['id'])
            a['strict_site_operations'][site]=chat.operation_snapshot({**operation,'confirmed':verified,'sql_comparisons':comparisons,'retry_allowed':False})
            chat.save_conversation_context(conn,owner,identifier,state)
            chat.append(conn,identifier,'assistant',('CRÉÉ ET VÉRIFIÉ : fiche article-site '+code+' / '+site+'. Article maître conservé.') if verified else 'RÉSULTAT INCERTAIN : fiche article-site '+code+' / '+site+' non confirmée. Aucune nouvelle tentative automatique.',{'article_id':a['id'],'site':site,'confirmed':verified,'retry_allowed':False})
    return chat.read(owner,identifier)
