"""Fresh per-plan confirmations, audit events and no automatic replay after an attempt."""
from copy import deepcopy
from uuid import UUID,uuid4
from datetime import datetime,timedelta,timezone
from psycopg.types.json import Jsonb
from app.services import erp_modification as service,business_store as db,sage_crud as crud
from app.core.config import settings
PERMITS={}

def validate_change_intent(draft):
    # Also protects proposals prepared by an older backend before this fix.
    import re
    from app.services.chat_turns import norm
    value=draft.get('changes',{}).get('address')
    if draft.get('resource')=='supplier' and isinstance(value,str) and re.search(r'\b(?:kan9sed|kanqsed|machi\s+f\d+)\b',norm(value)):
        service.block('Cette proposition confond une correction de cible avec une adresse. Indiquez la nouvelle adresse exacte avant toute préparation ou confirmation.')

class ModificationAuditService:
    @staticmethod
    def append(conn,owner,conversation,draft,event,extra=None):
        op=draft.get('operation') or {};plan=op.get('plan') or {}
        payload={'resource':draft['resource'],'code':draft['code'],'folder':draft.get('folder','TEST'),'changes':draft['changes'],'diff':plan.get('diff',[]),'plan_digest':op.get('digest'),'query_digest':op.get('query_digest'),'confirmation':event in ('approved','executing','succeeded','rollback','ambiguous'),'sensitive_confirmation':draft.get('sensitive_approved',False),'result':extra or {}}
        conn.execute('INSERT INTO chat_modification_audit(owner_id,conversation_id,draft_id,operation_id,event,payload) VALUES(%s,%s,%s,%s,%s,%s)',(owner,conversation,UUID(draft['id']),UUID(op['id']) if op.get('id') else None,event,Jsonb(payload)))

def current_values(view):
    if view['resource']=='supplier':
        p=(view.get('partners') or [{}])[0];s=(view.get('suppliers') or [{}])[0];a=next((r for r in view.get('addresses',[]) if service.clean(r['BPAADD_0'])==service.clean(s.get('BPAADD_0'))),{})
        return {'enabled':s.get('ENAFLG_0')==2 if s.get('ENAFLG_0') in (1,2) else None,'name':p.get('BPRNAM_0'),'short_name':p.get('BPRSHO_0'),'ice':p.get('XICE_0'),'if':p.get('XIF_0'),'rc':p.get('XRC_0'),'payment':s.get('PTE_0'),'phone':a.get('TEL_0'),'email':a.get('WEB_0'),'city':a.get('CTY_0'),'address':' '.join(service.clean(a.get('BPAADDLIG_'+str(i))) for i in range(3)).strip(),'contact_name':s.get('CNTNAM_0')}
    a=(view.get('articles') or [{}])[0]
    return {'sale_enabled':a.get('SALFLG_0')==2,'allow_negative_stock':a.get('NEGSTO_0')==2 if a.get('NEGSTO_0') in (1,2) else None,'supplier_flag':a.get('XFLGBPS_0')==2 if a.get('XFLGBPS_0') in (1,2) else None,'designation':a.get('ITMDES1_0'),'category':a.get('TCLCOD_0'),'accounting':a.get('ACCCOD_0'),'tax_level':[a.get('VACITM_'+str(i)) for i in range(3)],'stock_mode':a.get('STOMGTCOD_0'),'stock_unit':a.get('STU_0'),'purchase_unit':a.get('PUU_0'),'sale_unit':a.get('SAU_0'),'deactivate':a.get('ITMSTA_0'),'add_sites':[r.get('STOFCY_0') for r in view.get('sites',[])],'add_suppliers':[{'code':r['BPSNUM_0'],'reference':r['ITMREFBPS_0']} for r in view.get('article_suppliers',[])]}

