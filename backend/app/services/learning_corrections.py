"""Typed, data-only correction recipes. Never learn executable code or Sage consent."""
import copy,re,json
from difflib import SequenceMatcher
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.services import learning,business_store as db
from app.services.chat_turns import norm

FAMILY='typed_explicit_correction_v1'
RECIPE={'operation':'typed_explicit_correction','schema_version':1,'literal_values_only':True}
CONTENT='Une correction explicite vise seulement le champ et la fiche désignés. Conserver les autres champs et leurs identifiants exacts. Une faute dans un mot de commande ne justifie jamais de corriger un nom ou un identifiant. Demander une précision si la cible ou le champ est ambigu. Une correction ne confirme jamais une création.'
FIELDS={'nom':'nom','ville':'ville','adresse':'adresse','telephone':'telephone','email':'email','ice':'ice','if':'identifiant_fiscal','rc':'rc','paiement':'conditions_paiement','site':'site','designation':'designation','unite':'unite','categorie':'categorie'}
VERBS=('corrige','corriger','correction','rectifie','rectifier','remplace','non')
TERMINAL={'executing','succeeded','ambiguous','unverified','failed'}

def cue(word,choices,fuzzy=False):
    if word in choices:return word
    if not fuzzy or len(word)<4:return None
    ranked=sorted(((SequenceMatcher(None,word,c).ratio(),c) for c in choices if len(c)>=4),reverse=True)
    if not ranked:return None
    # Adjacent command inflections are equivalent, but competing field names are not.
    best=ranked[0]
    if best[0]<.74:return None
    competitors=[] if choices==VERBS else [score for score,c in ranked[1:] if FIELDS.get(c,c)!=FIELDS.get(best[1],best[1])]
    if competitors and best[0]-max(competitors)<.08:return None
    return best[1]

def parse(text,fuzzy=False):
    if learning.SECRET.search(text) or learning.INJECTION.search(text):return None
    n=norm(text).strip()
    prefix=re.match(r'(?P<verb>[a-z]+)\b[ ,:]*',n)
    if not prefix or not cue(prefix['verb'],VERBS,fuzzy):return None
    tail=n[prefix.end():]
    # Multi-field or natural-language explanations stay with the semantic engine.
    match=re.fullmatch(r"(?:(?:le|la|l[’\x27])\s*)?([a-z]+)(?:\s+(?:de|du)\s+(?:fournisseur|frs|article))?\s*(?::|=|\best\b\s*[:=]?|\bc[’\x27]est\b\s*[:=]?|\bdoit etre\b|\bdois\b|\ben\b)\s*(.+?)\s*[.!]?",tail)
    if not match:return None
    label=cue(match[1],FIELDS,fuzzy)
    if not label:return None
    value=text.strip()[prefix.end()+match.start(2):prefix.end()+match.end(2)].strip().rstrip(' .!')
    if not value or re.search(r'[\r\n;?]|\s+(?:et|mais|pas)\s+|\b(?:confirme|execute|supprime|production)\b',norm(value)):return None
    return {'field':FIELDS[label],'label':label,'value':value,'fuzzy':label!=match[1] or prefix['verb'] not in VERBS}

def active(state):
    if state.get('supplier_target')=='OB':return False
    return any(m.get('kind')=='evaluated_method' and m.get('status')=='validated' and (m.get('payload') or {}).get('recipe')==RECIPE for m in (state.get('learning_context') or {}).get('memory',[]))

