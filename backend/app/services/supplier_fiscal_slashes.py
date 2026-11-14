"""Bounded fiscal values and a separate literal address in slash-delimited forms."""
import re
from app.services.chat_turns import norm,SUPPLIER_WORD

def extract(text,state,history=()):
    n=norm(text)
    if '/' not in n or state.get('articles') or re.search(r'\b(?:articles?|clients?)\b',n):return None
    if '//' in text:
        labelled=double_slash_form(text)
        if labelled:return labelled
    if re.search(r'\b(?:adresse|ville|paiement|telephone|pays|devise|categorie)\s*[:=]',n):return None
    header=re.search(r'\b(?:creer?|ajouter?|prepare)\s+(?:(?:ce|un|le|nouveau|nouvel)\s+)*'+SUPPLIER_WORD+r'\b\s*(?:suivant\b\s*)?[:=]?\s*(.+?)(?=\s*/+\s*(?:ice|if|rc)\b|\s+(?:ice|if|rc)\b)',n,re.S)
    matches=list(re.finditer(r'\b(ice|if|rc)\s*[:=/]?\s*([0-9]{1,30})(?!\w)',n))
    if not matches:return None
    current=state.get('partners',[])
    contextual=bool(len(current)==1 and current[0].get('kind')=='supplier' or any(h.get('role')=='user' and re.search(r'\b'+SUPPLIER_WORD+r'\b',norm(h.get('content',''))) and re.search(r'\b(?:creer?|ajouter?|prepare)\b',norm(h.get('content',''))) for h in history[-8:]))
    if header:name=text[header.start(1):header.end(1)].strip(' .\n')
    elif contextual:
        name=text[:matches[0].start()].strip(' ./\n')
        if not name or len(name)>100 or re.search(r'\b(?:recherche|cherche|consulte|verifie|ice|if|rc)\b|[:=?]',norm(name)):return None
    else:return None
    fields={'nom':name}
    for match in matches:
        field={'ice':'ice','if':'identifiant_fiscal','rc':'rc'}[match[1]]
        value=text[match.start(2):match.end(2)]
        if field in fields and fields[field]!=value:return None
        fields[field]=value
    tail=text[matches[-1].end():].strip(' ./\n')
    tail=re.sub(r'\s+(?:merci|cordialement|cdlt)[.!\s]*$','',tail,flags=re.I).strip()
    if tail:
        if re.search(r'\b(?:ice|if|rc)\b|[:=]',norm(tail)):return None
        street=re.search(r'\b(?:rue|bd|boulevard|avenue|route|zone|bloc|lot|residence|immeuble)\b',norm(tail))
        postal=re.search(r'\b[0-9]{5}\s*[-–]\s*[a-z][a-z -]+$',norm(tail))
        if not street and not postal:return None
        fields['adresse']=tail
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import SupplierPatch
    update=not header and len(current)==1 and current[0].get('kind')=='supplier'
    try:patch=SupplierPatch.model_validate({'index':1,**fields} if update else fields)
    except ValueError:return None
    labels={'nom':'Nom','ice':'ICE','identifiant_fiscal':'IF','rc':'RC','adresse':'Adresse'}
    grounding='Créer un fournisseur dans TEST.\n'+'\n'.join(labels[k]+' : '+v for k,v in fields.items())
    return Delta(intent='update' if update else 'new',fournisseurs=[patch]),grounding

def double_slash_form(text):
    """Split field boundaries, never slashes inside dates or literal addresses."""
    parts=[p.strip() for p in re.split(r'/{2,}',text) if p.strip()]
    if not parts:return None
    header=re.search(r'\b(?:creer?|ajouter?|prepare)\s+(?:(?:ce|un|le|nouveau|nouvel)\s+)*'+SUPPLIER_WORD+r'\b\s*(?:suivant\b\s*)?[:=]?\s*(.+)$',norm(parts[0]),re.S)
    if not header:return None
    fields={'nom':parts[0][header.start(1):header.end(1)].strip(' :\n')}
    from app.services.chat_partners import ALIASES
    labels={**ALIASES,'email':'email','e-mail':'email','adresse mail':'email'}
    for part in parts[1:]:
        if re.fullmatch(r'(?:merci|cordialement|cdlt)[.!\s]*',norm(part)):continue
        match=re.fullmatch(r'([^:=]+)\s*[:=]\s*(.+)',part,re.S)
        if not match:return None
        field=labels.get(norm(match[1]).strip())
        if not field:return None
        value=match[2].strip()
        if field in ('ice','identifiant_fiscal','rc'):
            value=re.sub(r'^(?:n\s*[°ºo]|num[eé]ro)\s*','',value,flags=re.I).rstrip(' .')
            if not re.fullmatch(r'[0-9]{1,30}',value):return None
        if field in fields and fields[field]!=value:return None
        fields[field]=value
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import SupplierPatch
    try:patch=SupplierPatch.model_validate(fields)
    except ValueError:return None
    canonical={field:label for label,field in labels.items()}
    canonical['nom']='Nom';canonical['identifiant_fiscal']='IF';canonical['ice']='ICE'
    grounding='Créer un fournisseur dans TEST.\n'+'\n'.join(canonical.get(k,k)+' : '+v for k,v in fields.items())
    return Delta(intent='new',fournisseurs=[patch]),grounding
