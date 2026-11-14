"""Multilingual explicit supplier requests. Pure parsing, no I/O or write authority.

Recognizes a request's name introduction, then independently scans field aliases.
Unknown values are omitted; defaults and current Sage references belong to preparation.
"""
import re
from html import unescape
from app.services.chat_turns import norm

INTRODUCTIONS=[
    r'\b(?:ajoute|ajouter)\s+un\s+(?:frs|fournisseur)\s+',
    r'\bfournisseur\s+(?:jdid\s+)?smitou\s+',
    r'\bfournisseur\s+جديد\s+سميتو\s+',
    r'\bfiche\s+dyal\s+',
    r'\bbghit\s+nzed\s+',
    r'\bfrs\s+jdid\s*->\s*',
    r'\breference\s+fournisseur\s+a\s+etablir\s*:\s*',
    r'\bbesoin\s+de\s+referencer\s+',
    r'\bpreparer\s+la\s+creation\s+de\s+',
    r'\bsaisir\s+notre\s+prestataire\s+',
    r'\b(?:enregistrer|enregistre|referencement\s+du|enregistrer\s+notre\s+nouveau)\s+fournisseur\s+',
    r'\benregistrer\s+notre\s+nouveau\s+fournisseur\s+',
    r'\benregistrer\s+le\s+fournisseur\s+',
    r'\bfiche\s+fournisseur\s+au\s+nom\s+de\s+',
    r'\b(?:creer|creation\s+du)\s+(?:uniquement\s+la\s+fiche\s+)?fournisseur\s+',
    r'\bcreer\s+le\s+(?:compte\s+)?fournisseur\s+(?:de\s+)?',
    r'\bfiche\s+tiers\s+fournisseur\s+pour\s+',
    r'\b(?:nouvelle\s+)?fiche\s+pour\s+',
    r'\bcoordonnees\s+de\s+',
    r'\b(?:demande\s+l[’\']ajout\s+de|veuillez\s+ajouter|pouvez-vous\s+ajouter)\s+',
    r'\breferencer\s+la\s+societe\s+',
    r'\ben\s+tant\s+que\s+fournisseur\s*:\s*',
]
ALIASES={
    'identifiant ice':'ice','ice dyalou':'ice','ice':'ice',
    'identifiant fiscal':'identifiant_fiscal','if':'identifiant_fiscal',
    'registre commerce':'rc','registre de commerce':'rc','rc':'rc',
    'date regularite fiscale':'date_regularite','date de regularite fiscale':'date_regularite',
    'type montant':'type_montant','montant':'type_montant',
    'conditions de paiement':'conditions_paiement','condition de paiement':'conditions_paiement',
    'paiement':'conditions_paiement','reglement':'conditions_paiement','khalass':'conditions_paiement',
    'telephone':'telephone','tel':'telephone','numero':'telephone','fax':'fax',
    'ville':'ville','localite':'ville','mdina':'ville',
    'l’adresse':'adresse',"l'adresse":'adresse','adresse':'adresse','fin kayn':'adresse',
    'devise':'devise','nom':'nom',
}
CANONICAL={'nom':'Nom','ice':'ICE','identifiant_fiscal':'IF','rc':'RC','date_regularite':'Date de régularité fiscale','type_montant':'Type montant','conditions_paiement':'Paiement','telephone':'Téléphone','fax':'Fax','ville':'Ville','adresse':'Adresse','devise':'Devise'}
TAILS=[
    r'w\s+3tini\s+les\s+infos\s+bach\s+nconfirmi',r'bla\s+matcreyi\s+daba',
    r'وريني\s+المعلومات\s+قبل\s+التأكيد',r'ما\s+تدير\s+حتى\s+إنشاء\s+بلا\s+confirmation',
    r'merci\s+de\s+presenter\s+la\s+fiche\s+avant\s+validation',
    r'je\s+confirme\s+apres\s+verification',r'afficher\s+les\s+parametres\s+standard',
    r'prepare\s+seulement\s+la\s+fiche',r'ne\s+pas\s+lancer\s+la\s+creation\s+avant\s+accord',
    r'ne\s+cree\s+ni\s+article',r'le\s+devis\s+concerne',r'si\s+un\s+champ\s+manque',r'\bmerci\b',
    r'confirmer\s+avant\s+creation',r'affiche\s+la\s+fiche',r'ila\s+chi\s+info\s+na9sa',
    r'ne\s+reutilise\s+pas\s+les\s+noms',r'garde\s+la\s+correction\s+finale',
    r'إلا\s+نقصات\s+شي\s+معلومة',r'ne\s+renseigne\s+aucun',r'n[’\']invente\s+ni',
    r'3afak\s+verifie',r'bien\s+a\s+vous',r'cordialement',r'prepare\s+vite\s+la\s+fiche',
    r'utilise\s+la\s+decision\s+finale',r'svp\s+pas\s+des\s+factur',
    r'ne\s+creez\s+pas\s+de\s+commande',r'n[’\']enregistrez\s+aucune',
    r'je\s+n[’\']ai\s+pas\s+encore\s+recu',r'bien\s+cordialement',
    r'je\s+transmettrai\s+les\s+documents',r'je\s+verifierai\s+les\s+informations',
    r'la\s+creation\s+doit\s+etre\s+soumise',
]
LABEL=re.compile(r'(?<!\w)('+ '|'.join(re.escape(a) for a in sorted(ALIASES,key=len,reverse=True) if a!='nom')+r'|nom(?=\s*:))(?!\w)\s*:?\s*',re.I)