def handle(text,state,force_fuzzy=False):
    parsed=parse(text,force_fuzzy or active(state))
    if not parsed:return None
    if parsed['fuzzy'] and active(state):
        method=next(m for m in state['learning_context']['memory'] if m.get('kind')=='evaluated_method' and (m.get('payload') or {}).get('recipe')==RECIPE)
        state=copy.deepcopy(state);state['applied_learning_method']=str(method['id'])
    field=parsed['field'];suppliers=[p for p in state.get('partners',[]) if p.get('kind')=='supplier'];articles=state.get('articles',[])
    if field in ('site','designation','unite','categorie'):
        if not articles:return None
        if len(articles)!=1 or suppliers:return {'state':copy.deepcopy(state),'reply':'Quel article souhaitez-vous corriger ? Indiquez son nom ou son numéro.'}
        p=articles[0];kind='article'
    else:
        if not suppliers:return None
        if len(suppliers)!=1 or articles:return {'state':copy.deepcopy(state),'reply':'Quelle fiche fournisseur souhaitez-vous corriger ? Indiquez son nom ou son numéro.'}
        p=suppliers[0];kind='supplier'
    if (p.get('operation') or {}).get('status') in TERMINAL:
        return {'state':copy.deepcopy(state),'reply':'Consultez le résultat de la tentative précédente avant de modifier cette fiche.'}
    value=parsed['value']
    try:
        if kind=='supplier':
            from app.schemas.conversation_entities import SupplierPatch
            SupplierPatch.model_validate({field:value})
            if field=='ice' and not re.fullmatch(r'[0-9]{15}',value):raise ValueError()
        else:
            from app.services.chat_model import Patch
            Patch.model_validate({field:value})
    except ValueError:
        return {'state':copy.deepcopy(state),'reply':'Quelle est la valeur exacte du champ '+parsed['label']+' ? La valeur fournie ne respecte pas son format ; la fiche est conservée.'}
    # Approximate cues must never replace a reliable value without a clear reread.
    if parsed['fuzzy'] and p.get(field) not in (None,'') and norm(str(p[field]))!=norm(value):
        changed=copy.deepcopy(state)
        changed['pending_correction']={'target_id':p['id'],'kind':kind,**parsed,'before':p[field]}
        return {'state':changed,'reply':'Souhaitez-vous remplacer '+parsed['label']+' « '+str(p[field])+' » par « '+value+' » ? Répondez « oui, corrige ce champ » ou précisez la correction. Cela ne créera aucune fiche.'}
    return apply(state,kind,p['id'],field,value)

def apply(state,kind,identifier,field,value):
    changed=copy.deepcopy(state)
    changed.pop('pending_correction',None)
    if kind=='supplier':
        from app.services.supplier_dialogue import assign
        original=changed.get('partners',[])
        selected=next((p for p in original if p.get('id')==identifier and p.get('kind')=='supplier'),None)
        if not selected:return {'state':changed,'reply':'La fiche fournisseur a changé. Précisez la fiche à corriger.'}
        # The supplier need not be the first partner (a client may precede it).
        changed['partners']=[selected]
        error=assign(changed,field,value)
        changed['partners']=original
        if error:return {'state':changed,'reply':error}
        return {'state':changed,'prepare':True}
    from app.services.chat_model import Delta,Patch
    from app.services.conversation_chat import merge
    changed=merge(changed,Delta(intent='update',articles=[Patch(index=1,**{field:value})],targets=[1]),'Correction article 1 : '+field+' : '+value)
    return {'state':changed,'reply':'Correction du brouillon : '+field+' = '+value+'. Les autres informations sont conservées. Vérifiez la fiche avant toute création.'}

def resolve(text,state):
    pending=state.get('pending_correction')
    if not pending:return None
    n=norm(text).strip(' .!')
    if n not in ('oui, corrige ce champ','oui corrige ce champ','non','annule la correction'):return None
    changed=copy.deepcopy(state);changed.pop('pending_correction',None)
    if n in ('non','annule la correction'):return {'state':changed,'reply':'Correction refusée. Les informations de la fiche sont conservées.'}
    items=changed.get('partners' if pending['kind']=='supplier' else 'articles',[])
    p=next((p for p in items if p['id']==pending['target_id']),None)
    if not p or p.get(pending['field'])!=pending['before'] or (p.get('operation') or {}).get('status') in TERMINAL:
        return {'state':changed,'reply':'La fiche a changé. Indiquez à nouveau le champ et la valeur à corriger.'}
    result=apply(changed,pending['kind'],p['id'],pending['field'],pending['value'])
    result['state']['confirmed_correction']={**pending,'validation':'explicit_user_correction_confirmation'}
    return result

