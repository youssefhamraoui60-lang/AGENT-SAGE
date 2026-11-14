"""Deterministic speech acts protect persisted business state from model guesses."""
import re,unicodedata
from dataclasses import dataclass,field

def norm(text):return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c)).casefold()

@dataclass
class Turn:
    kind:str
    readonly:bool=False
    values:dict=field(default_factory=dict)
    lookups:dict=field(default_factory=dict)
    restricted:bool=False
    clear_fields:list=field(default_factory=list)
    targets:list=field(default_factory=list)

STOP={'est','le','la','les','un','une','il','elle','pour','vers','par','de','du','des','et','ce','code','article','comptable','oui','non'}
SUPPLIER_WORD=r'(?:fournisseur|founnisseur|founisseur|founiss+eur|founiseur|fournsieur|fornisseur|fourniseur|foourniseur|forniseur|fornssieur|fronseur|fourniseu?r|frs)'
def analyse(text,state,_parts=True):
    n=norm(text).strip();existing=bool(state.get('articles'))
    from app.services.chat_article_requests import presentation,creation_request
    if existing and presentation(text):return Turn('presentation',readonly=True)
    if creation_request(text,state):return Turn('creation_request',readonly=True)
    if re.search(r'\b(?:donner?|lister?|lisert|affiche|quels|quelles)\b',n) and re.search(r'\b(?:categories?|catigorier|catigorier?s|catigories?|cztigorier)\b',n) and not re.search(r'\b(?:change|remplace|corrige|creer?)\b',n):
        return Turn('question',readonly=True,lookups={'catalogue_categories':True})
    n=re.sub(r'^(oui|ok)(?=pas\b)',r'\1 ',n)
    if existing and re.fullmatch(r'(?:le code articles?|les codes? articles?|lister le|liste(?:r)?(?: les articles)?|recapitulatif)[.!\s]*',n):
        return Turn('question',readonly=True)
    cancel=bool(re.search(r'\bannul(?:e|er|ation)\b|\bne (?:cree|creer) (?:rien|pas)',n))
    question='?' in n or bool(re.search(r'est.ce qu|\b(?:existe.t.il|y a.t.il|quels|quelles)\b',n))
    # A question inside an email's explanatory paragraphs does not cancel its
    # explicit preparation request and labelled supplier facts. No write consent.
    if re.search(r'\b(?:merci de|je veux|je souhaite)\s+(?:bien vouloir\s+)?creer\s+(?:(?:le|un|nouveau)\s+)*fournisseur\b',n) and re.search(r'\bnom\s*:',n):
        question=False
    lookup=bool(re.search(r'\b(?:verifie|verifier|recherche|rechercher|cherche|chercher|controle|controler|actualise|rafraichis)\b',n))
    # Product names such as "ARTICLE CONTROLE" are data, not lookup commands.
    explicit_creation=bool(re.search(r'\b(?:creer?|prepare|ajoute)\s+(?:(?:le|la|les|ce|cet|cette|ces|un|une|deux|[1-9]|10)\s+)?(?:(?:nouvel|nouveau|nouvelle|nouveaux|nouvelles)\s+)?articles?\b',n))
    if explicit_creation:lookup=False
    correction=bool(re.search(r'\b(?:change|changer|remplace|remplacer|corrige|correction|utilise|retenir|retiens|confirme)\b',n))
    confirmation=bool(re.fullmatch(r'(?:oui(?:\s+merci|\s+(?:je\s+)?conf(?:irme|irmer|irmer?e|iremer))?|d.accord|ok)[.!\s]*',n))
    kind='cancellation' if cancel else 'question' if question else 'confirmation' if confirmation else 'correction' if correction else 'verification' if lookup else 'declaration'
    turn=Turn(kind,kind in ('question','verification','cancellation'))
    # A short answer only binds to an explicit pending field, never a guessed
    # category from product names. The normal SQL validation still follows.
    pending_fields={q.get('field') for q in state.get('pending',[])}
    category_context='categorie' in pending_fields or (existing and all(a.get('categorie')==n.upper() for a in state['articles']))
    if existing and category_context and re.fullmatch(r'[a-z][a-z0-9_-]{0,4}',n) and not re.fullmatch(r'f\w*\d\w*',n) and n not in STOP|{'merci','salut','ok'}:
        turn.values['categorie']=n.upper()
    supplier_word=SUPPLIER_WORD
    if existing and not turn.readonly and re.search(
        r'\b(?:pas\s+(?:de\s+|d[\x27’])|sans\s+|aucun\s+)'+supplier_word+r'\b|\b(?:supprime|retire|enleve)\s+(?:le\s+)?'+supplier_word+r'\b',n):
        turn.kind='correction';turn.clear_fields=['fournisseur_nom','code_fournisseur','reference_fournisseur']
    cat=re.search(r'\b(?:categorie|catigorie|catigorer|ctigorier|categ|cat)\b\s*(?:article\s*)?(?:(?:c.est|est|en|par)\s*)?[:=]?\s*(?:[«"\']\s*)?([\w-]+)',n)
    if cat and cat[1] not in STOP:
        value=cat[1].upper()
        destination=re.search(r'\b(?:categorie|catigorie|catigorer|cat)\s+[\w-]+\s+(?:par|vers|en)\s+([\w-]{1,5})\b',n)
        if destination:value=destination[1].upper()
        if turn.readonly or len(value)>5:turn.lookups['categorie']=value
        elif len(value)<=5:turn.values['categorie']=value
    # A lookup by label is not a confirmed code replacement.
    if turn.readonly:
        # A verification and an explicit declaration may concern different fields.
        # Preserve a question as read-only; only independent declarative clauses
        # in a mixed verification may contribute deterministic scalar values.
        if kind in ('verification','question') and _parts:
            parts=re.split(r'(\bpour\s+l[ea]\b|[;.\n]|\bet\b)',text,flags=re.I)
            if len(parts)>1:
                for i in range(0,len(parts),2):
                    part=parts[i];separator=norm(parts[i-1]).strip() if i else ''
                    sub=analyse(part,state,_parts=False)
                    explicit_clause=sub.kind=='correction' or (separator!='et' and bool(re.search(r'\best\b|[:=]',norm(part))))
                    if not sub.readonly and explicit_clause:turn.values.update(sub.values)
                if turn.values:turn.readonly=False;turn.restricted=True
            # A polite request to change is still an explicit correction. A
            # verification or hypothetical possibility remains read-only.
            polite=re.match(r'\s*(?:peux[ -]tu|pouvez[ -]vous|pourrais[ -]tu)\s+(?:changer|remplacer|corriger|mettre)\b',n)
            if polite:
                sub=analyse(re.sub(r'\?','',text[polite.start():]).split(' ',1)[1],state,_parts=False)
                if sub.values:
                    turn.values.update(sub.values);turn.readonly=False;turn.restricted=True;turn.kind='correction'
        return turn
    site=re.search(r'\bsite\b\s*(?:(?:declare|declaree|retenu|choisi|selectionne)\s+)?(?:(?:est|par|vers|a|au)\b\s*|[:=]\s*)?([a-z0-9_-]{1,5})\b',n)
    destination=re.search(r'\bsite\s+[a-z0-9_-]+\s+(?:vers|par|a|au)\s+([a-z0-9_-]{1,5})\b',n)
    if site and site[1] not in STOP:turn.values['site']=(destination or site)[1].upper()
    labelled_site=re.search(r'\bsite\s+(?:de\s+)?(?:frais?\s+generaux|freer\s+geniro)\s+(\d{3})\b',n)
    if labelled_site:turn.values['site']=labelled_site[1]
    stock=re.search(r'\bgestion(?:\s+de)?\s+stock\s*(?:[:=]\s*)?([123])\b',n)
    if stock:turn.values['gestion_stock']=stock[1]
    if re.search(r'\bnon\s+(?:gere(?:r|e|s)?|greer|grer)\b',n):turn.values['gestion_stock']='1'
    for field,cue,size in [('unite',r'(?:unite|uniter|unitee|unt)',3),('code_article',r'code\s+articles?',20)]:
        found=re.search(r'\b'+cue+r'\b\s*(?:de\s+articles?\s+)?(?:(?:est|en|par|vers)\s+|[:=]\s*)?([a-z0-9_./-]{1,'+str(size)+r'})(?!\w)',n)
        destination=re.search(r'\b'+cue+r'\s+[a-z0-9_./-]+\s+(?:vers|par|en)\s+([a-z0-9_./-]{1,'+str(size)+r'})(?!\w)',n)
        if found and (destination or found[1] not in (STOP-{'un'})|{'avec','commence','commencer','changer','change'}):
            turn.values[field]=(destination or found)[1].upper().rstrip('.')
    if existing and re.fullmatch(r'\d{2,5}[.\s]*',n) and (any(q['field']=='site' for q in state.get('pending',[])) or not any(a.get('site') for a in state['articles'])):
        turn.values['site']=re.sub(r'\D','',n)
    supplier=re.search(r'\b(?:code\s+)?(?:fournisseur|fournsieur|fornisseur|fourniseur|frs)\b\s*(?:(?:est|par|vers|a|en)\b\s*|[:=]\s*)?(F[A-Z0-9_-]{1,14})\b',text,re.I)
    explicit_supplier=re.search(r'\bcode\s+(?:sage\s+)?fournisseur\b\s*(?:est\s*|[:=]\s*)?([a-z0-9_-]{1,15})\b',n)
    supplier_destination=re.search(r'\b(?:fournisseur|frs)\b\s+f[a-z0-9_-]+\s+(?:vers|par|a|en)\s+(f[a-z0-9_-]{1,14})\b',n)
    if supplier and re.search(r'\d',supplier[1]):turn.values['code_fournisseur']=supplier[1].upper()
    if explicit_supplier and explicit_supplier[1] not in STOP:turn.values['code_fournisseur']=explicit_supplier[1].upper()
    if supplier_destination:turn.values['code_fournisseur']=supplier_destination[1].upper()
    if re.fullmatch(r'f[a-z0-9_-]{1,14}[.\s]*',n) and re.search(r'\d',n):turn.values['code_fournisseur']=n.strip(' .\n').upper()
    # A supplier suggestion is not awaiting_confirmation (reserved for category
    # offers). Resolve it from the persisted pending question and SQL proposal.
    supplier_pending=any(q.get('field')=='code_fournisseur' for q in state.get('pending',[]))
    candidates={a.get('proposals',{}).get('code_fournisseur') for a in state.get('articles',[])
                if a.get('fournisseur_nom') and not a.get('code_fournisseur')}
    candidates.discard(None)
    explicit_yes=re.fullmatch(r'(?:oui|ok|je\s+confirme)\s+(?:le\s+)?(f[a-z0-9_-]{1,14})[.!\s]*',n)
    if supplier_pending and len(candidates)==1:
        proposed=next(iter(candidates))
        if kind=='confirmation' or (explicit_yes and explicit_yes[1].upper()==proposed):
            turn.values['code_fournisseur']=proposed
            turn.kind='confirmation'
            turn.targets=[i for i,a in enumerate(state.get('articles',[]),1)
                          if a.get('fournisseur_nom') and not a.get('code_fournisseur') and a.get('proposals',{}).get('code_fournisseur')==proposed]
    if kind=='confirmation':
        offer=state.get('awaiting_confirmation')
        if offer:turn.values[offer['field']]=offer['value']
    return turn
