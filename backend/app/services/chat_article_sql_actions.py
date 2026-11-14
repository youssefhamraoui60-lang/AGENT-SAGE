"""Owner-bound, single-use confirmations for the supplied TEST SQL clone plans."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import UUID
from app.core.config import settings
from app.services import article_sql as sql,business_store as db,sage_crud as crud

PERMITS={}
def action(owner,conversation,identifier,step,revision,confirm=False,resource='article'):
    from app.services import conversation_chat as chat
    if not settings.sage_article_sql_enabled:sql.fail('Le service SQL articles n’est pas activé.')
    if step not in ('prepare','approve','execute') or resource not in ('article','category'):raise crud.CrudError('unknown_article_sql_action',422)
    if settings.sage_mcp_enabled and step!='prepare':sql.fail('MCP reste en lecture seule. Aucun enregistrement n’est autorisé dans ce pilote.')
    snapshot=None;collection='articles' if resource=='article' else 'category_drafts'
    with db.connection() as conn:
        row=chat.get_row(conn,owner,conversation,True)
        if row['revision']!=revision:raise crud.CrudError('La fiche a changé. Relisez les nouvelles données avant de confirmer.',409)
        state=row['state']
        folder=sql.supplier_sql.target(state.get('supplier_target','TEST'))
        if state.get('_pending') or state.get('pending_correction') or state.get('workflow')=='cancelled':sql.fail('Terminez l’analyse ou la correction avant de confirmer.')
        item=next((a for a in state.get(collection,[]) if a['id']==str(identifier)),None)
        if not item:raise crud.CrudError('Brouillon introuvable.',404)
        if resource=='article' and not item.get('unite'):
            PERMITS.pop(item['id'],None)
            sql.fail('Précisez l’unité de stock avant de préparer ou confirmer la création. Les unités d’achat et de vente sont à préciser si elles diffèrent.')
        if item.get('dossier_cible','TEST')!=folder:sql.fail('Dossier du brouillon article incoherent.')
        op=item.get('operation') or {}
        if op.get('status') in sql.TERMINAL:raise crud.CrudError('Une tentative existe déjà. Consultez son résultat ; aucun renvoi automatique.',409)
        current_hash=sql.fingerprint(item) if resource=='article' else crud.digest({k:v for k,v in item.items() if k not in ('operation','approved')})
        if step=='prepare':
            data=item if resource=='article' else {k:v for k,v in item.items() if k not in ('operation','approved')}
            prepared=sql.prepare(data,resource);item['operation']=prepared;item['approved']=False;PERMITS.pop(item['id'],None)
        else:
            valid=(op.get('transport')=='direct_sql_article' and op.get('resource')==resource and op.get('folder')==folder and op.get('query_digest')==sql.digest() and op.get('input_hash')==current_hash and op.get('digest')==crud.digest({'plan':op.get('plan'),'query':op.get('query_digest')}))
            if not valid:raise crud.CrudError('Repréparez la fiche puis confirmez ses données exactes. Aucune ancienne autorisation ne sera réutilisée.',409)
            if confirm is not True:raise crud.CrudError('Confirmation explicite obligatoire pour ces données.',403)
            if step=='approve':
                if op.get('status')!='prepared':raise crud.CrudError('Préparez la fiche avant confirmation.',409)
                PERMITS[item['id']]={'owner':str(owner),'conversation':str(conversation),'operation':op['id'],'digest':op['digest'],'expires':datetime.now(timezone.utc)+timedelta(minutes=15)}
                item['approved']=True;op['status']='approved'
            else:
                permit=PERMITS.get(item['id'])
                if (not permit or not item.get('approved') or op.get('status')!='approved' or permit['owner']!=str(owner) or permit['conversation']!=str(conversation) or permit['operation']!=op['id'] or permit['digest']!=op['digest'] or permit['expires']<=datetime.now(timezone.utc)):
                    raise crud.CrudError('Une nouvelle confirmation spécifique est nécessaire avant création.',403)
                PERMITS.pop(item['id'],None);item['approved']=False;op['status']='executing';snapshot=deepcopy(op)
        chat.save_conversation_context(conn,owner,conversation,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s AND owner_id=%s',(conversation,owner))
        chat.append(conn,conversation,'assistant',('La fiche est preparee dans '+folder+'. Relisez les parametres avant de confirmer.' if step=='prepare' else 'Vous avez confirmé les données exactes.' if step=='approve' else 'Creation en cours dans '+folder+'…'),{'article_sql_action':step,'draft_id':item['id'],'sage_writes':0})
    if snapshot:
        try:
            result=sql.transport('plan',snapshot['plan'],True,folder=snapshot['folder']) if snapshot['folder']!='TEST' else sql.transport('plan',snapshot['plan'],True)
            verified=sql.verify(snapshot['plan'],result)
            not_sent=result.get('transaction_state')=='NOT_STARTED' and result.get('confirmed_not_executed') is True and result.get('executed') is False
            status='succeeded' if verified else 'blocked' if result.get('transaction_state')=='ROLLBACK' or not_sent else 'ambiguous'
            label='La catégorie' if resource=='category' else 'L’article'
            message=(label+' '+snapshot['plan']['code']+' a ete enregistre dans '+snapshot['folder']+'. Les enregistrements attendus ont été relus dans la transaction.' if verified else result.get('message') or 'Le résultat est incertain. Ne relancez pas la création avant vérification.')
            functional={'sql_verified':verified,'sage_consultation_verified':False,'business_operations_verified':False}
            # Optional read-only SOAP consultation. Never SOAP SAVE, never substitutes for SQL proof.
            if verified and resource=='article' and snapshot['folder']=='TEST':
                try:
                    from app.services.sage_gateway import Gateway
                    view=Gateway('articles').read({'ITMREF':snapshot['plan']['code']})
                    fields=view.get('fields',{});designation=fields.get('ITM0_1.DES1AXX')
                    functional['sage_consultation_verified']=view.get('exists') is True and fields.get('ITM0_1.ITMREF')==snapshot['plan']['code'] and (designation==snapshot['plan']['summary']['designation'] or isinstance(designation,list) and designation[0]==snapshot['plan']['summary']['designation'])
                except Exception:pass
                message+=' La consultation Sage et les opérations métier restent à contrôler.' if not functional['sage_consultation_verified'] else ' La consultation Sage concorde ; les opérations métier restent à contrôler.'
        except Exception:
            verified=False;status='ambiguous';result={'retry_allowed':False};functional={'sql_verified':False,'sage_consultation_verified':False,'business_operations_verified':False};message='Le résultat n’est pas confirmé. Vérifiez la fiche avant toute nouvelle tentative.'
        with db.connection() as conn:
            row=chat.get_row(conn,owner,conversation,True);state=row['state'];item=next(a for a in state[collection] if a['id']==str(identifier))
            if item.get('operation',{}).get('id')!=snapshot['id']:raise crud.CrudError('La fiche a changé pendant la création.',409)
            item['operation']={**snapshot,'status':status,'result':result,'verification':functional,'message':message};item['approved']=False
            if verified and resource=='category':
                from app.services.article_sql_dialogue import prepare_state
                prepare_state(state)
            chat.save_conversation_context(conn,owner,conversation,state)
            conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s AND owner_id=%s',(conversation,owner))
            chat.append(conn,conversation,'assistant',message,{'article_sql_result':True,'draft_id':item['id'],'retry_allowed':False})
    return chat.read(owner,conversation)
