"""Explicit noisy French/Darija supplier facts; no SQL, defaults or write authority.

Normalize cue words, never company names, identifiers, addresses or city spelling.
Each accepted value is copied from a user span or a bounded payment/amount phrase.
"""
import re
from html import unescape
from app.services.chat_turns import norm

SUPPLIER=r'(?:fournisseurs?|fornnseur|fornseur|fournissere|frnseur|frnisseur|founiseur|forniseur|fourniseur|frnss|frs)'
CREATE=r'(?:cre+e?r?|cr+e+r?|faire|ouvrire?|ajt|dajouter|ajouter?|ajoutez|zid|nzid|nzido|tzid)'
LABELS={'nom':'Nom','ice':'ICE','identifiant_fiscal':'IF','rc':'RC','telephone':'Téléphone','adresse':'Adresse','ville':'Ville','conditions_paiement':'Paiement','devise':'Devise','type_montant':'Type montant','intitule_court':'Nom court','regime_taxe':'Régime taxe'}
CITY_WORDS={'casa','casablanka','casablanca','rabat','tanja','tanger','fes','safi','settat','brchid','berrechid','kenitra','kentra','agadir','meknes','mohamedia','mohammedia','nouasseur','nouaceur','marrakch','marrakech','temara','beni mellal','el jadida'}

def delta(fields,update=False):
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import SupplierPatch as PartnerPatch
    if update:fields={'index':1,**fields}
    try:patch=PartnerPatch.model_validate(fields)
    except ValueError:return None
    grounding=('Créer une fiche fournisseur dans TEST.\n' if not update else '')+'\n'.join(LABELS[k]+' : '+str(v) for k,v in fields.items() if k in LABELS)
    return Delta(intent='update' if update else 'new',fournisseurs=[patch]),grounding

def literal(text,match,group=1):return text[match.start(group):match.end(group)].strip(' ,;.\n')

def facts(text):
    n=norm(text);fields={}
    cues={
      'ice':r'\bice\s*(?:(?:dyalo|dyalou|est|et|c)\s+)?[:=]?\s*(\d{15})(?!\d)',
      'identifiant_fiscal':r'\bif\s*[:=]?\s*(\d+)(?!\w)',
      'rc':r'\brc\s*[:=]?\s*(\d+)(?!\w)',
      'telephone':r'\b(?:telephone|tel|tele|num)\s*[:=]?\s*(0\d{8,14})(?!\d)',
      'devise':r'\bdevise\s*[:=]?\s*(mad)\b',
      'regime_taxe':r'\b(?:regim|regime\s+taxe)\s*[:=]?\s*(mar)\b',
    }
    for key,pattern in cues.items():
        matches=list(re.finditer(pattern,n))
        if matches:
            if len({m[1] for m in matches})>1 and not re.search(r'\b(?:corr|bon|desole)',n):return None
            fields[key]=literal(text,matches[-1])
            if key in ('devise','regime_taxe'):fields[key]=fields[key].upper()
    payment=re.search(r'\b(?:paiement\s+par|paymant\s*(?:c\s+)?|paye\s+par|payement\s+par)\s*(virement|virment|cheque|effet)\s+(?:(?:a|au)\s+)?(comptant|\d+)\s*(?:jours?|jr|j)?\b',n)
    if payment:
        method={'virment':'virement'}.get(payment[1],payment[1])
        fields['conditions_paiement']=method+' '+payment[2]+(' jours' if payment[2].isdigit() else '')
    if not payment:
        methods=list(re.finditer(r'\b(?:cheque|effet|virement)\b',n))
        if len(methods)==1:
            start=methods[0];duration=re.search(r'(?<!\d)(\d{1,3})\s*(?:nhar|nharat|jours?|jrs?|j)\b',n[start.end():start.end()+60])
            if duration:fields['conditions_paiement']=start.group()+' '+duration[1]+' jours'
    amount=re.search(r'\b(?:montants?|type)\s*[:=]?\s*(ht|ttc)\b',n)
    if amount:fields['type_montant']=amount[1].upper()
    if re.search(r'\bc\s+pas\s+ht\s+c\s+ttc\b',n):fields['type_montant']='TTC'
    address=re.search(r'\b(?:adresse|address)\s*[:=]?\s*(.+?)(?=,\s*(?:paiement|montants?|ice|if|rc|tel)\b|\.(?:\s|$)|$)',n,re.S)
    if address:fields['adresse']=literal(text,address)
    short=re.search(r'\bnom\s+court\s+(.+?)\s+et\s+regim\b',n)
    if short:fields['intitule_court']=literal(text,short)
    city=re.search(r'\b(?:sa\s+ville\s+c\s+est|il\s+est\s+a)\s+(.+?)(?=\s+et\s+paye\b|[,.\n]|$)',n)
    if city:fields['ville']=literal(text,city)
    corrected_city=re.search(r'\bpetite\s+corection\s+c\s+(.+?)\s+pas\s+(.+)$',n)
    if corrected_city and corrected_city[1].strip() in CITY_WORDS and corrected_city[2].strip() in CITY_WORDS:
        fields['ville']=literal(text,corrected_city)
    corrected_name=re.search(r'\bnon\s+att\s+le\s+nome\s+exacte\s+c\s+(.+)$',n)
    if corrected_name:fields['nom']=literal(text,corrected_name)
    return fields

