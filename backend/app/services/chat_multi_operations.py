"""Literal mixed requests and dependency planning. No Sage writes or inferred codes."""
import re
from app.services.chat_turns import norm


SUPPLIER=r'(?:fournisseur|founiseur|forniseur|fourniseur|fornisseur)'


def canonical(text):
    text=re.sub(SUPPLIER,'fournisseur',text,flags=re.I)
    return re.sub(r'\bveuxc\s+r[eé]er\b','veux créer',text,flags=re.I)


def literal_extract(text,state):
    """Extract bounded labelled multi-operation facts; unknown prose uses AI.

    Values are slices of the user's original text. This route never supplies a
    missing category, supplier code, tax code or account.
    """
    from app.services.chat_model import Delta
    n=norm(text)
    if '?' in text or not re.search(SUPPLIER,n) or not re.search(r'\barticles?\b',n):return None
    if re.search(r'\b(?:prix|remise|incoterm|adresse|email|telephone)\b',n):return None
    if not re.search(r'\b(?:creer?|creation|veuxc\s+reer)\b',n):return None
    supplier=re.search(r'(?:mon\s+'+SUPPLIER+r'\s+c.est|(?:creer?|prepare)\s+(?:(?:un|le|la)\s+)?'+SUPPLIER+r')\s*[:=]?\s*(.+?)(?=\s+(?:forme\s+juridique|capital|annee|rc\b|ice\b)|[,;\n]|\s+et\s+(?:creer?|un\s+article|(?:(?:les|des)\s+)?articles?\b))',n,re.S)
    if not supplier:return None
    facts={'nom':text[supplier.start(1):supplier.end(1)].strip()}
    labels={
        'forme_juridique':r'forme\s+juridique\s*[:=]?\s*(.+?)(?=\s+(?:capital|annee|rc\b|ice\b)|[,;\n])',
        'capital':r'\bcapital\s*[:=]?\s*([\d][\d .,]*\s*(?:dh|mad|eur|usd))\b',
        'annee_creation':r'annee\s+de\s+creation\s*[:=]?\s*(\d{4})',
        'rc':r'\brc\s*[:=]?\s*([a-z0-9/-]+)',
        'ville_rc':r'\brc\s*[:=]?\s*[a-z0-9/-]+\s*\(([^)]+)\)',
        'ice':r'\bice\s*[:=]?\s*(\d{15})(?!\d)'}
    for field,pattern in labels.items():
        match=re.search(pattern,n,re.S)
        if match:facts[field]=text[match.start(1):match.end(1)].strip()
    shared={'fournisseur_nom':facts['nom']}
    unit=re.search(r'\bunit(?:e|er|ee)\s+(?:de\s+articles?\s+)?(?:est\s+)?(?:[:=]\s*)?([a-z0-9]{1,3})\b',n)
    if unit:shared['unite']=unit[1].upper()
    tax=re.search(r'\btva\s*(?:demandee\s+|de\s+|[:=]\s*)?(\d{1,2}(?:[.,]\d+)?)\s*%?',n)
    if tax:shared['taux_tva']=tax[1].replace(',','.')
    if re.search(r'\bnon\s+ger(?:e|er)\b',n):shared['gestion_stock']='1'
    site=re.search(r'\bsite\s+(?:(?:de\s+)?(?:frais?\s+generaux|freer\s+geniro)\s+)?(\d{3})\b',n)
    if site:shared['site']=site[1]
    category=re.search(r'\b(?:categorie|cat)\s*[:=]?\s*([a-z0-9_-]{1,5})\b',n)
    if category:shared['categorie']=category[1].upper()
    # Numbered lists are exact entities; a per-line site overrides shared site.
    numbered=re.findall(r'(?m)^\s*(\d{1,2})[.)]\s*(.+)$',text)
    articles=[]
    if numbered:
        if [int(i) for i,_ in numbered]!=list(range(1,len(numbered)+1)) or len(numbered)>20:return None
        for _,line in numbered:
            parts=re.split(r'[,;]',line)
            item={'designation':parts[0].strip()}
            for part in parts[1:]:
                m=re.fullmatch(r'\s*(site|categorie|cat|unite)\s*[:=]?\s*([a-z0-9_-]+)\s*[.]?',norm(part))
                if not m:return None
                item[{'cat':'categorie'}.get(m[1],m[1])]=m[2].upper()
            articles.append(item)
        # Site declarations in individual numbered rows are never global.
        if any(a.get('site') for a in articles):shared.pop('site',None)
    else:
        marker=re.search(r'\b(?:creer?|prepare)\s+(?:(?:le|les|un|une|la)\s+)?articles?\s+(.+?)(?=\s+(?:etreffirzncer|et\s+referencer|a\s+rattacher|unite|le\s+unit|categorie|cat\b|site\b|tva\b)|[,;\n]|$)',n,re.S)
        coordinated=False
        if not marker:
            marker=re.search(r'\bet\s+(?:(?:les|des)\s+)?articles?\s*:\s*(.+?)(?=\s+(?:unite|categorie|site|tva)\b|[,;\n]|$)',n,re.S)
            coordinated=bool(marker)
        if not marker:return None
        designation=text[marker.start(1):marker.end(1)].strip().rstrip('.')
        designation=re.sub(r'\s+(?:cdlt|cordialement|merci)[.!\s]*$','',designation,flags=re.I).strip()
        if not designation or len(designation)>70:return None
        names=re.split(r'\s+et\s+',designation,flags=re.I) if coordinated else [designation]
        if not 1<=len(names)<=20 or any(not name.strip() for name in names):return None
        articles=[{'designation':name.strip().rstrip('.')} for name in names]
    try:
        return Delta(intent='new',shared=shared,articles=articles,fournisseurs=[facts])
    except ValueError:return None


