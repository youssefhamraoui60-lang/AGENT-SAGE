"""Grounded supplier conversation facts, independent of inference and SQL availability."""
import copy,re
from uuid import uuid4
from app.services.chat_turns import norm,SUPPLIER_WORD

TERMINAL={'executing','succeeded','ambiguous','unverified','failed'}
CREATE=r'(?:ncreer?|creer?|ceer|crrer|crer|crreer|ajouter?|prepare[r]?|zid|nzid|n7el|nhel|ndir)'
NEW=r'(?:nouveau|nouvel|nouvelle|nevelle|neveau|nevue|jdid)'

def explicit_supplier_creation(text):
    n=norm(text)
    # Adding a supplier relationship to an existing article remains an UPDATE.
    if re.search(r'\b(?:a|au|pour|sur|de|du)\s+(?:l[\x27’]\s*)?article\b',n):return False
    return creation_declared(text) and bool(re.search(r'\b'+CREATE+r'\s+(?:(?:un|une|le|la|ce|nouveau|nouvel|nouvelle|nevelle|lina|lia|liya|wahed|wahad)\s+)*(?:(?:fiche|dossier)\s+)?'+SUPPLIER_WORD+r'\b',n) or re.search(r'(?:مورد|فورنيسور).*?جديد',n))

def creation_declared(text):
    n=norm(text)
    if re.search(r'\b'+CREATE+r'\s+(?:(?:un|une|le|la|nouveau|nouvel)\s+)*articles?\b',n):return False
    if re.search(r'(?:بغيت|اريد|أريد).*?(?:نزيد|اضافة|إضافة).*?(?:مورد|فورنيسور).*?جديد',n):return True
    positive=re.search(r'\b'+CREATE+r'\b',n) and re.search(r'\b'+SUPPLIER_WORD+r's?\b',n)
    negative=re.search(r'\b(?:annule|existant|recherche|cherche)\b',n) or re.search(r'\bne\s+(?:(?:(?:veux|souhaite)\s+)?pas\s+(?:encore\s+)?'+CREATE+r'|'+CREATE+r'\s+pas)\b',n)
    return bool(positive and not negative)

