"""Literal coefficient follow-ups on one pending article; no ERP operations."""
import copy,re
from decimal import Decimal,InvalidOperation
from app.services.chat_turns import norm

TERMINAL={'cancelled','succeeded','executing','failed','ambiguous','unverified'}

def creation_followup(text,state):
    """A full equality is structured data, never a scalar coefficient."""
    if '=' not in text:return None
    if (state.get('conversation_focus') or {}).get('intent')=='modify':return None
    active=[a for a in state.get('articles',[]) if a.get('operation',{}).get('status') not in TERMINAL]
    if len(active)!=1:return None
    a=active[0];stock=a.get('unite');sale=a.get('unite_vente')
    if not stock or not sale or stock==sale:return None
    if re.search(r'\b(?:annul\w*|supprim\w*|creer)\b',norm(text)):return None
    changed=copy.deepcopy(state);a=next(a for a in changed['articles'] if a['id']==active[0]['id'])
    match=re.search(r'\b1\s*([a-z][a-z0-9]{0,4})\s*=\s*(\d+(?:[.,]\d+)?)\s*([a-z][a-z0-9]{0,4})\b',text,re.I)
    if text.count('=')!=1 or not match or {match[1].upper(),match[3].upper()}!={stock,sale} or Decimal(match[2].replace(',','.'))<=0:
        message='Donnez une seule égalité entre '+stock+' et '+sale+', par exemple « 1 '+stock+' = 1000 '+sale+' », uniquement si elle correspond à votre article. Une chaîne contenant plusieurs signes = n’est pas un coefficient. Les valeurs précédentes sont conservées.'
        a['operation']={'status':'blocked','message':message}
    else:
        coefficient=format(Decimal(match[2].replace(',','.')),'f')
        a['coefficient_vente_declare']=coefficient
        a['conversion_vente_declaree']={'source_unit':match[1].upper(),'target_unit':match[3].upper(),'coefficient':coefficient,'evidence':text}
        a['operation']={'status':'invalidated'}
        from app.services.article_sql_dialogue import prepare_state
        message=prepare_state(changed)
    from app.services import chat_article_sql_actions
    chat_article_sql_actions.PERMITS.pop(a['id'],None)
    a.update(approved=False,reviewed=False)
    changed['tool_orchestration']={'version':1,'provider':'literal_creation_conversion','calls':[],'sage_writes':0}
    return {'state':changed,'reply':message,'phase':'creation_unit_conversion'}