def plan(state):
    """Rebuild read-only dependency status from persisted drafts and evidence."""
    operations=[]
    suppliers=[p for p in state.get('partners',[]) if p['kind']=='supplier']
    for p in suppliers:
        reference=p.get('checks',{}).get('tools',{}).get('name',{})
        rows=reference.get('rows',[])
        exact=[r for r in rows if norm((r.get('BPRNAM_0') or '').strip())==norm(p.get('nom',''))]
        status='lookup_pending' if not reference.get('ok') else 'existing_requires_selection' if rows else 'absent_draft_only'
        prep=p.get('preparation')
        if prep:
            if any(d['supplier_exists'] for d in prep['duplicates']):status='existing_requires_selection'
            elif prep['duplicates']:status='existing_partner_requires_review'
            elif not prep.get('duplicate_check_complete'):status='lookup_pending'
            elif prep['target_folder']=='OB':status='absent_draft_only'
        p['resolution']={'status':status,'existing_candidates':rows,'exact_match_count':len(exact),'creation_executed':False}
        operations.append({'id':'supplier:'+p['id'],'kind':'supplier','status':status,'human_approval_required':True})
    for a in state.get('articles',[]):
        matching=[p for p in suppliers if norm(p.get('nom',''))==norm(a.get('fournisseur_nom') or '')]
        if not matching:
            a.pop('supplier_dependency',None)
            continue
        partner=matching[0]
        a['supplier_dependency']={'partner_id':partner['id'],'name':partner['nom'],'status':partner['resolution']['status'],
            'code':partner.get('code'),'binding_verified':False,'creation_executed':False}
        operations.append({'id':'article:'+a['id'],'kind':'article','depends_on':['supplier:'+partner['id']],
            'status':'draft_incomplete' if any(not a.get(k) for k in ('categorie','unite','site')) else 'business_validation_required',
            'missing_fields':[k for k in ('categorie','unite','site') if not a.get(k)],'human_approval_required':True})
        operations.append({'id':'association:'+a['id'],'kind':'supplier_article_link','depends_on':['supplier:'+partner['id'],'article:'+a['id']],
            'status':'blocked_pending_verified_supplier_code_and_mapping','human_approval_required':True})
    state['operation_plan']={'operations':operations,'sage_writes':0,'approval_granted':False}
    return state


def compose(state):
    operations=state.get('operation_plan',{}).get('operations',[])
    if not operations:return ''
    lines=['Opérations dépendantes — préparation uniquement, aucune écriture autorisée :']
    statuses={'lookup_pending':'recherche fournisseur indisponible ou à effectuer',
        'existing_requires_selection':'fournisseur existant ou proche : sélectionner la fiche, sans en créer une autre',
        'existing_partner_requires_review':'tiers déjà présent : rôle fournisseur et rapprochement à examiner avant création',
        'absent_draft_only':'aucun fournisseur retourné : brouillon de création à compléter',
        'draft_incomplete':'article à compléter : catégorie ou autre paramètre obligatoire manquant',
        'business_validation_required':'article à vérifier dans Sage avant préparation',
        'blocked_pending_verified_supplier_code_and_mapping':'rattachement bloqué : code fournisseur vérifié et mapping nécessaires'}
    labels={'supplier':'Fournisseur','article':'Article','supplier_article_link':'Rattachement fournisseur–article'}
    for operation in operations:lines.append('- '+labels[operation['kind']]+' : '+statuses.get(operation['status'],operation['status']))
    lines.append('Le fournisseur n’est pas créé. Les articles et leurs fiches article-site nécessitent des validations séparées. Une approbation humaine des données exactes sera requise avant toute écriture ; un « oui » dans le chat ne suffit pas.')
    return '\n'.join(lines)