def extract_followup(message):
    """Explicit additions/corrections to the single current supplier, never a SAVE."""
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import SupplierPatch as PartnerPatch
    from app.services.chat_partners import ALIASES as existing_aliases
    aliases={**existing_aliases,'adress':'adresse','adr':'adresse','tele':'telephone','tel':'telephone'}
    text=unescape(message).strip()
    if '?' in text:return None
    prefix=r"(?:(?:avec|avce|pour)\s+)?(?:(?:ajoute|ajouter|rajoute|renseigne|corrige|modifie|remplace|complete)\s+)?(?:l['’]\s*|(?:le|la|son|sa)\s+)?"
    pattern=r'(?:^|\s+et\s+|[,;\n]\s*)'+prefix+'('+ '|'.join(map(re.escape,sorted(aliases,key=len,reverse=True)))+r')(?!\w)\s*(?::|=|\bdois\b|\bdoit\b|\best\b|\bpar\b)?\s+'
    matches=list(re.finditer(pattern,norm(text)))
    if not matches or matches[0].start()!=0:return None
    fields={};grounding=[]
    for i,match in enumerate(matches):
        key=aliases[match[1]]
        value=text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip(' \r\n,;.')
        raw=value
        if not value:return None
        if key=='type_montant':value=value.upper()
        if key=='date_regularite':
            from app.services.supplier_dates import normalize_date
            try:value=normalize_date(value)
            except ValueError:return None
        if key in fields and fields[key]!=value:return None
        fields[key]=value
        canonical=next((label for label,field in existing_aliases.items() if field==key),None)
        if not canonical:return None
        grounding.append(canonical+' : '+(raw if key=='date_regularite' else str(value)))
    try:patch=PartnerPatch.model_validate({'index':1,**fields})
    except ValueError:return None
    return Delta(intent='update',fournisseurs=[patch]),'\n'.join(grounding)