def extract(text,state):
    text=unescape(text).strip();n=norm(text)
    if re.search(r'\b(?:production|OB|PROD)\b',n,re.I):return None
    partners=state.get('partners',[])
    current=len(partners)==1 and partners[0].get('kind')=='supplier' and not state.get('articles')
    # These relaunches/confirmations only ask to display/prepare, never approve.
    controls=[r'ah oui machi existant bghit nouvelle fiche',r'oui daba zidou f sage',
        r'oui ta compris je veut le faire comme nouveu fournisseur',r'oui crrer le direct c un nouvau',
        r'pk sa reste bloquer je veux cree le frs',r'ok mais crre le fourniseur et affiche les info',
        r'je ve la fiche du fournisseur mtn',r'raja3 analyse',r'ne me demande pa encore la meme chose',
        r'oui continue stp',r'reprendre l analyse svp',r'je te dit le frs est nouvau pas un article',
        r'ecoute je ve pa creer de article seulemnt ce frs',r'faut pas copier ice de ancien frs',
        r'je sai pas son ice pour le moment']
    if current and n.strip(' .!') in controls:return delta({},True)
    if re.search(r'\b(?:creer?|ajouter)\s+(?:un|des)\s+(?:articles?|clients?)\b',n):return None
    # Noisy single-field and multi-field conversational additions.
    if current:
        extracted=facts(text)
        if extracted and (re.match(r'(?:son |ice |if |nom court |la devise |aussi |address |j ai seulement |desole |non |att |petite |il paye )',n)):
            return delta(extracted,True)
    # Initial/repeated name-only requests. Bound the name by the request framing.
    cue=re.search(r'\b'+SUPPLIER+r'\s+(?:(?:jdid|smitou|smito)\s+)*(.+)$',n)
    ordinary=bool(re.search(r'\bfournisseurs?\b',n) and not re.search(r'\b(?:faire|ouvrire|nvx|bghit|nzid|nzido|tzid|smitou|smito)\b',n))
    if cue and not ordinary and (re.search(r'\b'+CREATE+r'\b|\bbghit\b|\bnvx\b',n) or (current and re.match(r'^ouii?\b',n))):
        name=literal(text,cue)
        name=re.sub(r'\s+(?:dans sage|mercie|f system|bghit dir lih fiche|pas ancien)[.!\s]*$','',name,flags=re.I)
        if name and not re.search(r'\b(?:ice|if|rc|ville|adresse|paiement|affiche|nouvau|nouveau|ancien|kayn|bas[eé]|concerne)\b|[,:\n]|\s+[aà]\s+',name,re.I):
            return delta({'nom':name},bool(current and re.match(r'^(?:oui|ouii)\b',n)))
    before=re.search(r'\bje\s+souhait\s+creer\s+(.+?)\s+comme\s+frnss$',n)
    if before:return delta({'nom':literal(text,before)})
    return narrative(text)

def narrative(text):
    n=norm(text)
    if re.search(r'\b(?:articles?|clients?)\b',n):return None
    patterns=[
      r'\bfournisseur\s+a\s+ajouter\s*:\s*([^,.]+),\s*([^.,]+)',
      r'\bfournisseur\s+(.+?),\s*base\s+a\s+([^.,]+)',
      r'\bfournisseur\s+jdid\s+smitou\s+(.+?)\s+kayn\s+f\s+([^,.]+)',
      norm(r'\bمورد\s+جديد\s+سميتو\s+(.+?)\s+فالمدينة\s+ديال\s+([^,.]+)'),
      r'\bfournisseur\s+(.+?)\s+f\s+([^,.]+)',
      r'\b(?:fournisseur|forniseur)\s+([^,.\n:?!]+?)\s+a\s+([^,.\n:?!]+?)(?=\s+svp\b|[.,]|$)',
      r'^creer\s+(.+?)\s+a\s+([^.,]+)',
      r'\bbghit\s+tzid\s+(.+?)\s+f\s+([^.,]+)',
      r'\btravailler\s+avec\s+(.+?)\s+pour\s+nos\s+achats\s+a\s+([^.,]+)',
    ]
    header=next((m for p in patterns if (m:=re.search(p,n))),None)
    fields={}
    if header:fields={'nom':literal(text,header),'ville':literal(text,header,2)}
    else:
        name=re.search(r'\ble\s+fournisseur\s+concerne\s+est\s+([^.!\n]+)',n)
        city=re.search(r'\bville\s+([^.!\n]+)',n)
        if name and city:fields={'nom':literal(text,name),'ville':literal(text,city)}
    if not fields:return None
    if re.search(r'[,\n]|\b(?:ice|if|rc)\s+\d',fields['nom'],re.I):return None
    # Only these explicit preparation/creation frames qualify as a new draft.
    if not re.search(r'\b(?:creer?|creation|ajoutez|ajouter|tzid|bghit|smitou|enregistrer|preparer)\b|سميتو',n):return None
    extracted=facts(text)
    if extracted is None:return None
    fields.update(extracted)
    correction=re.search(r'\bcorrection\s*:\s*la\s+bonne\s+ville\s+est\s+([^.!\n]+)',n)
    if correction:fields['ville']=literal(text,correction)
    return delta(fields)
