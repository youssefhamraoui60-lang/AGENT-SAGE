"""Existing chat actions backed by the supplied TEST supplier SQL, never SOAP."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from app.services import business_store as db,sage_crud as crud,chat_partners as partners,supplier_sql as sql

PERMITS={}
TERMINAL={'executing','ambiguous','unverified','succeeded','failed','cancelled'}

def fingerprint(partner):return crud.digest({k:partner.get(k) for k in sorted(partners.FIELDS)})

def action(owner,identifier,partner_id,step,revision,confirm=False,confirm_duplicates=False,confirm_draft_only_fields=False):
    from app.core.config import settings
    if settings.sage_mcp_enabled and step in ('approve','execute'):
        raise crud.CrudError('Pilote MCP en lecture seule : aucune création SQL autorisée. Le brouillon est conservé.',423)
    from app.services import conversation_chat as chat
    if step not in ('prepare','approve','execute'):raise crud.CrudError('unknown_action',422)
    snapshot=None
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision:raise crud.CrudError('stale_revision',409)
        state=row['state'];p=next((x for x in state.get('partners',[]) if x['id']==str(partner_id)),None)
        if state.get('supplier_creation_hold') or state.get('active_supplier_task','create')!='create':
            raise crud.CrudError('Création suspendue ou autre demande active. Revenez explicitement au brouillon avant de préparer ou confirmer.',423)
        if state.get('pending_correction'):raise crud.CrudError('Confirmez ou refusez la correction proposée dans le chat avant toute création.',423)
        if not p or p.get('kind')!='supplier':raise crud.CrudError('supplier_not_found',404)
        review=state.get('document_review') or {}
        if review.get('items') or review and not review.get('target_id'):
            raise crud.CrudError('Relisez les valeurs du document et résolvez les conflits dans le chat avant de préparer ou confirmer la création.',423)
        folder=sql.target(p.get('dossier_cible','TEST'))
        if folder!=state.get('supplier_target','TEST'):raise crud.CrudError('supplier_target_mismatch',403)
        if state.get('_pending') or state.get('workflow')=='cancelled':raise crud.CrudError('draft_not_reviewable',409)
        if step=='prepare':
            from app.services.supplier_chat_flow import repair_embedded_fields
            repair_embedded_fields(p)
        from app.services.supplier_followups import phone_warning
        if phone_warning(p):raise crud.CrudError(phone_warning(p),423)
        op=p.get('operation') or {}
        if op.get('status') in TERMINAL:raise crud.CrudError('existing_attempt_requires_readback_no_retry',409)
        if step in ('approve','execute') and (op.get('duplicate_warnings') or op.get('validation',{}).get('sql_error_number')==50109):
            raise crud.CrudError(sql.preparation_message(op.get('validation') or {'duplicate_warnings':op['duplicate_warnings']}),423)
        sha=sql.query_digest(folder) if folder=='OB' else sql.query_digest()
        values=sql.parameters(p,op.get('model_defaults')) if step!='prepare' else None
        if step=='prepare':
            if op and op.get('status') not in ('invalidated','blocked'):raise crud.CrudError('supplier_preparation_already_exists',409)
            PERMITS.pop(p['id'],None)
            p['operation']=sql.prepare_operation(p);p['operation']['partner_hash']=fingerprint(p)
            p['approved']=False
        elif step=='approve':
            expected_draft_fields=[{'field':'forme_juridique','label':'Forme juridique','value':p['forme_juridique']}] if p.get('forme_juridique') else []
            if op.get('draft_only_fields',[])!=expected_draft_fields:
                raise crud.CrudError('Préparez à nouveau la fiche : le périmètre des champs a changé.',409)
            if expected_draft_fields and confirm_draft_only_fields is not True:
                raise crud.CrudError('Confirmez que la forme juridique sera conservée uniquement dans le brouillon, sans enregistrement dans Sage.',423)
            if op.get('duplicate_warnings') and confirm_duplicates is not True:
                raise crud.CrudError('Confirmez explicitement la création malgré les doublons affichés dans TEST.',423)
            if (confirm is not True or op.get('status')!='prepared' or op.get('partner_hash')!=fingerprint(p)
                or op.get('folder')!=folder
                or op.get('transport')!='direct_sql' or op.get('query_digest')!=sha or op.get('parameters')!=values):
                raise crud.CrudError('specific_confirmation_required',409)
            if sql.operation_digest(op)!=op.get('digest'):raise crud.CrudError('specific_confirmation_required',409)
            PERMITS[p['id']]={'owner':str(owner),'hash':fingerprint(p),'operation_id':op['id'],'digest':op['digest'],
                'duplicate_codes':sorted({w['code'] for w in op.get('duplicate_warnings',[])}),
                'expires_at':datetime.now(timezone.utc)+timedelta(minutes=15)}
            p['approved']=True;op['status']='approved'
        else:
            permit=PERMITS.get(p['id'])
            if (confirm is not True or not p.get('approved') or op.get('status')!='approved' or not permit
                or permit['owner']!=str(owner) or permit['hash']!=fingerprint(p) or op.get('partner_hash')!=fingerprint(p)
                or permit['operation_id']!=op.get('id') or permit['digest']!=op.get('digest')
                or op.get('parameters')!=values or op.get('query_digest')!=sha or op.get('transport')!='direct_sql'
                or op.get('folder')!=folder
                or sql.operation_digest(op)!=op.get('digest')
                or permit['expires_at']<=datetime.now(timezone.utc)):
                raise crud.CrudError('fresh_specific_approval_required',403)
            PERMITS.pop(p['id'],None);p['approved']=False;op['status']='executing'
            snapshot={**op,'partner_id':p['id']}
        chat.save_conversation_context(conn,owner,identifier,state)
        chat.append(conn,identifier,'system',
            (p['operation'].get('validation',{}).get('message') or 'La fiche fournisseur est prête. Vérifiez ses informations avant de confirmer.') if step=='prepare' else
            'Vous avez confirmé la création du fournisseur.' if step=='approve' else
            'Création du fournisseur en cours…',{'partner_id':p['id'],'action':step})
    if snapshot:
        try:
            codes=permit.get('duplicate_codes') or []
            options={'folder':folder} if folder=='OB' else {}
            body=sql.run(snapshot['parameters'],execute=True,approved_duplicate_codes=codes,**options) if codes else sql.run(snapshot['parameters'],execute=True,**options)
            proof=sql.verify(snapshot['parameters'],body,**options)
            message=('Nous vous informons que le fournisseur '+snapshot['parameters']['Nom']+' a été créé avec succès. Son code est '+proof['code']+'. Ses informations ont été vérifiées dans TEST.' if proof else
                'La création du fournisseur n’est pas encore confirmée. Vérifiez sa fiche avant de réessayer.')
            message=message.replace('dans TEST','dans '+folder)
            if proof and snapshot.get('draft_only_fields'):
                message+=' La forme juridique reste uniquement dans le brouillon, conformément à votre accord.'
            operation={**snapshot,'status':'succeeded' if proof else 'ambiguous',
                'result':{'status':1 if proof else 0,'supplier_verification':proof,
                'supplier_message':message,'retry_allowed':False,'sql_error_number':body.get('sql_error_number')},
                'record_keys':{'BPSNUM':proof['code']} if proof else {},'after_record':{'exists':bool(proof)}}
            if body.get('code')=='sql_validation_rejected':
                message='La création a été annulée. Vérifiez à nouveau les informations de la fiche avant de confirmer.'
                operation['status']='blocked';operation['validation']={**body,'message':message}
                operation['result']['supplier_message']=message
        except Exception:
            operation={**snapshot,'status':'ambiguous','result':{'retry_allowed':False,
                'supplier_message':'La création n’est pas encore confirmée. Vérifiez la fiche avant de réessayer.'}}
        with db.connection() as conn:
            row=chat.get_row(conn,owner,identifier,True);state=row['state']
            p=next(x for x in state['partners'] if x['id']==snapshot['partner_id'])
            if p.get('operation',{}).get('id')!=snapshot['id']:raise crud.CrudError('supplier_operation_changed',409)
            p['operation']=chat.operation_snapshot(operation)
            chat.save_conversation_context(conn,owner,identifier,state)
            chat.append(conn,identifier,'assistant',operation['result']['supplier_message'],{'partner_id':p['id'],'retry_allowed':False})
    return chat.read(owner,identifier)