def prepare_draft(draft):
    draft['approved']=False;draft['sensitive_approved']=False;PERMITS.pop(draft['id'],None)
    if draft.get('unit_conversion_requests') and draft.get('unit_conversion_changes')==draft.get('changes') and draft.get('operation',{}).get('status') in ('needs_input','blocked'):
        # Rechecking unchanged data cannot resolve a declared contradiction or
        # enable a stock migration unsupported by the existing planner.
        return draft
    try:
        validate_change_intent(draft)
        folder=draft.get('folder','TEST')
        schema=service.catalog(folder) if folder!='TEST' else service.catalog();view=service.snapshot(draft['resource'],draft['code'],folder) if folder!='TEST' else service.snapshot(draft['resource'],draft['code'])
        draft['current']=current_values(view);draft['analysis']=service.ArticleDependencyAnalyzer().analyze(view)
        if draft['resource']=='article' and 'category' in draft['changes']:
            value=draft['changes']['category']
            if not any(service.clean(r['TCLCOD_0'])==value for r in view['categories']):
                a=(view.get('articles') or [{}])[0]
                if draft['analysis']['used']:service.ArticleModificationPolicy().check('article',draft['changes'],draft['analysis'])
                profile={col:a[col] for col in (*service.article_sql.FLAGS.values(),'STU_0','ACCCOD_0','VACITM_0') if col in a}
                rejected=draft.get('rejected_categories',[])
                choices=service.CategoryResolver().search(value,view['categories'],profile,rejected,5 if rejected else 3)
                draft['category_choices']=choices
                message='Choisissez une catégorie proposée par son code avant la préparation.' if choices else 'Aucune catégorie compatible retrouvée. Une nouvelle catégorie peut être préparée séparément, sans modifier cet article.'
                draft['operation']={'status':'needs_selection','message':message};return draft
        draft['operation']=service.prepare(draft,schema,view)
    except (crud.CrudError,ValueError,TypeError,KeyError) as exc:
        message=exc.code if isinstance(exc,crud.CrudError) else 'Une valeur nécessite une précision. Vos changements sont conservés ; aucune écriture.'
        draft['operation']={'status':'blocked','message':message}
    return draft

def add(owner,conversation,revision,resource,code,changes):
    from app.services import conversation_chat as chat
    if not settings.sage_modification_enabled:service.block('Le module de modification n’est pas activé.')
    with db.connection() as conn:
        row=chat.get_row(conn,owner,conversation,True)
        if row['revision']!=revision:raise crud.CrudError('La conversation a changé.',409)
        folder=service.supplier_sql.target(row['state'].get('supplier_target','TEST'))
        if row['state'].get('_pending'):service.block('Terminez l’analyse en cours avant une nouvelle préparation.')
        draft={'id':str(uuid4()),'folder':folder,'resource':resource,'code':code,'changes':changes}
        prepare_draft(draft);row['state'].setdefault('modification_drafts',[]).append(draft)
        chat.save_conversation_context(conn,owner,conversation,row['state']);conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(conversation,))
        ModificationAuditService.append(conn,owner,conversation,draft,'prepared' if draft['operation']['status']=='prepared' else 'blocked')
        chat.append(conn,conversation,'assistant',draft['operation'].get('message') or 'Modification preparee dans '+folder+'. Verifiez les valeurs avant confirmation.',{'modification_draft':draft['id'],'sage_writes':0})
    return chat.read(owner,conversation)