def turn(text,state,history=()):
    if state.get('articles') or any(p.get('kind')!='supplier' for p in state.get('partners',[])):return None
    if re.search(r'\b'+CREATE+r'\s+(?:(?:un|une|le|la|nouveau|nouvel)\s+)*articles?\b',norm(text)):return None
    original=re.sub(r'[*`]+','',text).replace('\u2019',"'")
    n=norm(original);supplier=bool(re.search(r'\b'+SUPPLIER_WORD+r's?\b',n))
    create=creation_declared(text)
    clarification=supplier and bool(re.search(r'\b'+NEW+r'\b',n)) and not re.search(r'\b(?:recherche|cherche|existant)\b',n)
    rows=state.get('partners',[])
    if len(rows)>1:return None
    if state.get('workflow')=='cancelled' and not (create or clarification):return None
    active=bool(rows) or (state.get('_supplier_dialogue') or {}).get('intent')=='create_supplier'
    if not (active or create or clarification):
        replay={'articles':[],'partners':[]}
        for row in history:
            if row.get('role')!='user':continue
            previous=row.get('content','')
            if re.search(r'\bannule\b',norm(previous)):replay={'articles':[],'partners':[]};continue
            recovered=turn(previous,replay)
            if recovered:replay=recovered['state']
        if replay.get('partners') and replay.get('_supplier_dialogue',{}).get('intent_confirmed'):
            restored=copy.deepcopy(state);restored['partners']=replay['partners'];restored['_supplier_dialogue']=replay['_supplier_dialogue']
            restored['_supplier_dialogue']['recovered_from_user_history']=True
            return turn(text,restored)
        return None
    # Preserve original spans even for Unicode ligatures/combining accents.
    chars=[];starts=[];ends=[]
    for i,char in enumerate(original):
        for c in norm(char):chars.append(c);starts.append(i);ends.append(i+1)
    literal=''.join(chars)
    def value(pattern):
        m=re.search(pattern,literal)
        return original[starts[m.start(1)]:ends[m.end(1)-1]].strip(' .!,:;') if m and m.start(1)<m.end(1) else None
    stop=r"(?=\s+(?:c'est\s+(?:une?|la)|forme\s+juridique|(?:leur\s+)?ville\s+(?:est|:)|mais\s+|(?:je|j')\s*(?:n'ai|ai|ne\s+connais|connais)|et\s+(?:il|elle)|kayn\s+f|walakin|khdem|(?:son|mon|le)\s+(?:ice|if|rc)|(?:ice|if|rc)\s*[:=])\b|[,;\n]|$)"
    name=value(r"\b(?:il|elle|le fournisseur)?\s*(?:s'appelle|se nomme)\s+(.+?)"+stop)
    if not name:name=value(r'\b(?:smito|smiya\s+(?:correcte\s+hiya|s7i7a(?:\s+hiya)?))\s+(.+?)'+stop)
    if not name and (create or clarification):
        name=value(r'\b'+SUPPLIER_WORD+r'\s+(?:jdid|b\s+ism)\s+(.+?)(?=\s+(?:w\s+|f\s+|kayn\s+|walakin\s+)|[,;\n.]|$)')
        if name:
            from app.services.conversation_guardrails import invalid_supplier_name
            if invalid_supplier_name(name):name=None
    named=value(r'\b'+SUPPLIER_WORD+r'\s+(?:nomme|appele)\s+(.+?)'+stop) if create else None
    if named:name=named
    if not name:name=value(r"\b(?:son\s+nom|le\s+nom(?:\s+(?:du|de)\s+fournisseur)?|nom)\s*(?:est\s*[:=]?|c'est\s*[:=]?|[:=])\s*(.+?)"+stop)
    city=value(r"\b(?:(?:il|elle)\s+est(?:\s+(?:situe|base))?\s+a|ville\s*(?:[:=]|est)|mdina\s*[:=]?|kayn\s+f)\s+([^,;.\n]+)")
    if city:city=re.split(r'\s+(?:(?:le|son)\s+)?ice\b',city,1,flags=re.I)[0].strip()
    if create and city and not name:
        plain=value(r'\b'+SUPPLIER_WORD+r'\s+(.+?)'+stop)
        if plain and not re.match(r'(?:suivant|dans|nouveau|jdid)\b',norm(plain)):name=plain
    legal=value(r'\b(?:forme\s+juridique\s*[:=]?|(?:c.est|il\s+est)\s+(?:une?\s+)?)\s*((?:sarl\s+au|sarlau|sarl|sas|sa|snc|eurl))\b')
    if legal and not city:
        city=value(r'\b(?:sarl\s+au|sarl|sas|sa|snc|eurl)\s+a\s+(.+?)'+stop)
    if city:city=re.split(r"\s+(?:mais|et\s+je|j'ai|je\s+ne|je\s+connais)\b",city,1,flags=re.I)[0].strip()
    if create and re.search(r'(?:مورد|فورنيسور).*?جديد',original):
        arabic=re.search(r'سميتو\s+(.+?)(?:\s+ف(?:الرباط|كازا|الدار البيضاء)|\s+وما\s|$)',original)
        if arabic:name=arabic[1].strip()
        if 'فالرباط' in original:city='Rabat'
    fields={k:v for k,v in [('nom',name),('ville',city),('forme_juridique',legal.upper() if legal else None)] if v}
    if create and name:
        ice=value(r'\bice\s*(?:est|[:=])?\s*(\d{1,30})(?!\d)')
        if ice:fields['ice']=ice
    if named:
        labelled_city=value(r'(?:^|[,;\n])\s*ville\s*[:=]?\s+([^,;\n]+)')
        ice=value(r'\bice\s*[:=]?\s*(\d{1,30})(?!\d)')
        if labelled_city:fields['ville']=labelled_city
        if ice:fields['ice']=ice
    # Rich forms retain their existing field parser: this narrow controller must
    # not consume a name/city while dropping an ICE, phone or payment alongside it.
    rich=bool(re.search(r'\b(?:ice|if|rc|telephone|tel|email|paiement|adresse)\s*[:=]?\s*[0-9@]|\b(?:paiement|adresse)\s*[:=]',n))
    named_form=named and not re.search(r'\b(?:if|rc|telephone|tel|email|paiement|adresse)\b',n)
    if rich and not named_form:return None
    unknown=[]
    for cue,key in [('ice','ice'),('if','identifiant_fiscal'),('rc','rc'),('telephone','telephone'),('email','email')]:
        if re.search(r"\b(?:je\s+(?:ne\s+)?(?:connais|sais)(?:\s+pas)|je\s+n'ai\s+pas|j'ai\s+pas|pas\s+encore|inconnu|non\s+renseigne).{0,65}\b"+cue+r'\b',n):unknown.append(key)
    if not fields and not unknown:
        if not (create or clarification):return None
        # A real new request for a named supplier is handled by the existing parser.
        tail=re.search(r'\b'+SUPPLIER_WORD+r's?\b\s*(.*)',n)
        tail_text=tail[1].strip(' .!?') if tail else ''
        bare_darija=bool(re.match(r'^jdid\s*[,;].*\b(?:ma3reftch|chno|kifach)\b',tail_text))
        if tail_text and not bare_darija and not re.fullmatch(r'(?:jdid|nouveau|nouvelle|nevelle|fiche|fournisseur|\s)+',tail_text):return None
        if rows and rows[0].get('nom'):
            return {'state':copy.deepcopy(state),'reply':'La fiche '+rows[0]['nom']+' et ses informations sont conservées. Vous pouvez la compléter sans tout répéter.'}
    if rows and (rows[0].get('operation') or {}).get('status') in TERMINAL:return None
    changed=copy.deepcopy(state)
    if create and rows and rows[0].get('nom') and name and norm(name)!=norm(rows[0]['nom']):
        changed.setdefault('supplier_archives',[]).append({'partners':copy.deepcopy(rows),'reason':'explicit_new_request'})
        changed['partners']=[]
    if not changed.get('partners'):
        changed['partners']=[{'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False}]
    p=changed['partners'][0]
    from app.services.supplier_dialogue import assign,QUESTIONS
    correction=bool(re.search(r'\b(?:non|corrige|corriger|correction|trompe|rectifie|remplace)\b',n))
    for field,val in fields.items():
        old=p.get(field)
        if old and norm(str(old))!=norm(val) and p.get('field_states',{}).get(field,{}).get('status')=='confirmed' and not correction:
            changed['pending_correction']={'target_id':p['id'],'kind':'supplier','field':field,'label':field,'value':val,'before':old,'fuzzy':False}
            return {'state':changed,'reply':'Cette information diffère de la valeur déjà confirmée. Souhaitez-vous remplacer '+str(old)+' par '+val+' ? Répondez « oui, corrige ce champ » ou précisez la correction.'}
        try:error=assign(changed,field,val)
        except ValueError:
            changed.setdefault('_supplier_dialogue',{})['unapplied_value']={'field':field,'value':val}
            return {'state':changed,'reply':'Cette valeur doit être vérifiée. Les autres informations sont conservées.'}
        if error:return {'state':changed,'reply':error}
        if correction and old not in (None,'') and norm(str(old))!=norm(val):
            changed['_supplier_dialogue']['explicit_correction']={'field':field,'value':val,'before':old}
    focus=changed.setdefault('_supplier_dialogue',{});focus['intent']='create_supplier';focus['intent_confirmed']=True
    for field in unknown:
        if not p.get(field):
            p.setdefault('field_states',{})[field]={'value':None,'status':'unknown','source':'user_declared_missing'}
            p.setdefault('unknown_fields',[])
            if field not in p['unknown_fields']:p['unknown_fields'].append(field)
    if not p.get('nom'):
        focus['expected_field']='nom'
        return {'state':changed,'reply':QUESTIONS['nom'] if not state.get('_supplier_dialogue',{}).get('expected_field') else 'La nouvelle fiche est conservée. Vous pouvez indiquer son nom.'}
    focus.pop('expected_field',None)
    return {'state':changed,'prepare':True,'unknown_fields':unknown}
