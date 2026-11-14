"""Speech-act interrupts precede every pending-value slot. Never execute Sage."""
import copy,re
from uuid import uuid4
from app.services.chat_turns import norm,SUPPLIER_WORD

def turn(text,state):
    n=norm(text).strip();s=copy.deepcopy(state)
    cancelling=bool(re.match(r'(?:(?:je veux|merci de)\s+)?annul\w*\b',n) and re.search(r'\b(?:creation|creer|brouillon)\b',n))
    if cancelling:
        from app.services.chat_supplier_sql_actions import PERMITS
        pending=[p for p in s.get('partners',[]) if p.get('operation',{}).get('status') not in ('executing','succeeded','ambiguous','unverified','failed')]
        for p in pending:
            PERMITS.pop(p['id'],None);p.update(approved=False,reviewed=False)
            p['operation']={'status':'cancelled','message':'Création annulée dans la conversation.'}
        s.pop('_supplier_dialogue',None);s.pop('pending_creation',None)
        s['supplier_creation_hold']=True;s['active_supplier_task']='idle'
        if s.get('supplier_tasks'):s['supplier_tasks']['active']='idle'
        s['workflow']='cancelled'
        reply='La création est annulée. Le brouillon reste dans l’historique ; aucune écriture Sage.'
        if not pending and any(p.get('operation',{}).get('status')=='succeeded' for p in s.get('partners',[])):
            reply='La fiche déjà créée ne peut pas être annulée par ce message. Aucune suppression ni modification Sage.'
        if re.search(r'\b(?:modifier|modifie|modifer|changer)\b',n):
            s['modification_pending_target']={'resource':'supplier','message':text};s['workflow']='draft'
            reply+=' Quel fournisseur souhaitez-vous modifier ? Donnez son code ou son nom.'
        return {'state':s,'reply':reply}
    request=re.fullmatch(r'(?:(?:je veux|je souhaite|merci de)\s+)?(?:modifier|modifie|modifer|changer)\s+(?:(?:le|la|mon|ce|cette)\s+)*'+SUPPLIER_WORD+r'(?:\s+(.+?))?[.!\s]*',n)
    if not request:return None
    # A field-specific UPDATE belongs to its existing handler, not name search.
    label=text[request.start(1):request.end(1)].strip(' .!') if request[1] else ''
    if re.search(r'\b(?:nom|ville|adresse|telephone|ice|if|rc|paiement)\b',norm(label)):return None
    s.pop('_supplier_dialogue',None);s['workflow']='draft';s['supplier_creation_hold']=True
    s['active_supplier_task']='modify'
    if s.get('supplier_tasks'):s['supplier_tasks']['active']='modify'
    s['modification_pending_target']={'resource':'supplier','message':text,'name_query':label}
    if not label:return {'state':s,'reply':'Quel fournisseur souhaitez-vous modifier ? Donnez son code ou son nom.'}
    from app.services import chat_tools,modification_dialogue
    try:
        if re.fullmatch(r'f\d+',norm(label)):code=label.upper()
        else:
            response=chat_tools.run([{'id':'transition_supplier','tool':'search_suppliers','args':{'Label':label,'Supplier':''}}]).get('transition_supplier',{})
            if response.get('ok') is not True:raise ValueError('supplier_search_unavailable')
            rows=response.get('rows',[])
            exact=[r for r in rows if norm(str(r.get('BPRNAM_0') or '').strip())==norm(label)]
            if len(exact)!=1:
                choices=', '.join(str(r.get('BPSNUM_0') or '')+' — '+str(r.get('BPRNAM_0') or '') for r in rows[:5])
                return {'state':s,'reply':('Correspondances dans TEST : '+choices+'. Donnez le code exact.' if rows else 'Aucun fournisseur correspondant à « '+label+' » n’a été trouvé dans TEST. Vérifiez son nom ou donnez son code.')+' Aucune création préparée.'}
            code=str(exact[0]['BPSNUM_0']).strip()
        current=modification_dialogue.read_current_record('supplier',code)
        d={'id':str(uuid4()),'folder':'TEST','resource':'supplier','code':code,'current':current,'changes':{},'operation':{'status':'needs_input'}}
        s.setdefault('modification_drafts',[]).append(d);s.pop('modification_pending_target',None)
        if s.get('supplier_tasks'):s['supplier_tasks']['control']={'code':code,'kind':'update','field':None,'new_value':None,'status':'needs_input'}
        return {'state':s,'reply':'Fournisseur '+code+' — '+str(current.get('name') or label)+'. Quelle information souhaitez-vous modifier ? Aucune création préparée.'}
    except Exception as exc:
        from app.services.chat_diagnostics import record
        record(exc,'supplier_update_name_lookup')
        return {'state':s,'reply':'La recherche du fournisseur est momentanément indisponible. La demande de modification est conservée ; donnez son code ou réessayez. Aucune création préparée.'}