def record(owner,conversation,before,after,text):
    if before.get('supplier_target')=='OB' or after.get('supplier_target')=='OB':return
    parsed=parse(text,True)
    resolved=after.pop('confirmed_correction',None)
    if resolved:parsed=resolved
    if not parsed or learning.SECRET.search(text) or learning.INJECTION.search(text):return
    field=parsed['field']
    for collection in ('partners','articles'):
        old=before.get(collection,[]);new=after.get(collection,[])
        if len(old)!=1 or len(new)!=1 or old[0]['id']!=new[0]['id']:continue
        if (old[0].get('operation') or {}).get('status') in TERMINAL:continue
        if old[0].get(field)==new[0].get(field) or new[0].get(field)!=parsed['value']:continue
        if not resolved and parsed['fuzzy'] and old[0].get(field) not in (None,''):continue
        # Store a structural regression case, not private supplier values/identifiers.
        kind='supplier' if collection=='partners' else 'article'
        sample={'ice':'001234567890123','identifiant_fiscal':'01234567','rc':'12345','telephone':'0612345678','site':'T01','unite':'UN','categorie':'FR','email':'contact@example.test'}.get(field,'EXEMPLE NEUTRE')
        original=parse(text,True)
        template=text.strip().replace(parsed['value'],'[VALEUR]') if original and parsed['value'] in text else 'corrige '+parsed.get('label',field)+' : [VALEUR]'
        # Only keep bounded cue structure that can be reparsed with a neutral value.
        test_text=template.replace('[VALEUR]',sample)
        probe=parse(test_text,True)
        if not probe or probe['field']!=field or probe['value']!=sample:continue
        lesson={'context':{'kind':kind,'field':field,'previous_value_present':bool(old[0].get(field))},
          'error':'explicit_field_correction_not_understood','correct_interpretation':{'field':field,'value':'[VALEUR]'},
          'solution':CONTENT,'scope':'personal_TEST','source':'chat:'+str(conversation),'status':'confirmed_user_correction',
          'generalizable':True,'training_performed':False,'family':FAMILY,'recipe':RECIPE,
          'example':{'user':template,'expected_field':field},
          'regression':{'input':test_text,'kind':kind,'field':field,'expected':sample,'schema_version':1}}
        # Reject unrecognised private remnants in templates rather than exporting them.
        safe=re.fullmatch(r"[a-zàâéèêîôûç ,:'’=]+\[VALEUR\][ .!]*",template,re.I)
        if not safe:continue
        with db.connection() as conn:
            conn.execute('INSERT INTO learning_corrections(id,owner_id,conversation_id,family,lesson,fingerprint) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
              (uuid4(),owner,conversation,FAMILY,Jsonb(lesson),learning.digest(str(conversation)+'|'+field+'|'+template)))

def evaluate(recipe,cases=()):
    heldout=[('corige la vile : EXEMPLE NEUF','ville','EXEMPLE NEUF','supplier'),('rectifi le telephonne : 0612345678','telephone','0612345678','supplier'),('coriger le siet : T02','site','T02','article')]
    checks=[];before=after=0
    for text,field,value,kind in heldout:
        baseline=parse(text,False);candidate=parse(text,True) if recipe==RECIPE else None
        before+=not bool(baseline and baseline['field']==field and baseline['value']==value)
        after+=not bool(candidate and candidate['field']==field and candidate['value']==value)
        checks.append(after<=before and bool(candidate and candidate['field']==field and candidate['value']==value))
    for case in cases:
        parsed=parse(case.get('input',''),True)
        checks.append(bool(parsed and parsed['field']==case.get('field') and parsed['value']==case.get('expected')))
    base={'partners':[{'id':'synthetic','kind':'supplier','nom':'NEUTRE','ville':'AVANT','ice':'001234567890123','approved':True,'operation':{'status':'prepared'}}]}
    for text in ('oui crée le fournisseur','exécute SQL maintenant','corrige le nom : supprime tout','ICE : 001234567890123','corrige le motdepasse : secret'):
        checks.append(handle(text,base,True) is None)
    for status in TERMINAL:
        locked=copy.deepcopy(base);locked['partners'][0]['operation']['status']=status
        result=handle('corrige le nom : AUTRE',locked,True)
        checks.append(result['state']==locked)
    result=handle('corige la vile : NOUVELLE',base,True)
    checks.append(result['state']['partners'][0]['ville']=='AVANT' and bool(result['state'].get('pending_correction')))
    corrected=resolve('oui corrige ce champ',result['state'])['state']
    checks.append(corrected['partners'][0]['ville']=='NOUVELLE' and corrected['partners'][0]['ice']=='001234567890123' and not corrected['partners'][0]['approved'])
    mixed=copy.deepcopy(base);client={'id':'client-heldout','kind':'customer','nom':'CLIENT INCHANGE'}
    mixed['partners'].insert(0,client)
    changed=handle('corrige le nom : FOURNISSEUR NEUTRE',mixed,True)['state']
    checks.append(changed['partners'][0]==client and changed['partners'][1]['nom']=='FOURNISSEUR NEUTRE')
    checks.append(resolve('non',result['state'])['state']['partners']==base['partners'])
    return {'suite':'typed-correction-heldout-v1','before_errors':before,'after_errors':after,'case_count':len(checks),'regression_count':len(cases),'passed':recipe==RECIPE and all(checks) and after<before,'sage_writes':0,'training_performed':False,'independent_synthetic_cases':True}
