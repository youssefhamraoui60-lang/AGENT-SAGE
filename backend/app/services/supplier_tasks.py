"""Independent supplier task slots. Only local drafts and predefined TEST reads.

This controller cannot approve/execute writes. Explicit new values can be
submitted to the existing modification validator for a reviewable proposal.
"""
import copy,re
from uuid import uuid4
from datetime import datetime,timezone
from app.services.chat_turns import norm
from app.services import chat_tools,sage_crud as crud

TERMINAL={'executing','succeeded','ambiguous','unverified','failed'}
ORDINAL=r'(?:premier|1er|1ere|1|2eme|2e|deuxieme|2|3eme|3e|troisieme|3)'
CITY={'casa':'Casablanca','casablanca':'Casablanca','rabat':'Rabat','agadir':'Agadir','fes':'Fes','berrechid':'Berrechid'}

def now():return datetime.now(timezone.utc).isoformat()
def index(word):return 0 if word in ('premier','1er','1ere','1') else 1 if word in ('2eme','2e','deuxieme','2') else 2
def blank():return {'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False,'operation':{'status':'invalidated'}}
def store(p,field,value):
    # A confirmed/attempted Sage write is a historical snapshot, never an
    # editable creation draft. Subsequent changes require a separate UPDATE.
    if p.get('operation',{}).get('status') in TERMINAL:return False
    from app.schemas.conversation_entities import SupplierPatch
    SupplierPatch.model_validate({field:value})
    p[field]=value;p.setdefault('sources',{})[field]='user_declared';p['approved']=False;p['reviewed']=False
    p.setdefault('field_states',{})[field]={'value':value,'status':'declared','source':'user_declared'}
    if (p.get('operation') or {}).get('status') not in TERMINAL:p['operation']={'status':'invalidated'}
def unknown(p,field):
    if not p.get(field):
        p.setdefault('field_states',{})[field]={'value':None,'status':'unknown','source':'user_declared_missing'}
        if field not in p.setdefault('unknown_fields',[]):p['unknown_fields'].append(field)
def cancel_plans(state,code):
    from app.services.modification_actions import PERMITS
    for d in state.get('modification_drafts',[]):
        if d.get('resource')=='supplier' and d.get('code')==code and d.get('operation',{}).get('status') not in ('executing','succeeded','ambiguous'):
            PERMITS.pop(d['id'],None);d.update(approved=False,sensitive_approved=False)
            d['operation']={'status':'cancelled','message':'Demande remplacée ou retirée dans le chat. Aucune écriture autorisée.'}
def workflow(state):
    return state.setdefault('supplier_tasks',{'version':1,'active':'create','group':{'id':str(uuid4()),'expected_count':len(state.get('partners',[])),'status':'draft'},'control':None,'history':[]})
def result(state,reply,phase='supplier_tasks'):
    workflow(state)
    state['active_supplier_task']=state['supplier_tasks']['active']
    task=state['supplier_tasks'];c=task.get('control')
    state['conversation_analysis']={'status':'validated','provider':'task_controller','training_performed':False,
        'analysis':{'intent':'CREATE_SUPPLIER' if task['active']=='create' else 'UPDATE_SUPPLIER' if c and c.get('kind')=='update' else 'SEARCH',
        'reformulation':'Demandes fournisseur conservées dans des emplacements séparés.','extracted':[{'field':k,'value':str(p[k]),'evidence':str(p[k]),'target_index':i} for i,p in enumerate(state.get('partners',[]),1) for k in ('nom','ville','forme_juridique','telephone','ice','capital') if p.get(k)],
        'unknowns':[],'corrections':[],'proposed_action':'READ' if c and task['active']=='control' else 'PREPARE_DRAFT','reply_candidate':reply[:1200]}}
    return {'state':state,'reply':reply,'phase':phase}
def missing(p):
    labels={'nom':'nom','ville':'ville','forme_juridique':'forme juridique','ice':'ICE','identifiant_fiscal':'IF','rc':'RC','adresse':'adresse','telephone':'téléphone','email':'email'}
    return ', '.join(label for key,label in labels.items() if not p.get(key)) or 'aucune information de cette liste'
def summary(state,include_control=False):
    task=workflow(state);rows=[]
    for i,p in enumerate(state.get('partners',[]),1):
        rows.append(str(i)+'. '+(p.get('nom') or 'Nom à préciser')+' — '+(p.get('ville') or 'ville à préciser')+' ; forme : '+(p.get('forme_juridique') or 'inconnue')+' ; capital : '+(p.get('capital') or 'non renseigné')+'. Non renseignés : '+missing(p)+'.')
        check=p.get('duplicate_check',{})
        if check.get('verified'):rows.append('Doublons '+(p.get('nom') or str(i))+' : '+(', '.join(str(m['code'])+' — '+str(m['name']) for m in check.get('matches',[])) or 'aucune correspondance trouvée')+'.')
        elif check:rows.append('Recherche de doublons indisponible pour '+(p.get('nom') or str(i))+'. Vérification en attente.')
    if not rows:rows=['Aucun brouillon fournisseur.']
    c=task.get('control') if include_control else None
    if include_control:
        latest={item['code']:item for item in task.get('history',[]) if item.get('code')}
        if c:latest[c['code']]=c
        for item in latest.values():
            if not c or item['code']!=c['code']:rows.append('Consultation '+item['code']+' : '+item.get('message','lecture non disponible')+(' Demande de modification retirée.' if item.get('status') in ('cancelled','withdrawn') else ''))
        if c and any(item.get('code')==c['code'] and item.get('status')=='cancelled' for item in task.get('history',[])):
            rows.append('Ancienne modification de '+c['code']+' annulée ; consultation uniquement.')
    if c:rows.append('Contrôle indépendant '+c['code']+' : '+c.get('message','en attente de lecture')+(' Nouvelle adresse non fournie : aucun changement proposé.' if c.get('field')=='address' and not c.get('new_value') else ''))
    rows.append('Autorisées : consultations uniquement. Créations en attente de vérification et confirmation, bloquées si doublon. Les champs fiscaux et contacts peuvent rester vides.'+(' Créations suspendues à votre demande.' if state.get('supplier_creation_hold') else '')+' Aucune écriture Sage autorisée par ces messages.')
    return '\n\n'.join(rows)
def read_record(code):
    raw=chat_tools.run([{'id':'task_supplier','tool':'get_supplier_record','args':{'Folder':'TEST','Supplier':code}}]).get('task_supplier',{})
    rows=raw.get('rows',[])
    if not raw.get('ok') or raw.get('folder')!='TEST' or len(rows)!=1 or rows[0].get('folder')!='TEST' or rows[0].get('BPSNUM_0')!=code or rows[0].get('BPRNUM_0')!=code:
        raise crud.CrudError('Lecture exacte de '+code+' indisponible ou fournisseur introuvable dans TEST.',423)
    return rows[0]
def control_read(c):
    try:
        row=read_record(c['code']);c.update(record=row,read_at=now(),status='read')
        active=row.get('supplier_active');partner=row.get('partner_active')
        status='actif' if str(active)==str(partner)=='2' else 'inactif' if str(active)==str(partner)=='1' else 'statuts à vérifier : tiers '+str(partner)+', fournisseur '+str(active)
        c['message']=c['code']+' — '+str(row.get('BPRNAM_0') or 'nom non renseigné')+' : '+status+' dans TEST.'
        return True
    except Exception as exc:
        from app.services.chat_diagnostics import record
        c.update(status='read_unavailable',message='Lecture de '+c['code']+' momentanément indisponible. La demande est conservée ; aucun résultat inventé.',diagnostic_id=record(exc,'supplier_task_read'))
        return False
def check_duplicates(state):
    lines=[]
    for i,p in enumerate(state.get('partners',[]),1):
        if not p.get('nom'):lines.append(str(i)+'. Nom manquant : rapprochement impossible.');continue
        try:
            raw=chat_tools.run([{'id':'task_duplicates','tool':'check_supplier_fiscal_duplicates','args':{'Folder':'TEST','Label':p['nom'],'Supplier':'','Ice':p.get('ice') or '','Fiscal':p.get('identifiant_fiscal') or '','Rc':p.get('rc') or ''}}]).get('task_duplicates',{})
            if not raw.get('ok') or raw.get('folder')!='TEST' or any(r.get('folder')!='TEST' for r in raw.get('rows',[])):raise ValueError('duplicate_read_unavailable')
            matches=[{'code':r.get('BPSNUM_0') or r.get('BPRNUM_0'),'name':r.get('BPRNAM_0') or r.get('BPSNAM_0')} for r in raw.get('rows',[])]
            p['duplicate_check']={'matches':matches,'read_at':now(),'folder':'TEST','verified':True}
            if matches:
                p['approved']=False;p['operation']={'status':'blocked','duplicate_warnings':matches,'validation':{'message':'Correspondances dans TEST : '+', '.join(str(m['code'])+' — '+str(m['name']) for m in matches)+'. Aucune création.'}}
            lines.append(str(i)+'. '+p['nom']+' : '+(', '.join(str(m['code'])+' — '+str(m['name']) for m in matches)+'. Création bloquée.' if matches else 'aucune correspondance retournée par cette recherche TEST ; ce n’est pas une autorisation de création.'))
        except Exception as exc:
            from app.services.chat_diagnostics import record
            p['duplicate_check']={'verified':False,'diagnostic_id':record(exc,'supplier_task_duplicates')}
            lines.append(str(i)+'. '+p['nom']+' : recherche indisponible, conclusion impossible ; création non autorisée.')
    return '\n\n'.join(lines)

def target_partner(text,partners):
    n=re.split(r'\b(?:matbdelch|le deuxieme fournisseur reste|kheli)\b',norm(text),1)[0];ordinal=re.search(r'\b(?:le |au |pour le )?('+ORDINAL+r')\b',n)
    if ordinal and index(ordinal[1])<len(partners):return index(ordinal[1])
    hits=[]
    for i,p in enumerate(partners):
        name=norm(p.get('nom') or '')
        if name and (name in n or name.split()[0] in n.split()):hits.append(i)
        elif p.get('ville') and re.search(r'\bfournisseur\s+de\s+'+re.escape(norm(p['ville']))+r'\b',n):hits.append(i)
    if len(set(hits))==1:return hits[0]
    return 0 if len(partners)==1 else None

def existing_update_target(text,state):
    """Resolve an existing-record request without changing a creation snapshot."""
    n=norm(text)
    if re.search(r'\b(?:article|articl|artcle|produit)\b',n):return None
    if not re.search(r'\b(?:modifi\w*|modif\w*|change\w*|corrige\w*|bdel|nbdl)\b',n):return None
    if not re.search(r'\b(?:ville|vile|mdina|telephone|adresse|nom|email|paiement)\b',n):return None
    code=re.search(r'\bf\d+\b',n)
    if code:return code[0].upper()
    created=[]
    for p in state.get('partners',[]):
        op=p.get('operation') or {}
        if op.get('status')=='succeeded':
            value=(op.get('record_keys') or {}).get('BPSNUM') or ((op.get('result') or {}).get('supplier_verification') or {}).get('code')
            if value:created.append(value)
    return created[0] if len(set(created))==1 else None

def route(text,state,history=(),_recover=True):
    if state.get('articles') or state.get('supplier_target','TEST')!='TEST':return None
    # The independent task controller still handles its own phone/address slots.
    # A verified creation followed by an UPDATE belongs to the modification path.
    if any(p.get('operation',{}).get('status')=='succeeded' for p in state.get('partners',[])) and existing_update_target(text,state):return None
    n=norm(text).strip();s=copy.deepcopy(state);partners=s.setdefault('partners',[])
    # Parse a numbered list atomically, including when a previous group was
    # already created. Supplier names must never collapse into one empty draft.
    markers=list(re.finditer(r'(?<!\w)(\d{1,2})[.)]\s+',text))
    if markers and re.search(r'\bfournisseurs\b',n) and re.search(r'\b(?:preparer?|creer|creation)\b',n):
        if [int(m[1]) for m in markers]!=list(range(1,len(markers)+1)) or len(markers)>10:
            workflow(s);return result(s,'Numérotez les fournisseurs de 1 à 10, sans numéro manquant. Les fiches existantes sont conservées.','supplier_task_question')
        fresh=[]
        for i,m in enumerate(markers):
            segment=text[m.end():markers[i+1].start() if i+1<len(markers) else len(text)].strip()
            columns=re.split(r'\s*[—–]\s*|\s+-\s+',segment)
            legal=re.match(r'(SARL\s+AU|SARL|SAS|SA)\b',columns[2],re.I) if len(columns)>=3 else None
            if not legal:return None
            p=blank();store(p,'nom',columns[0].strip());store(p,'ville',CITY.get(norm(columns[1].strip()),columns[1].strip()));store(p,'forme_juridique',legal[1].upper())
            if re.search(r'\b(?:pas encore|ne disposons pas|sans)\b',n):
                if 'ice' in n:unknown(p,'ice')
                if 'registres de commerce' in n or re.search(r'\brc\b',n):unknown(p,'rc')
            fresh.append(p)
        if any(p.get('operation',{}).get('status')=='executing' for p in partners):
            workflow(s);return result(s,'Une création est en cours. Attendez son résultat avant de changer de groupe.','supplier_task_question')
        task=workflow(s)
        if partners:s.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(partners),'group':copy.deepcopy(task['group']),'reason':'numbered_new_group'})
        s['partners']=fresh;task.update(active='create',group={'id':str(uuid4()),'expected_count':len(fresh),'status':'draft','require_no_duplicates':True})
        duplicates=check_duplicates(s) if re.search(r'\bdoublons?\b',n) else ''
        from app.services.supplier_chat_flow import prepare_state
        messages=[]
        for p in fresh:
            check=p.get('duplicate_check',{})
            if duplicates and (not check.get('verified') or check.get('matches')):
                p['approved']=False;p['operation']={'status':'blocked','validation':{'message':'Création bloquée : doublon trouvé ou recherche non concluante. Consultez les résultats ci-dessus.'}}
            else:messages.append(prepare_state({**s,'partners':[p]}))
        preparation=' '.join(dict.fromkeys(messages))
        return result(s,summary(s)+('\n\n'+duplicates if duplicates else '')+'\n\n'+preparation)
    if re.search(r'\bceer\b',n):
        from app.services.supplier_multiturn import turn
        parsed=turn(text,s,history)
        if parsed and parsed['state'].get('partners'):
            s=parsed['state'];workflow(s)
            from app.services.supplier_chat_flow import prepare_state
            return result(s,prepare_state(s))
    if re.fullmatch(r'(?:oui|ok|d.accord)[.!\s]*',n) and len(partners)==1 and partners[0].get('ice') and len(partners[0]['ice'])!=15:
        workflow(s);return result(s,'L’ICE '+partners[0]['ice']+' contient '+str(len(partners[0]['ice']))+' chiffres au lieu de 15. Quel est l’ICE exact ? Le nom et la ville sont conservés. Ce message ne confirme aucune création.','supplier_task_question')
    if _recover and not partners and history:
        recovered={'articles':[],'partners':[]}
        users=[r.get('content','') for r in history if r.get('role')=='user']
        if users and users[-1]==text:users=users[:-1]
        for previous in users:
            pn=norm(previous)
            # Rebuild literal draft facts only. Never replay a historical SQL
            # lookup, approval, modification or dependency scan.
            if re.search(r'\bf\d+\b|\b(?:sage|base|doublon|confirme|execute|desactiver|reactiver)\b',pn):continue
            if re.search(r'\bannule\b',pn):recovered={'articles':[],'partners':[]};continue
            turn=route(previous,recovered,(),False)
            if turn:recovered=turn['state']
        if recovered.get('supplier_tasks',{}).get('group',{}).get('expected_count',0)>1 and any(p.get('nom') for p in recovered['partners']):
            s['partners']=recovered['partners'];s['supplier_tasks']=recovered['supplier_tasks'];s['supplier_tasks']['recovered_from_user_history']=True;partners=s['partners']
            if recovered.get('supplier_creation_hold'):s['supplier_creation_hold']=True
    if re.search(r'\n\s*(?:[2-9]|1[0-2])\s*\n',text) and len(set(re.findall(r'\bf\d+\b',n)))>1:
        workflow(s)['pending_pasted_request']=text
        return result(s,'Ce message contient plusieurs étapes et plusieurs cibles. Il est conservé. Envoyez la première demande séparément ; aucune modification ni création ne sera lancée.','supplier_task_question')
    darija_new=re.search(r"\b(?:ncreer?|nzid|zid)\s+(?:lina\s+)?fournisseur\s+(?:jdid|tani).*?\bsmitou?\s+(.+?)(?=[,;.]|\s+kayn\s+f\s+|$)",n)
    from app.services.supplier_multiturn import explicit_supplier_creation,turn as literal_turn
    if darija_new:
        if any(p.get('operation',{}).get('status')=='executing' for p in partners):
            return result(s,'Une création est en cours. Consultez son résultat avant de changer les brouillons.','supplier_task_question')
        fresh=blank();store(fresh,'nom',text[darija_new.start(1):darija_new.end(1)].strip())
        city=re.search(r"(?:[,;]\s*(?:kayn\s+)?|\bkayn\s+)f\s+([^,;.]+?)(?=[,;.]|\s+(?:sarl|telephone|ice)\b|$)",n)
        if city:
            value=text[city.start(1):city.end(1)].strip();store(fresh,'ville',CITY.get(norm(value),value))
        legal=re.search(r'\b(sarl\s+au|sarl)\b',n)
        if legal:store(fresh,'forme_juridique',text[legal.start():legal.end()].upper())
        phone=re.search(r'\btelephone\s*(?:est|:)?\s*(0\d{9})(?!\d)',n)
        if phone:store(fresh,'telephone',phone[1])
        if re.search(r'\bice\s+(?:mazal|ma3ndich)',n):unknown(fresh,'ice')
        task=workflow(s)
        same=next((p for p in partners if norm(p.get('nom') or '')==norm(fresh['nom'])),None)
        if same:
            for field in ('ville','forme_juridique','telephone'):
                if fresh.get(field):store(same,field,fresh[field])
        elif partners and re.search(r'\b(?:tani|deuxieme|2eme)\b',n):
            if len(partners)>=10:return result(s,'Dix brouillons maximum par groupe.','supplier_task_question')
            partners.append(fresh)
        else:
            if partners:s.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(partners),'group':copy.deepcopy(task['group']),'reason':'explicit_new_group'})
            s['partners']=[fresh]
        task.update(active='create');task['group']['expected_count']=len(s['partners'])
        return result(s,summary(s))
    if partners and explicit_supplier_creation(text):
        parsed=literal_turn(text,{'articles':[],'partners':[]})
        fresh=parsed['state']['partners'][0] if parsed and parsed['state'].get('partners') else None
        if fresh and fresh.get('nom') and (len(partners)!=1 or norm(partners[0].get('nom') or '')!=norm(fresh['nom'])):
            if any(p.get('operation',{}).get('status')=='executing' for p in partners):return result(s,'Une création est en cours. Consultez son résultat.','supplier_task_question')
            task=workflow(s);s.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(partners),'group':copy.deepcopy(task['group']),'reason':'explicit_new_group'})
            s['partners']=[fresh];task.update(active='create',group={'id':str(uuid4()),'expected_count':1,'status':'draft'})
            return result(s,summary(s))
    count=re.search(r'\b(?:creer?|crrer|crer|ajouter?|zid|nzid)\s+(\d{1,2}|trois)\s+(?:nouveaux?\s+|nevelle\s+)?(?:fournisseurs?|fourniseurs?|frs)\b',n)
    if count:
        size=3 if count[1]=='trois' else int(count[1])
        if not 1<=size<=10:return {'state':s,'reply':'Préparons entre 1 et 10 fournisseurs à la fois. Combien souhaitez-vous préparer ?','phase':'supplier_tasks'}
        if any(p.get('operation',{}).get('status')=='executing' for p in partners):return {'state':s,'reply':'Une création est déjà en cours. Vérifiez son résultat avant une nouvelle préparation.','phase':'supplier_tasks'}
        if partners:s.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(partners),'reason':'explicit_new_group'})
        s['partners']=[blank() for _ in range(size)];task=workflow(s);task.update(active='create',group={'id':str(uuid4()),'expected_count':size,'status':'collecting'})
        return result(s,'Je conserve '+str(size)+' brouillons séparés. Donnez le nom et la ville de chacun, par exemple « le premier… le deuxième… le troisième… ». Aucune création ne sera lancée.','supplier_task_question')
    existing_task=s.get('supplier_tasks')
    # Capture a legacy UPDATE target as an independent slot when switching it.
    last=next((d for d in reversed(s.get('modification_drafts',[])) if d.get('resource')=='supplier' and d.get('operation',{}).get('status') not in ('cancelled','succeeded','ambiguous','executing')),None)
    correction_code=re.search(r'\b(?:kan9sed|kanqsed|je voulais(?:\s+dire)?|je vise|plutot|non[, ]+c.est)\s+(?:fournisseur\s+)?(f\d+)\b',n)
    codes=re.findall(r'\bf\d+\b',n);code=(correction_code[1] if correction_code else codes[0] if codes else None)
    c=(existing_task or {}).get('control')
    if code and re.search(r'\bannule\b',n) and c and c['code']==code.upper():
        cancel_plans(s,c['code']);workflow(s)['history'].append({**copy.deepcopy(c),'status':'cancelled'})
        c={'code':code.upper(),'kind':'search','field':None,'new_value':None};workflow(s).update(control=c,active='control');control_read(c)
        return result(s,'Modification annulée. '+c['message'],'supplier_control')
    if c and c.get('kind')=='update' and c.get('field')=='phone':
        supplied=re.search(r"\b(?:nouveau\s+)?telephone(?:\s+de\s+f\d+)?\s*(?:est|:|=)\s*(0\d{9})(?!\d)",n)
        if supplied and (not code or code.upper()==c['code']):
            from app.services import modification_actions
            d={'id':str(uuid4()),'folder':'TEST','resource':'supplier','code':c['code'],'changes':{'phone':supplied[1]}}
            modification_actions.prepare_draft(d)
            s.setdefault('modification_drafts',[]).append(d);workflow(s)['active']='modify';c['new_value']=supplied[1];c['status']='proposal_to_review'
            return result(s,d['operation'].get('message') or 'Téléphone proposé, sans validation.','modification_preview')
    if c and c.get('kind')=='update' and c.get('field')=='address':
        supplied=re.fullmatch(r"\s*(?:(?:la|l[’'])\s*)?(?:nouvelle\s+)?adresse\s*(?:est|:|=)\s*(.+?)\s*[.]?",n)
        if supplied:
            value=text[supplied.start(1):supplied.end(1)].strip()
            from app.services import modification_actions
            d={'id':str(uuid4()),'folder':'TEST','resource':'supplier','code':c['code'],'changes':{'address':value}}
            modification_actions.prepare_draft(d)
            s.setdefault('modification_drafts',[]).append(d);workflow(s)['active']='modify';c['new_value']=value
            return result(s,d['operation'].get('message') or 'Nouvelle adresse proposée. Vérifiez les anciennes et nouvelles valeurs avant toute confirmation.','modification_preview')
    if not c and last and correction_code:
        task=workflow(s);task['control']={'code':last['code'],'kind':'update','field':last.get('pending_field'),'status':'needs_input'};c=task['control']
    if correction_code and c:
        old=copy.deepcopy(c);cancel_plans(s,old['code']);workflow(s)['history'].append({**old,'status':'withdrawn'})
        newcode=code.upper();c={'code':newcode,'kind':old['kind'],'field':old.get('field'),'status':'needs_input','new_value':None};workflow(s).update(control=c,active='control');s.pop('modification_pending_target',None)
        if control_read(c):c['message']+=' La cible '+old['code']+' est retirée de cette demande.'
        if c.get('field')=='phone':c['message']+=' Quel nouveau téléphone faut-il retenir ? Aucun changement préparé.'
        if c.get('field')=='address':c['message']+=' Quelle nouvelle adresse faut-il retenir pour '+newcode+' ? Aucune valeur n’a été proposée.'
        return result(s,c['message'],'supplier_control')
    reactivation=bool(re.search(r'\b(?:reactiver|reactivation)\b',n))
    disabling=bool(re.search(r'\b(?:desactiver|desactivation)\b',n))
    searching=bool(re.search(r'\b(?:cherche|recherche|consulte)\b',n) and code)
    address_request=bool(code and re.search(r'\b(?:nbdl|nbdel|modifi\w*|change)\b.*\badresse\b',n))
    if address_request:
        from app.services.modification_dialogue import parse_changes
        if parse_changes(text,'supplier').get('address'):address_request=False
    # Leave standalone UPDATE conversations to the established modification
    # dialogue, which also handles immediate values and successive corrections.
    phone_request=bool((existing_task or partners) and code and re.search(r'\b(?:nbdl|nbdel|modifi\w*|change)\b.*\btelephone\b',n))
    if code and (searching or disabling or reactivation or address_request or phone_request):
        task=workflow(s)
        if task.get('control'):cancel_plans(s,task['control']['code']);task['history'].append(copy.deepcopy(task['control']))
        kind='reactivate_check' if reactivation else 'disable_check' if disabling else 'update' if address_request or phone_request else 'search'
        c={'code':code.upper(),'kind':kind,'field':'address' if address_request else 'phone' if phone_request else None,'new_value':None,'status':'needs_input'};task.update(control=c,active='control');s.pop('modification_pending_target',None)
        control_read(c)
        if phone_request:c['message']+=' Nouveau numéro non fourni : aucun changement préparé.'
        if address_request:c['message']+=' Nouvelle adresse non fournie : quelle adresse souhaitez-vous retenir ? Aucun changement préparé.'
        if disabling and not reactivation:
            try:
                from app.services import erp_modification
                from app.services.modification_policy import ArticleDependencyAnalyzer
                analysis=ArticleDependencyAnalyzer().analyze(erp_modification.snapshot('supplier',c['code']));c['dependencies']=analysis
                c['message']+=' Dépendances : '+str(analysis['sources_checked'])+' tables contrôlées ; '+('analyse complète' if analysis['complete'] else 'couverture incomplète')+'. '+str(len(analysis['active']))+' utilisations actives, '+str(len(analysis['unknown_activity']))+' statuts non démontrés.'
            except Exception as exc:
                from app.services.chat_diagnostics import record
                c['dependency_diagnostic']=record(exc,'supplier_dependency_read');c['message']+=' Le contrôle des commandes, réceptions et factures n’a pas abouti ; aucune conclusion de compatibilité.'
            c['message']+=' Désactivation fournisseur non prise en charge par le module validé : aucun plan ni écriture autorisés.'
        if reactivation:c['message']+=' Il s’agit uniquement d’une consultation. '+('Aucune réactivation nécessaire : le fournisseur est déjà actif.' if str(c.get('record',{}).get('supplier_active'))==str(c.get('record',{}).get('partner_active'))=='2' else 'La réactivation fournisseur nécessite une méthode métier validée ; aucun plan ni écriture autorisés.')
        return result(s,c['message'],'supplier_control')
    if re.search(r'\b(?:resume|resumer|manquantes?|baqi|ba9i|na9es|reviens)\b',n) and (partners or existing_task) and not re.search(r'\bcorrige\b',n):
        task=workflow(s)
        if 'reviens' in n and re.search(r'\b(?:3|trois)\b',n) and len(partners)!=3:
            previous=next((a for a in reversed(s.get('supplier_archives',[])) if len(a.get('partners',[]))==3),None)
            if previous:
                s.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(partners),'group':copy.deepcopy(task['group']),'reason':'switched_group'})
                s['partners']=copy.deepcopy(previous['partners']);task['group']=copy.deepcopy(previous.get('group') or {'id':str(uuid4()),'expected_count':3,'status':'draft'})
        if not task.get('control') and last:
            field=last.get('pending_field') or next(iter(last.get('changes',{})),None)
            value=last.get('changes',{}).get(field)
            unsafe=isinstance(value,str) and bool(re.search(r'\b(?:kan9sed|machi\s+f\d+)\b',norm(value)))
            if unsafe:cancel_plans(s,last['code']);value=None
            task['control']={'code':last['code'],'kind':'update','field':field,'new_value':value,'status':'needs_input' if not value else 'proposal_to_review','message':'Demande concernant '+last['code']+' conservée ; '+('nouvelle valeur à préciser.' if not value else 'proposition existante à relire, sans nouvelle autorisation.')}
        if 'reviens' in n:task['active']='create'
        return result(s,summary(s,include_control=bool(re.search(r'\b(?:demandes|deux|controles?)\b|\bf\d+\b',n))),'supplier_summary')
    if partners and (re.search(r'\b(?:conserve seulement|ne cree rien|pour le moment|continuera plus tard)\b',n)):
        task=workflow(s);task['group']['status']='paused';task['active']='create';s['supplier_creation_hold']=True
        for p in partners:
            if p.get('operation',{}).get('status') not in TERMINAL:p['approved']=False;p['operation']={'status':'blocked','validation':{'message':'Création suspendue à votre demande. Brouillon conservé.'}}
        return result(s,'Les brouillons sont conservés pour plus tard. Les créations sont suspendues ; aucune écriture Sage.')
    if partners and re.search(r'\breprends?\s+(?:la\s+)?preparation\b',n):
        workflow(s)['group']['status']='draft';s['supplier_creation_hold']=False
        return result(s,'Préparation reprise. Vérifiez les informations ; une nouvelle confirmation sera nécessaire avant toute création.')
    duplicate_request=bool(re.search(r'\b(?:deja|doublons?|kaynin|l9itih)\b|\bwach\b.{0,45}\bkayn\b',n) and re.search(r'\b(?:base|sage|test|matcreihch|wrini|tchouf|chof|chouf|9elleb|avant|verifie|verifier)\b',n))
    if partners and duplicate_request:
        task=workflow(s);task['active']='create';task['group']['require_no_duplicates']=True
        # Return the already checked records when asked to display them, without
        # repeating a stale error instead of answering a new operation.
        if re.search(r'\b(?:wrini|affiche|informations)\b',n) and all(p.get('duplicate_check',{}).get('verified') for p in partners):
            reply='\n\n'.join((p.get('nom') or 'Fournisseur')+' : '+(', '.join(str(r['code'])+' — '+str(r['name']) for r in p['duplicate_check']['matches']) or 'aucune correspondance retournée.') for p in partners)
        else:reply=check_duplicates(s)
        return result(s,reply+' Aucune création effectuée.','supplier_duplicate_read')
    phone_correction=re.search(r"\b(?:bon\s+numero|telephone|telefon|tel)\s*(?:(?:c.est|est|:)\s*)?(0\d{9})(?!\d)",n)
    if partners and phone_correction and not code:
        ix=target_partner(text,partners)
        if ix is not None:
            store(partners[ix],'telephone',phone_correction[1]);workflow(s)['active']='create'
            return result(s,summary(s))
    # Ordinal list: names and locations are separate, even in Darija/French prose.
    chunks=list(re.finditer(r'\b(?:le |pour le )?('+ORDINAL+r')\b\s*(?:c.est\s+)?',n)) if len(partners)>1 else []
    changed=False
    if chunks:
        for j,m in enumerate(chunks):
            ix=index(m[1]);part=text[m.end():chunks[j+1].start() if j+1<len(chunks) else len(text)].strip(' ,;.');part=re.sub(r'\s+et\s*$','',part,flags=re.I)
            if ix>=len(partners):continue
            p=partners[ix];partn=norm(part)
            legal=re.search(r'\b(sarl\s+au|sarl|sa|sas)\b',partn)
            if legal:store(p,'forme_juridique',part[legal.start():legal.end()].upper());changed=True
            elif 'forme juridique' in partn and re.search(r'pas|connais|inconn',partn):unknown(p,'forme_juridique');changed=True
            else:
                locations=list(re.finditer(r'(?=\s+(?:a|f)\s+([^,;.]+)$)',partn))
                location=locations[-1] if locations else None
                if location:
                    name=part[:location.start()].strip();city=part[location.start(1):location.end(1)].strip()
                    if name:store(p,'nom',name);store(p,'ville',CITY.get(norm(city),city));changed=True
        if changed:workflow(s)['active']='create';return result(s,summary(s))
    if partners and (existing_task or re.search(r'\b(?:had fournisseur|rah|walakin|ma3ndich|mabghitch|capital|ville aussi)\b',n) or re.search(r'\bnom\s*,\s*c.est',n)):
        ix=target_partner(text,partners);p=partners[ix] if ix is not None else None
        corrected_name=re.search(r'(?:smiya\s+s7i7a|smito|(?:le\s+)?nom\s*[,;]?\s*(?:c.est|est))\s+([^,;.]+)',n)
        if p and corrected_name and re.search(r'\b(?:non|corrige|tromp\w*|machi|s7i7a)\b',n):
            value=text[corrected_name.start(1):corrected_name.end(1)].strip()
            value=re.split(r'\s+(?:corrige|les autres|pas|machi)\b',value,1,flags=re.I)[0].strip(' ,;.')
            store(p,'nom',value);changed=True
        city=re.search(r'\bville\s+(?:aussi\s+)?(?:c.est|est|:)\s*(?:finalement\s+c.est\s+)?([^,;.]+?)(?=\s*[,;.]|\s+(?:machi|pas)\b|$)',n)
        if p and city:store(p,'ville',text[city.start(1):city.end(1)].strip());changed=True
        if p:
            for cue,field in [('ice','ice'),('telephone','telephone'),('email','email')]:
                if re.search(r'\b'+cue+r'\b',n) and re.search(r'\b(?:pas|ma3ndich|mabghitch|connais|inconnu|daba)\b',n):unknown(p,field);changed=True
            legal=re.search(r'\b(sarl\s+au|sarl)\b',n)
            if legal and not re.search(r'\b(?:premier|2eme|3eme)\b',n):store(p,'forme_juridique',text[legal.start():legal.end()].upper());changed=True
            capital=re.search(r'\bcapital\s+(?:de\s+)?(\d[\d ]*\s*(?:dh|mad)?)',n)
            if capital:store(p,'capital',text[capital.start(1):capital.end(1)].strip());changed=True
        # Each named clause is resolved separately; never spread a phone across all rows.
        if len(partners)>1:
            for part in re.split(r'\bmais\b|[,;]',text,flags=re.I):
                target=target_partner(part,partners)
                if target is None:continue
                phone=re.search(r"\btelephone\s*(?:c.est|est|:)?\s*(0\d{9})(?!\d)",norm(part))
                if phone:store(partners[target],'telephone',phone[1]);changed=True
                if 'ice' in norm(part) and re.search(r'pas|ma3ndich',norm(part)):unknown(partners[target],'ice');changed=True
                if 'telephone' in norm(part) and re.search(r'pas|ma3ndich',norm(part)):unknown(partners[target],'telephone');changed=True
        if changed:workflow(s)['active']='create';return result(s,summary(s))
    return None

