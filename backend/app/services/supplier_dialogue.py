"""Task dialogue state, independent from model availability and write permissions."""
import copy,re
from uuid import uuid4
from app.services.chat_turns import norm,SUPPLIER_WORD

QUESTIONS={'nom':'Quel est le nom du fournisseur ?','ville':'Quelle est la ville du fournisseur ?',
 'adresse':'Quelle est l’adresse du fournisseur ?','ice':'Quel est son ICE ? Vous pouvez aussi le laisser vide.',
 'conditions_paiement':'Quelles sont ses conditions de paiement ?','telephone':'Quel est son téléphone ?'}
def supplier_intent(text,state):
    return bool(any(p.get('kind')=='supplier' for p in state.get('partners',[])) or re.search(r'\b'+SUPPLIER_WORD+r's?\b',norm(text)))

def assign(state,field,value):
    p=state['partners'][0];old=p.get(field)
    if (p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):
        return 'Consultez le résultat de la tentative précédente avant de modifier cette fiche.'
    from app.schemas.conversation_entities import SupplierPatch
    SupplierPatch.model_validate({field:value})
    p[field]=value;p.setdefault('sources',{})[field]='user_declared'
    p.setdefault('document_sources',{}).pop(field,None)
    p.setdefault('field_states',{})[field]={'value':value,'previous':old,'status':'declared','source':'user_declared'}
    p['approved']=False;p['reviewed']=False;p['operation']={'status':'invalidated'}
    focus=state.setdefault('_supplier_dialogue',{})
    focus.update(last_field=field,last_assignment={'field':field,'value':value,'before':old})
    if focus.get('expected_field')==field or field=='conditions_paiement' and focus.get('expected_field')=='payment_method':
        focus.pop('expected_field',None);focus.pop('payment_days',None)
    if value not in (None,'') and field in p.get('unknown_fields',[]):p['unknown_fields'].remove(field)
    return None

def recover_missing_history(state,history):
    """Recover literal facts for this named draft, never another supplier's data."""
    partners=state.get('partners',[])
    if len(partners)!=1 or not partners[0].get('nom'):return False
    p=partners[0]
    if (p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):return False
    from app.services.supplier_chat_flow import extract
    facts={}
    for row in reversed(history):
        if row.get('role')!='user':continue
        try:parsed=extract(row.get('content',''),{'partners':[],'articles':[]})
        except ValueError:continue
        if not parsed or len(parsed[0].fournisseurs)!=1:continue
        fields=parsed[0].fournisseurs[0].model_dump(exclude_none=True,exclude_unset=True)
        if not fields.get('nom'):continue
        if norm(fields['nom'])!=norm(p['nom']):break
        for key in ('ice','identifiant_fiscal','rc','adresse','ville','telephone','email','conditions_paiement','fax','date_regularite','type_montant','devise','pays'):
            if fields.get(key):facts.setdefault(key,set()).add(fields[key])
    changed=False
    for field,values in facts.items():
        if p.get(field) in (None,'') and len(values)==1:
            assign(state,field,next(iter(values)));changed=True
    return changed

