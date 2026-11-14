"""Literal article facts, declared site selections and non-writing chat actions."""
import re
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field
from app.services.chat_turns import norm


class SiteSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sites:list[Annotated[str,Field(pattern=r'^[A-Z0-9_-]{1,5}$')]]=Field(min_length=1,max_length=20)


def presentation(text):
    n=norm(text)
    if not re.search(r'\b(?:affiche|afficher|presente|presentation|montre|format)\b',n):return None
    if re.search(r'\b(?:tableau|table|tabe)\b',n) and not re.search(r'\bpas\s+(?:de\s+|en\s+)?(?:tableau|table|tabe)\b',n):return 'table'
    if re.search(r'\b(?:cartes?|cards?|cardes?)\b',n) and not re.search(r'\bpas\b.*\b(?:cartes?|cards?|cardes?)\b',n):return 'cards'
    return None


def creation_request(text,state):
    if not state.get('articles') and not state.get('partners'):return False
    n=norm(text).strip(' .!')
    if presentation(text):return False
    if re.fullmatch(r'(?:valide(?:r)?\s+et\s+cr[e2]er|lance(?:r)?\s+la\s+creation|enregistre(?:r)?\s+(?:cet|les|l[\x27’])\s*articles?)(?:\s+dans\s+(?:sage|test))?',n):return True
    if re.fullmatch(r'(?:creer?|crrer|crer|crreer)\s+(?:le|les)',n):return True
    found=re.search(r'\b(?:creer?|cr2er|crrer|crer|crreer)\s+(?:(?:le|les|ces|cet|cette)\s+|l[\x27’]\s*)(?:articles?|fournisseurs?)\b',n)
    if not found:return False
    tail=n[found.end():].strip()
    return not tail or bool(re.fullmatch(r'(?:directement|derctomnet|apres|aprer|mon|ma|confirmation|forfirmation|confirme|ok|oui|\s)+',tail))


def declared_sites(text):
    n=norm(text)
    match=re.search(r'\bsites?\s*(?:(?:dois|doit|sont|est|dans|pour|sur|:|=)\s*)*((?:\d{3})(?:\s*(?:et|,|/|ainsi que)\s*\d{3})*)\b',n)
    if not match:return None
    return SiteSelection(sites=list(dict.fromkeys(re.findall(r'\d{3}',match[1])))).sites


def literal_extract(text,state):
    from app.services.chat_model import Delta
    if state.get('articles') and (presentation(text) or creation_request(text,state)):
        return Delta(intent='approve' if creation_request(text,state) else 'lookup')
    n=norm(text)
    if not state.get('articles') and '?' not in n:
        partial=simple_initial(text)
        if partial:return partial
    if state.get('articles') or '?' in text or re.search(r'\b(?:prix|remise|incoterm|adresse)\b',n):return None
    match=re.match(r'\s*(?:creer?|crrer|crer|crreer)\s+(?:un|une)\s+articles?\s+(?:de\s+)?(.+?)(?=\s+(?:le\s+)?unit(?:e|er|ee)\b|[,;\n]|$)',n)
    if not match:return None
    label=text[match.start(1):match.end(1)].strip()
    unit=re.search(r'\bunit(?:e|er|ee)\b\s*(?:est\s+)?[:=]?\s*([a-z0-9]{1,3})\b',n)
    sites=declared_sites(text)
    tax=re.search(r'\btva\s*[:=]?\s*(\d{1,2}(?:[.,]\d+)?)\s*%',n)
    from app.services.chat_semantics import supplier_decision
    if not unit or not sites or not tax or supplier_decision(text)!='none' or len(label)>70:return None
    shared={'unite':unit[1].upper(),'site':sites[0],'taux_tva':tax[1].replace(',','.')}
    if re.search(r'\bnon\s+(?:gere(?:r|e|s)?|greer|grer)\b',n):shared['gestion_stock']='1'
    category=re.search(r'\b(?:categorie|cat)\s*[:=]?\s*([a-z0-9_-]{1,5})\b',n)
    if category:shared['categorie']=category[1].upper()
    return Delta(intent='new',articles=[{'designation':label}],shared=shared)