def apply_analysis(text,state):
    task=state.get('supplier_tasks')
    if not task:return None
    if existing_update_target(text,state):return None
    s=copy.deepcopy(state);envelope=s.get('conversation_analysis',{});a=envelope.get('analysis',{})
    if envelope.get('status')!='validated':return None
    facts=a.get('extracted',[]) if envelope.get('status')=='validated' else []
    absent=a.get('scoped_unknowns',[]) if envelope.get('status')=='validated' else []
    rows=s.get('partners',[])
    if len(rows)==1:
        for f in facts+absent:
            if f.get('target_index') is None:f['target_index']=1
    all_items=facts+absent
    if a.get('intent')=='CHAT' or a.get('proposed_action')=='CHAT':return None
    if not all_items and not re.search(r'\b(?:fournisseur|fiche|premier|deuxieme|ville|adresse|telephone|nom|ice|paiement|capital|sarl)\b',norm(text)):return None
    if any(p.get('operation',{}).get('status') in TERMINAL for p in rows):return None
    whole_target=target_partner(text,rows) if len(re.findall(r'\b'+ORDINAL+r'\b',norm(text)))<=1 else None
    grounded=all(f.get('target_index') is not None and 1<=f['target_index']<=len(rows) and (target_partner(f.get('evidence',''),rows)==f['target_index']-1 or whole_target==f['target_index']-1) for f in all_items)
    if task['active']=='create' and all_items and grounded and a.get('intent') in ('CREATE_SUPPLIER','UPDATE_SUPPLIER') and a.get('proposed_action')=='PREPARE_DRAFT':
        try:
            staged=copy.deepcopy(s)
            for f in facts:store(staged['partners'][f['target_index']-1],f['field'],f['value'])
            for f in absent:unknown(staged['partners'][f['target_index']-1],f['field'])
            return result(staged,summary(staged))
        except ValueError:pass
    c=task.get('control')
    if task['active']=='control' and c:
        reply='La demande concernant '+c['code']+' est conservée. '+('Il manque uniquement la nouvelle adresse. Quelle adresse souhaitez-vous retenir ?' if c.get('field')=='address' and not c.get('new_value') else 'Précisez le contrôle supplémentaire souhaité. Aucune modification n’a été préparée.')
    else:
        target=target_partner(text,rows)
        reply=('La fiche '+(rows[target].get('nom') or str(target+1))+' est conservée. Précisez uniquement le champ et la valeur à corriger.' if target is not None else 'Vos demandes et les informations de chaque fiche sont conservées. Précisez le fournisseur (nom ou numéro dans la liste), puis le champ concerné.')
    return result(s,reply+' Aucune écriture Sage.','supplier_task_clarification')