def action(owner,conversation,draft_id,step,revision,confirm=False,sensitive_confirm=False):
    from app.services import conversation_chat as chat
    if not settings.sage_modification_enabled:service.block('Modifications désactivées ; les brouillons restent conservés.')
    if step not in ('prepare','approve','execute'):raise crud.CrudError('Action inconnue.',422)
    if step!='prepare' and settings.sage_mcp_enabled:service.block('MCP reste strictement en lecture seule ; aucune confirmation d’écriture dans ce pilote.')
    execution=None
    with db.connection() as conn:
        row=chat.get_row(conn,owner,conversation,True);state=row['state']
        if row['revision']!=revision:raise crud.CrudError('La fiche a changé. Relisez ses valeurs.',409)
        folder=service.supplier_sql.target(state.get('supplier_target','TEST'))
        if state.get('_pending') or state.get('pending_correction') or state.get('workflow')=='cancelled':service.block('Terminez l’analyse ou la correction avant de confirmer.')
        d=next((d for d in state.get('modification_drafts',[]) if d['id']==str(draft_id)),None)
        if not d:raise crud.CrudError('Modification introuvable.',404)
        if d.get('folder','TEST')!=folder:service.block('Dossier de modification incoherent.')
        validate_change_intent(d)
        if d.get('resource')=='supplier' and state.get('supplier_tasks') and (state.get('active_supplier_task')!='modify' or (state['supplier_tasks'].get('control') or {}).get('code')!=d['code'] and not ('enabled' in d.get('changes',{}) and d['code'] in state.get('supplier_status_batch',{}).get('codes',[]))):service.block('La demande active ne confirme pas ce changement fournisseur. Revenez explicitement à sa modification.')
        op=d.get('operation') or {}
        if op.get('status') in service.TERMINAL:raise crud.CrudError('Tentative déjà enregistrée. Consultez son résultat ; aucun renvoi automatique.',409)
        if step=='prepare':prepare_draft(d)
        else:
            if op.get('transport')!='direct_sql_modification' or op.get('query_digest')!=service.query_digest() or op.get('input_hash')!=service.fingerprint(d) or op.get('digest')!=crud.digest({'plan':op.get('plan'),'query':op.get('query_digest')}):raise crud.CrudError('Les paramètres ont changé. Une nouvelle préparation et confirmation sont nécessaires.',409)
            if confirm is not True:raise crud.CrudError('Confirmation explicite des changements obligatoire.',403)
            sensitive=op['plan']['policy']['sensitive']
            if sensitive and sensitive_confirm is not True:raise crud.CrudError('Confirmation spécifique des données sensibles obligatoire.',403)
            if step=='approve':
                if op['status']!='prepared':raise crud.CrudError('Préparez les nouvelles valeurs avant confirmation.',409)
                PERMITS[d['id']]={'owner':str(owner),'conversation':str(conversation),'operation':op['id'],'digest':op['digest'],'expires':datetime.now(timezone.utc)+timedelta(minutes=15),'sensitive':sensitive_confirm}
                d['approved']=True;d['sensitive_approved']=sensitive_confirm;op['status']='approved'
            else:
                permit=PERMITS.get(d['id'])
                if not permit or not d.get('approved') or op['status']!='approved' or permit['owner']!=str(owner) or permit['conversation']!=str(conversation) or permit['operation']!=op['id'] or permit['digest']!=op['digest'] or permit['expires']<=datetime.now(timezone.utc) or sensitive and not permit['sensitive']:raise crud.CrudError('Une nouvelle confirmation individuelle est nécessaire.',403)
                PERMITS.pop(d['id'],None);d['approved']=False;op['status']='executing';execution=deepcopy(d)
        chat.save_conversation_context(conn,owner,conversation,state);conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(conversation,))
        ModificationAuditService.append(conn,owner,conversation,d,'prepared' if step=='prepare' and d['operation']['status']=='prepared' else 'blocked' if step=='prepare' else 'approved' if step=='approve' else 'executing')
        chat.append(conn,conversation,'assistant',d['operation'].get('message') or ('Vérifiez les changements avant confirmation.' if step=='prepare' else 'Vous avez confirmé ces changements précis.' if step=='approve' else 'Modification en cours dans '+folder+'…'),{'modification_action':step,'sage_writes':0})
    if execution:
        plan=execution['operation']['plan']
        try:result=service.transport('plan',execution['resource'],execution['code'],plan,True,folder=execution['folder']) if execution['folder']!='TEST' else service.transport('plan',execution['resource'],execution['code'],plan,True);verified=service.verify(plan,result)
        except Exception:result={'ok':False,'retry_allowed':False};verified=False
        not_sent=result.get('transaction_state')=='NOT_STARTED' and result.get('confirmed_not_executed') is True and result.get('executed') is False
        status='succeeded' if verified else 'blocked' if result.get('transaction_state')=='ROLLBACK' or not_sent else 'ambiguous'
        message='Les changements de '+execution['code']+' ont été enregistrés et relus dans '+execution['folder']+'. Les documents historiques n’ont pas été modifiés. La validation fonctionnelle Sage reste à effectuer.' if verified else result.get('message') or 'Le résultat de la modification est incertain. Vérifiez la fiche avant toute autre tentative.'
        with db.connection() as conn:
            row=chat.get_row(conn,owner,conversation,True);state=row['state'];d=next(d for d in state['modification_drafts'] if d['id']==execution['id'])
            if d.get('operation',{}).get('id')!=execution['operation']['id']:raise crud.CrudError('La modification a changé pendant l’exécution.',409)
            d['operation']={**execution['operation'],'status':status,'result':result,'message':message};d['approved']=False
            chat.save_conversation_context(conn,owner,conversation,state);conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(conversation,))
            ModificationAuditService.append(conn,owner,conversation,d,'succeeded' if verified else 'rollback' if status=='blocked' else 'ambiguous',result)
            chat.append(conn,conversation,'assistant',message,{'modification_result':d['id'],'verified':verified,'retry_allowed':False})
    return chat.read(owner,conversation)