def extract_request(message):
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import SupplierPatch as PartnerPatch
    from app.services.supplier_dates import normalize_date
    text=unescape(message)
    text=re.sub(r'\bR[eè]glement\s+par\s+', 'Paiement : ',text,flags=re.I)
    text=re.sub(r'\bFacturation\s+en\s+(HT|TTC)\b',lambda m:'Type montant : '+m[1],text,flags=re.I)
    n=norm(text)
    intro=next((m for pattern in INTRODUCTIONS if (m:=re.search(pattern,n))),None)
    labelled_name=bool(re.search(r'\bnom\s*:',n))
    explicit_correction=re.search(r'\b(?:le\s+bon\s+nom\s+est|le\s+nom\s+correct\s+est)\s+([^.!\n]+)',n)
    contextual=bool(re.search(r'\b(?:fournisseur|fornisseur|frs|fiche|tiers|مورد)\b',n))
    if not intro and not ((labelled_name or explicit_correction) and contextual):return None
    if re.search(r'\b(?:recherche|cherche|consulte)\b',n) and not re.search(r'\b(?:cree|creer|creation|nouveau|prepare|preparer)\b',n):return None
    if re.search(r'\bclients?\b',n):return None
    # Leave mixed article/client operations to the existing semantic controller.
    if re.search(r'\b(?:creer?|ajouter|ajoute)\s+(?:un|des|deux)\s+(?:articles?|clients?)\b',n):return None
    if re.search(r'\b(?:OB|PROD|production)\b',text,re.I):return None
    # Fields outside this parser must go through the complete existing path.
    if re.search(r'\b(?:code\s+comptable|categorie|regime\s+(?:taxe|fiscal)|pays|email|nom\s+court|site)\b|\bsociete\s*[:=]',n):return None
    if re.search(r'\bdossier\s*[:=]\s*(?!TEST\b)\w+',n,re.I):return None
    if labelled_name:intro=None  # An explicit field wins over a generic introduction.
    fields={};grounding=['Créer une fiche fournisseur dans TEST.']
    stop=-1
    if intro:
        end=re.search(r'\.(?=\s|$)|[؟?\n]|\s+f\s+liste\s+fournisseurs|\s+dans\s+Sage\s+(?:TEST|X3)|,\s*(?:sans\s+commande|sous\s+reserve|sous\s+réserve|fournisseur\s+de)|\s+(?:pour\s+son\s+enregistrement|comme\s+fournisseur|[aà]\s+la\s+liste\s+de\s+nos\s+fournisseurs)',text[intro.end():],re.I)
        if not end:return None
        stop=intro.end()+end.start();name=text[intro.end():stop].strip(' ,;:')
        if not name or len(name)>100:return None
        if re.search(r'[,;]\s*(?:identifiant\s+)?(?:ICE|IF|RC)\b',name,re.I):return None
        if re.search(r'\b(?:ICE|IF|RC)\s*[:=]?\s*\d',name,re.I):return None
        fields['nom']=name;grounding.append('Nom : '+name)
    final_name=re.search(r'\bfinalement\s+le\s+nom\s+correct\s+est\s+([^.!\n]+)',n)
    if final_name:
        fields['nom']=text[final_name.start(1):final_name.end(1)].strip()
        grounding=['Créer une fiche fournisseur dans TEST.','Nom : '+fields['nom']]
    body=text[stop+1:];body_n=norm(body)
    if not intro:
        first=next((m for m in LABEL.finditer(body_n) if ':' in m[0]),None)
        if not first:return None
        body=body[first.start():];body_n=norm(body)
    # Remove commentary while retaining any explicitly labelled data after it.
    while True:
        endings=[m for pattern in TAILS if (m:=re.search(norm(pattern),norm(body),re.I))]
        if not endings:break
        ending=min(endings,key=lambda m:m.start())
        following=next((m for m in LABEL.finditer(norm(body),ending.end()) if ':' in m[0]),None)
        body=body[:ending.start()]+('\n'+body[following.start():] if following else '')
    matches=list(LABEL.finditer(norm(body)))
    for i,match in enumerate(matches):
        key=ALIASES[match[1].lower()]
        raw=body[match.end():matches[i+1].start() if i+1<len(matches) else len(body)].strip(' \r\n,;/.-')
        raw=re.split(r'\.(?=\s|$)|\s*/\s*TEST\s*(?:/|$)',raw,maxsplit=1,flags=re.I)[0].rstrip(' ,;/.')
        if not raw:continue
        value=raw
        if key in ('ice','identifiant_fiscal','rc','telephone','fax'):
            found=re.fullmatch(r'[0-9]+',raw)
            if not found:return None
            value=found[0]
        elif key=='date_regularite':
            found=re.fullmatch(r'\d{2}[/.-]\d{2}[/.-]\d{4}|\d{4}-\d{2}-\d{2}',raw)
            if not found:return None
            try:value=normalize_date(found[0])
            except ValueError:return None
            raw=found[0]
        elif key=='type_montant':
            found=re.fullmatch(r'(HT|TTC)',raw,re.I)
            if not found:return None
            value=found[0].upper()
        elif key=='devise':
            found=re.fullmatch(r'[A-Za-z]{3}',raw)
            if not found:return None
            value=raw.upper()
        if key in fields and fields[key]!=value:return None  # No silent conflicting values.
        fields[key]=value
        grounding.append(CANONICAL[key]+' : '+(raw if key=='date_regularite' else value))
    correction=re.search(r'\bcorrection\s+finale\s*:\s*([A-Z0-9]+)',text,re.I)
    if correction:
        fields['conditions_paiement']=correction[1]
        grounding.append('Paiement : '+correction[1])
    final_payment=re.search(r'\bdecision\s+finale\s+est\s+([^.!\n]+)',n)
    if final_payment:
        fields['conditions_paiement']=text[final_payment.start(1):final_payment.end(1)].strip()
        grounding.append('Paiement : '+fields['conditions_paiement'])
    if explicit_correction:
        fields['nom']=text[explicit_correction.start(1):explicit_correction.end(1)].strip()
        grounding.append('Nom : '+fields['nom'])
    if not fields.get('nom'):return None
    try:patch=PartnerPatch.model_validate(fields)
    except ValueError:return None
    return Delta(intent='new',fournisseurs=[patch]),'\n'.join(grounding)