def followup(text,state):
    n=norm(text)
    equality=re.search(r'\b1\s*([a-z][a-z0-9]{0,4})\s*=\s*(\d+(?:[.,]\d+)?)\s*([a-z][a-z0-9]{0,4})\b',text,re.I)
    if not equality and not re.search(r'\b(?:coefficient|coeficient|cofission|cofision|cofiss?ion|conversion)\b',n):return None
    # Refuse compound commands: this path only records a literal conversion.
    if re.search(r'\b(?:annul\w*|supprim\w*|creer|modifi\w*|confirme\w*)\b',n):return None
    number=re.search(r'\b(?:coefficient|coeficient|cofission|cofision|cofiss?ion|conversion)\s*(?:(?:est|de|:|=)\s*)?(\d+(?:[.,]\d+)?)\b',text,re.I)
    if not number and not equality:return None
    try:
        coefficient=Decimal((equality[2] if equality else number[1]).replace(',','.'))
        if not coefficient.is_finite() or coefficient<=0 or coefficient.adjusted()>20:return None
    except InvalidOperation:return None
    pending=[d for d in state.get('modification_drafts',[]) if d.get('resource')=='article' and d.get('operation',{}).get('status') not in TERMINAL and any(k in d.get('changes',{}) for k in ('stock_unit','purchase_unit','sale_unit'))]
    if len(pending)!=1:return None
    changed=copy.deepcopy(state);d=next(d for d in changed['modification_drafts'] if d['id']==pending[0]['id'])
    current=d.get('current') or {};changes=d['changes']
    known={str(v).upper() for k,v in current.items() if k in ('stock_unit','purchase_unit','sale_unit') and isinstance(v,str)}
    known.update(str(v.get('code') if isinstance(v,dict) else v).upper() for k,v in changes.items() if k in ('stock_unit','purchase_unit','sale_unit'))
    direction=re.search(r'\b([a-z0-9]{1,5})\s+(?:vers|vere|ver|a)\s+([a-z0-9]{1,5})\b',n)
    previous=d.get('unit_conversion_requests') or []
    source,target=(direction[1].upper(),direction[2].upper()) if direction and {direction[1].upper(),direction[2].upper()}<=known else (None,None)
    if equality:
        source,target=equality[1].upper(),equality[3].upper()
        if not {source,target}<=known:return None
    if not source and previous:source,target=previous[-1].get('source_unit'),previous[-1].get('target_unit')
    if equality and re.search(r'\b(?:corrig\w*|remplace\w*|plutot)\b',n):
        # An explicit correction replaces only this pair, retaining other pairs.
        superseded=[r for r in previous if r.get('status')=='declared_equivalence' and {r.get('source_unit'),r.get('target_unit')}=={source,target}]
        d.setdefault('unit_conversion_history',[]).extend(copy.deepcopy(superseded))
        d['unit_conversion_history']=d['unit_conversion_history'][-20:]
        previous=[r for r in previous if r not in superseded]
    request={'coefficient':format(coefficient,'f'),'source_unit':source,'target_unit':target,'status':'declared_equivalence' if equality else 'needs_equivalence','evidence':text}
    if not equality and not direction and previous and previous[-1].get('status')=='declared_equivalence' and all(previous[-1].get(k)==request.get(k) for k in ('coefficient','source_unit','target_unit')):
        request=copy.deepcopy(previous[-1])
    if previous and all(previous[-1].get(k)==request.get(k) for k in ('coefficient','source_unit','target_unit')):previous[-1]=request
    else:previous.append(request)
    d['unit_conversion_requests']=previous[-10:]
    conflicts=[]
    declarations=[r for r in d['unit_conversion_requests'] if r.get('status')=='declared_equivalence']
    for i,left in enumerate(declarations):
        for right in declarations[i+1:]:
            if {left['source_unit'],left['target_unit']}!={right['source_unit'],right['target_unit']}:continue
            a,b=Decimal(left['coefficient']),Decimal(right['coefficient'])
            consistent=a==b if left['source_unit']==right['source_unit'] else a*b==1
            if not consistent:conflicts.append('1 '+left['source_unit']+' = '+left['coefficient']+' '+left['target_unit']+' contredit 1 '+right['source_unit']+' = '+right['coefficient']+' '+right['target_unit'])
    d['unit_conversion_conflicts']=conflicts
    d['unit_conversion_changes']=copy.deepcopy(changes)
    message='Le coefficient '+request['coefficient']+' est conservé pour '+d['code']+'. '
    if request['status']=='declared_equivalence':
        message+='Équivalence déclarée : 1 '+source+' = '+request['coefficient']+' '+target+'. Cette valeur reste à vérifier ; elle ne modifie pas les conversions Sage.'
    elif source and target:
        message+='Pour '+source+' → '+target+', voulez-vous dire « 1 '+source+' = '+request['coefficient']+' '+target+' » ou « 1 '+target+' = '+request['coefficient']+' '+source+' » ?'
    else:message+='Entre quelles unités et dans quel sens ? Donnez une égalité complète, par exemple « 1 RLX = 1000 M2 », uniquement si elle correspond à votre article.'
    stock=changes.get('stock_unit');old=current.get('stock_unit')
    missing_stock=bool(stock and old and stock!=old and not any({r['source_unit'],r['target_unit']}=={old,stock} for r in declarations))
    if stock and old and stock!=old:
        if missing_stock:message+=' Pour le changement de stock '+old+' → '+stock+', la relation '+old+' / '+stock+' reste à préciser.'
        elif not conflicts:message+=' La relation '+old+' / '+stock+' est renseignée. Le module actuel ne prend pas en charge cette migration de l’unité de stock avec recalcul des conversions. Ce blocage est technique ; aucun autre coefficient ne vous est demandé pour le contourner.'
    if conflicts:message+=' Équivalences contradictoires : '+' ; '.join(conflicts)+'. Indiquez celle à retenir avec « corrige : 1 … = … … ».'
    message+=' Les deux unités demandées sont conservées ; aucune modification Sage appliquée.'
    from app.services import modification_actions
    modification_actions.PERMITS.pop(d['id'],None)
    status='blocked' if conflicts or (request['status']=='declared_equivalence' and stock and old and stock!=old and not missing_stock) else 'needs_input'
    d.update(approved=False,sensitive_approved=False,operation={'status':status,'message':message})
    changed['conversation_focus']={'intent':'modify','resource':'article','operation_id':d['id'],'expected_fields':['conversion_correction'] if conflicts else [] if status=='blocked' else ['conversion_equivalence'],'source':'server'}
    changed['tool_orchestration']={'version':1,'provider':'literal_conversion_followup','calls':[],'sage_writes':0}
    return {'state':changed,'reply':message,'phase':'unit_conversion_followup'}