def handle(text,state,history=()):
    from app.services.supplier_multiturn import CREATE
    if re.search(r'\b'+CREATE+r'\s+(?:(?:un|une|le|la|nouveau|nouvel)\s+)*articles?\b',norm(text)):return None
    from app.services.supplier_followups import turn as short_turn
    followup=short_turn(text,state)
    if followup:return followup
    from app.services.supplier_multiturn import turn
    literal=turn(text,state,history)
    if literal:return literal
    if state.get('articles'):return None
    n=norm(text).strip(' .!?');drafts=state.get('partners',[])
    if re.match(r'^(?:comment|pourquoi|quelle?s?|quels?|est.ce|peux.tu expliquer)\b',n):return None
    if any(p.get('kind')!='supplier' for p in drafts):return None
    state=copy.deepcopy(state);focus=state.setdefault('_supplier_dialogue',{})
    from app.services import supplier_discourse as discourse
    if re.search(r'\bet\s+(?:(?:les|des)\s+)?articles?\s*:',n):return None
    if discourse.off_topic(text) and (drafts or state.get('discussion_mode')=='supplier'):
        return {'state':state,'reply':discourse.OFF_TOPIC_REPLY}
    language=discourse.language_clarification(text)
    if language:
        if len(drafts)==1 and (drafts[0].get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):
            return {'state':state,'reply':'Vous pouvez continuer en darija. Consultez le résultat de la tentative précédente avant de modifier cette fiche.'}
        if not drafts:
            state['partners']=[{'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False}]
        elif discourse.mistaken_language_name(drafts[0].get('nom')):
            assign(state,'nom',None)
        if state['partners'][0].get('nom'):
            return {'state':state,'reply':'Vous pouvez continuer en darija. Je conserve le nom '+state['partners'][0]['nom']+' et les informations déjà fournies.'}
        state['_supplier_dialogue']={'expected_field':'nom'}
        return {'state':state,'reply':'J’ai compris : vous parlez en darija et souhaitez créer un fournisseur. Quel est son nom ?'}
    name=discourse.explicit_name(text)
    if name and not drafts and '?' not in text and re.search(r'\b'+SUPPLIER_WORD+r's?\b',n):
        state['partners']=[{'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False}]
        error=assign(state,'nom',name)
        if not error:recover_missing_history(state,history)
        return {'state':state,'prepare':not error,'reply':error}
    if name and len(drafts)==1:
        error=assign(state,'nom',name)
        if not error:recover_missing_history(state,history)
        return {'state':state,'prepare':not error,'reply':error}
    from app.services import supplier_chat_flow,chat_partners
    # Explicit NEW means fresh facts, even after a duplicate or an earlier success.
    new=bool(re.search(r'\b(?:creer?|ajouter?|prepare)\b',n) and re.search(r'\b(?:nouveau|nouvelle|nouvel|autre)\s+(?:fiche\s+)?'+SUPPLIER_WORD+r's?\b',n))
    bare=discourse.bare_request(text)
    if bare or new and drafts:
        if any((p.get('operation') or {}).get('status')=='executing' for p in drafts):
            return {'state':state,'reply':'La création précédente est en cours. Attendez son résultat avant de préparer une autre fiche.'}
        if new and drafts:
            state.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(drafts),'reason':'explicit_new_request'})
            state['partners']=[];drafts=[]
        if not bare:
            parsed=supplier_chat_flow.extract(text,{'articles':[],'partners':[]},history)
            if parsed:
                merged=chat_partners.merge({'articles':[],'partners':[]},parsed[0],parsed[1])
                if merged.get('partners'):
                    state['partners']=merged['partners'];state['_supplier_dialogue']={}
                    return {'state':state,'prepare':True}
        if not drafts:state['partners']=[{'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False}]
        state['_supplier_dialogue']={'expected_field':'nom'}
        return {'state':state,'reply':QUESTIONS['nom']}
    if len(drafts)!=1:return None
    p=state['partners'][0]
    if re.search(r'\b(?:deja|dans la conv|dans cette conv)',n) and re.search(r'\b(?:ice|ici|if|rc|information|donne)',n):
        if recover_missing_history(state,history):return {'state':state,'prepare':True}
        if re.search(r'\b(?:ice|ici)\b',n):
            return {'state':state,'reply':('L’ICE conservé est '+p['ice']+'.' if p.get('ice') else 'Je ne retrouve pas d’ICE certain pour cette fiche. Quel est son ICE ? Vous pouvez aussi le laisser vide.')}
    if re.search(r'(?:deja demande|deja donne|deja fourni|encore cette information)',n):
        focus.pop('expected_field',None)
        known=[label+' : '+str(p[field]) for field,label in (('nom','Nom'),('ville','Ville'),('adresse','Adresse'),('ice','ICE'),('conditions_paiement','Paiement')) if p.get(field)]
        return {'state':state,'reply':'Je conserve les informations déjà fournies. '+(' ; '.join(known)+'. ' if known else '')+'Vous pouvez compléter ou corriger la fiche sans tout répéter.'}
    from app.services.learning_auto import apply,correct_relation
    learned=apply(text,state)
    if learned:return learned
    corrected=correct_relation(text,state)
    if corrected:return corrected
    if not focus.get('expected_field'):
        previous=next((h.get('content','') for h in reversed(history) if h.get('role')=='assistant'),'')
        question=norm(previous)
        candidates=[field for field,pattern in {'ville':r'quelle\s+(?:est\s+la\s+)?ville','nom':r'quel\s+(?:est\s+le\s+)?nom','adresse':r'quelle\s+(?:est\s+l[’\x27])?adresse'}.items() if re.search(pattern,question)]
        if len(candidates)==1:focus['expected_field']=candidates[0]
    aliases={'nom':'nom','ville':'ville','adresse':'adresse','ice':'ice','telephone':'telephone','paiement':'conditions_paiement'}
    requested=re.fullmatch(r'(?:(?:ajoute|ajouter|renseigne|complete|precise|pour)\s+)?(?:le |la |l[’\'])?('+ '|'.join(aliases)+r')',n)
    if requested:
        field=aliases[requested[1]];focus['expected_field']=field
        return {'state':state,'reply':QUESTIONS[field]}
    correction=re.fullmatch(r"(?:non[, ]+)?(?:c['’]est|c est|plutot|c['’]etait)\s+(?:la |le |l['’])?(ville|adresse|nom)",n)
    if correction:
        if (p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):
            return {'state':state,'reply':'Consultez le résultat de la tentative précédente avant de modifier cette fiche.'}
        field=correction[1];last=focus.get('last_assignment');value=focus.get('ambiguous_value') or (last or {}).get('value')
        if value:
            if last and last['field']!=field and p.get(last['field'])==last['value']:
                p[last['field']]=last['before']
                p.setdefault('sources',{}).pop(last['field'],None)
            error=assign(state,field,value)
            return {'state':state,'prepare':not error,'reply':error}
        focus['expected_field']=field
        return {'state':state,'reply':QUESTIONS[field]}
    payment=re.fullmatch(r'(?:non[, ]+)?(?:plutot|passe a|mets|corrige a)\s+(\d{1,3})\s*(?:jours?|j|jr)',n)
    if payment:
        current=p.get('conditions_paiement') or ''
        method=re.search(r'\b(cheque|effet|virement)\b',norm(current))
        if not method:
            method=re.match(r'(CHQ|EFF|VIR)\d+',current.upper())
            mode={'CHQ':'chèque','EFF':'effet','VIR':'virement'}.get(method[1]) if method else None
        else:mode=method[1]
        if not mode:
            focus.update(expected_field='payment_method',payment_days=payment[1])
            return {'state':state,'reply':'Quel mode de paiement souhaitez-vous : chèque, effet ou virement ?'}
        error=assign(state,'conditions_paiement',mode+' '+payment[1]+' jours')
        return {'state':state,'prepare':not error,'reply':error}
    expected=focus.get('expected_field')
    if expected and re.search(r'\b(?:annul\w*|modifi\w*|modif\w*|change\w*|stop)\b',n):return None
    if expected and not re.search(r'[:=\n?]',text) and not re.search(r'\b(?:ice|if|rc|telephone|tel)\s*\d',n) and len(text.strip())<=100:
        if n in ('oui','ok','non','merci'):
            return {'state':state,'reply':QUESTIONS.get(expected,'Quel mode de paiement souhaitez-vous ?')}
        value=text.strip().rstrip('.')
        if expected=='payment_method':
            if n not in ('cheque','effet','virement'):return {'state':state,'reply':'Précisez le mode : chèque, effet ou virement.'}
            value=value+' '+str(focus['payment_days'])+' jours';expected='conditions_paiement'
        if expected in QUESTIONS:
            if expected=='ice' and n in ('vide','sans ice','je ne sais pas'):value=None
            try:error=assign(state,expected,value)
            except ValueError:return {'state':state,'reply':'Cette valeur n’a pas le format attendu. '+QUESTIONS[expected]}
            return {'state':state,'prepare':not error,'reply':error}
    explicit=re.fullmatch(r"(?:(?:correction|je corrige)\s*:\s*)?(?:non[, ]+)?(?:le |la |l['’])?(nom|ville|adresse)\s+(?:est|c['’]est|c est)\s+(.+)",n)
    if explicit:
        value=text[explicit.start(2):explicit.end(2)].strip()
        error=assign(state,explicit[1],value)
        return {'state':state,'prepare':not error,'reply':error}
    return None

def remember_changes(before,after,text):
    previous=before.get('partners',[]);current=after.get('partners',[])
    if len(previous)!=1 or len(current)!=1 or previous[0]['id']!=current[0]['id']:return
    changed=[k for k in QUESTIONS if previous[0].get(k)!=current[0].get(k)]
    if len(changed)==1:
        field=changed[0];after.setdefault('_supplier_dialogue',{}).update(last_field=field,last_assignment={'field':field,'value':current[0].get(field),'before':previous[0].get(field)})

def fallback(text,state):
    state=copy.deepcopy(state);state.pop('_pending',None)
    drafts=state.get('partners',[])
    if len(drafts)==1 and not drafts[0].get('nom'):
        state['_supplier_dialogue']={'expected_field':'nom'};reply=QUESTIONS['nom']
    elif len(drafts)==1:
        state.setdefault('_supplier_dialogue',{})['ambiguous_value']=text.strip() if len(text)<80 and '?' not in text else None
        reply='Votre fiche est conservée. Quelle information souhaitez-vous préciser : le nom, la ville, l’adresse ou le paiement ?'
    else:reply='Votre demande est conservée. Indiquez le nom du fournisseur et les informations dont vous disposez.'
    return state,reply