def simple_initial(text):
    """Literal single-article facts; missing units stay missing, not L/UN."""
    from app.services.chat_model import Delta
    from app.services.chat_slash_extract import parse_labelled
    slash=parse_labelled(text)
    if slash:
        label=slash.pop('designation')
        return Delta(intent='new',articles=[{'designation':label}],shared=slash)
    labelled=labelled_initial(text)
    if labelled:return labelled
    text=re.sub(r'\s+(?:dans|dasn)\s+le\s+syst[eèé]me(?:\s+(?:avec|avce)\s+la)?\s*',', ',text,flags=re.I)
    text=re.sub(r'\s+et\s+(?:le|la)\s+(?=tva\b|cat(?:egorie|igorier)\b|site\b)',', ',text,flags=re.I)
    n=norm(text)
    match=re.search(r'\b(?:creer?|cr2er)\s+(?:(?:un|une)\s+(?:nouvel(?:le)?\s+)?|l[\x27’]\s*)articles?\s+(.+?)(?=,|;|\n|$)',n)
    if not match:return None
    label=text[match.start(1):match.end(1)].strip().rstrip('.')
    label=re.sub(r'\s+(?:dans|dasn)\s+le\s+syst[eèé]me\s*$', '',label,flags=re.I)
    if not 0<len(label)<=70 or re.search(r'\b(?:fournisseur|unite|uniter|catigorier|categorie|tva|site|et)\b',norm(label)):return None
    tail=text[match.end():].strip(' ,;\n.')
    shared={}
    for part in re.split(r'[,;\n]+',tail) if tail else []:
        if re.fullmatch(r'\s*non\s+gere\s+en\s+stock\s*',norm(part)):
            shared['gestion_stock']='1';continue
        m=re.fullmatch(r'\s*(categorie|catigorier|catigorier|cat|tva|unite|u|site)\s*[:=]?\s*([a-z0-9_.%-]+)\s*%?\s*',norm(part))
        if not m:return None
        key={'categorie':'categorie','catigorier':'categorie','cat':'categorie','tva':'taux_tva','unite':'unite','u':'unite','site':'site'}[m[1]]
        value=m[2].rstrip('%').upper()
        if key in shared and shared[key]!=value:return None
        shared[key]=value
    return Delta(intent='new',articles=[{'designation':label}],shared=shared)


def labelled_initial(text):
    """Complete labelled single article; unknown/duplicate clauses go to the model."""
    from app.services.chat_model import Delta
    n=norm(text)
    if not re.search(r'\bcreer\s+un\s+(?:nouvel\s+)?article\b',n):return None
    markers=list(re.finditer(r'\b(designation|categorie(?:\s+article)?|unite|site|tva|gestion\s+de\s+stock)\s*:',n))
    if not markers or markers[0][1]!='designation':return None
    prefix=n[:markers[0].start()]
    if not re.fullmatch(r'\s*(?:merci\s+de\s+)?creer\s+un\s+(?:nouvel\s+)?article(?:\s+dans\s+sage\s+x3)?[\s,.:;-]*(?:avec\s+les\s+informations\s+suivantes[\s:;-]*)?',prefix):return None
    data={}
    for i,m in enumerate(markers):
        value=text[m.end():markers[i+1].start() if i+1<len(markers) else len(text)].strip(' \t\r\n-;,.')
        key={'categorie article':'categorie','categorie':'categorie','designation':'designation','unite':'unite','site':'site','tva':'taux_tva','gestion de stock':'gestion_stock'}[m[1]]
        if key in data or not value:return None
        if key=='designation':
            if len(value)>70:return None
        elif key=='gestion_stock':
            if norm(value) not in ('non gere en stock','non gere'):return None
            value='1'
        elif key=='taux_tva':
            if not re.fullmatch(r'\d{1,2}(?:[.,]\d+)?\s*%?',value):return None
            value=value.rstrip('%').strip().replace(',','.')
        else:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,5}',value):return None
            value=value.upper()
        data[key]=value
    designation=data.pop('designation')
    return Delta(intent='new',articles=[{'designation':designation}],shared=data)


def apply(state,text,delta):
    view=presentation(text) if delta.intent!='new' else None
    if view:state['presentation']={'article_view':view};state['last_turn']['presentation_requested']=True
    if creation_request(text,state):
        state['last_turn']['creation_requested']=True
        from app.services.chat_semantics import targets
        selected=targets(text) or delta.targets or list(range(1,len(state.get('articles',[]))+1))
        state['creation_request']={'article_ids':[a['id'] for i,a in enumerate(state.get('articles',[]),1) if i in selected],'status':'requested','write_approved':False}
    if state.get('last_turn',{}).get('readonly'):return state
    sites=declared_sites(text)
    if not sites:return state
    from app.services.chat_semantics import targets
    selected=targets(text) or delta.targets or list(range(1,len(state.get('articles',[]))+1))
    # Multiple per-article declarations are already scoped by the merger. Never
    # replace their distinct sites by the first site mentioned in the message.
    if delta.intent=='new' and len({p.site for p in delta.articles if p.site})>1:return state
    for index in selected:
        if index>len(state['articles']):raise ValueError('invalid_article_target')
        article=state['articles'][index-1]
        if len(sites)>1 or article.get('requested_sites'):
            article['requested_sites']=sites
            article.setdefault('sources',{})['requested_sites']='user_declared'
    return state
