"""Minimal, literal Sage product intake, including when inference is offline."""
import re
from app.services.chat_turns import norm

def parse(text,state):
    if state.get('discussion_mode')=='supplier' and state.get('supplier_target','TEST')!='OB':return None
    body=re.sub(r'\b(?:artilces|articels|artcles|articele)\b','articles',text,flags=re.I)
    body=re.sub(r'\b(?:articlmes|artice)\b','article',body,flags=re.I)
    body=re.sub(r'\b(?:cr2er|crer)\b','creer',body,flags=re.I)
    body=re.sub(r'\bl"(?=\s*articles?\b)',"l'",body,flags=re.I)
    body=re.sub(r'\barticne\b','article',body,flags=re.I)
    body=re.sub(r'\b(?:cati[ée]gorier|catigorier|catigorer)\b','categorie',body,flags=re.I)
    body=re.sub(r'\bdasn\b','dans',body,flags=re.I)
    body=re.sub(r'\buniter\b','unite',body,flags=re.I)
    body=re.sub(r"\bl\s*&\s*articles?\b",'article',body,flags=re.I)
    n=norm(body).strip(' .!')
    category=r'(?:cat(?:egorie|igonier|igourier|igourer)|ctigorier)'
    creation=bool(re.search(r"\b(?:creer?|crrer|crer|ajouter?)\s+(?:(?:un|une|nouvel|nouveau|le|les|cet|cette)\s+|l['’]\s*)?articles?\b",n))
    if re.search(r'\b(?:annul\w*|modifi\w*|desactiv\w*|reactiv\w*|activ\w*|supprim\w*|cherch\w*|consult\w*)\b',n):return None
    if re.search(r'\b(?:texte|blog|redig\w*|journal|public cible)\b',n):return None
    active=[a for a in state.get('articles',[]) if a.get('operation',{}).get('status') not in ('succeeded','executing','ambiguous','cancelled','failed','unverified')]
    pending=state.get('article_intake_pending')
    if not creation and not pending and not active:return None
    if len(active)==1:
        # Answers to a category question are matched against the actual Sage
        # choices presented for this draft, rather than a hard-coded code list.
        options=active[0].get('category_options') or {}
        if options.get('folder')==state.get('supplier_target',active[0].get('dossier_cible','TEST')):
            declared=re.sub(r"^\s*c['’]est\s+(?:le\s+|la\s+)?",'',body,flags=re.I).strip(' .!')
            matches=[choice for choice in options.get('choices',[]) if norm(declared) in (norm(choice.get('code','')),norm(choice.get('label','')))]
            if len(matches)==1:
                return {'name':active[0].get('designation'),'target_id':active[0]['id'],'review':True,'category_label':declared}
        accounting=re.fullmatch(r'\s*(?:(?:le\s+)?code\s+comptable\s*(?:est\s*|[:=]\s*)?)?([0-9]{3,15})\s*',body,re.I)
        blocker=' '.join(active[0].get('sql_blockers',[]))+' '+str(active[0].get('operation',{}).get('message',''))
        if accounting and re.search(r'\bcomptable\b',norm(blocker)):
            field='code_comptable' if re.search(r'\bcode\s+comptable\b',norm(body)) else 'compte_general'
            return {'name':active[0].get('designation'),'target_id':active[0]['id'],'review':True,field:accounting[1]}
        full_name=re.fullmatch(r'\s*(?:le\s+)?nom\s+compl[eé]te?\s+est\s+(.+?)\s*[.!]?\s*',body,re.I)
        if full_name:
            return {'name':full_name[1].strip(),'target_id':active[0]['id']}
        existing=active[0].get('designation') or ''
        if re.fullmatch(r'[\w -]{2,70}',body.strip()) and (norm(existing)==norm(body.strip()) or norm(existing).startswith(norm(body.strip())+' ')):
            return {'name':existing,'target_id':active[0]['id'],'review':True}
        unit=re.fullmatch(r"\s*(?:(?:le|la|l['’])\s*)?unit[eé]\s*(?:est\s*|[:=]\s*)?([A-Za-z0-9_]{1,5})\s*[.!]?\s*",body,re.I)
        if unit or body.strip().upper()=='UN':
            return {'name':active[0].get('designation'),'target_id':active[0]['id'],'review':True,'unite':unit[1].upper() if unit else 'UN'}
        # A direct answer to the category question updates the same draft.
        answer=re.fullmatch(r"\s*(?:c['’]est\s+(?:le\s+|la\s+)?)?([^\W\d_][\w]{1,19})\s*[.!]?\s*",body,re.I)
        if answer and (answer[1].upper()=='NEG' or norm(answer[1]) in ('negose','negos','negoce','negouse')):
            return {'name':active[0].get('designation'),'target_id':active[0]['id'],'review':True,'category_label':answer[1]}
    # An explicit name, site and category in the same pending-name answer.
    rich=re.fullmatch(r"\s*(?:le\s+)?article\s+est\s+(.+?)\s+dans\s+le\s+site\s+(\d{2,5})\s+et\s+(?:son|la)\s+categorie\s+est\s+([\w -]{1,100})\s*[.!]?\s*",body,re.I)
    if rich and (pending or len(active)==1):
        return {'name':rich[1].strip(),'site':rich[2],'category_label':rich[3].strip(),'target_id':active[0]['id'] if len(active)==1 else None}
    name=None;label=None
    # Split explicit field clauses before interpreting the name, rather than
    # storing "Tempo et dans la catégorie ..." as one designation.
    combined=re.search(r'(?:\s+et\s+|[,;]\s*|\s+(?=dans\s+la\b))(?:(?:dans|pour)\s+)?(?:la\s+)?'+category+r'\s*(?:(?:est|dois|doit)\s+|[:=]\s*)?([\w -]{1,100})\s*[.!]?\s*$',norm(body))
    if combined:
        label=body[combined.start(1):combined.end(1)].strip(' .')
        if re.search(r'\b(?:site|unite|fournisseur|tva|code)\b',norm(label)):return None
        body=body[:combined.start()].strip(' ,;.');n=norm(body).strip(' .!')
        if not body and label and len(active)==1:
            return {'name':active[0].get('designation'),'target_id':active[0]['id'],'category_label':label,'review':True}
    declaration=re.fullmatch(r"\s*(?:la|le|mon|mes|l['’])\s*articles?\s+(?:est|s.appelle)\s+(.+?)\s*[.!]?\s*",body,re.I)
    if not declaration:declaration=re.fullmatch(r"\s*(?:le\s+)?nom\s+(?:de\s+)?(?:l['’]\s*|du\s+)?articles?\s*(?:est\s+|[:=]\s*)(.+?)\s*[.!]?\s*",body,re.I)
    if declaration:name=declaration[1].strip(' .')
    category_only=re.fullmatch(r'\s*(?:et\s+)?(?:(?:dans|pour)\s+)?(?:la\s+)?'+category+r'\s*(?:(?:est|dois|doit)\s+|[:=]\s*)?([\w -]{1,100})\s*[.!]?\s*',body,re.I)
    if len(active)==1 and category_only:
        return {'name':active[0].get('designation'),'target_id':active[0]['id'],'category_label':category_only[1].strip(),'review':True}
    if pending and not declaration and not creation and re.fullmatch(r"[\w][\w .'-]{0,69}",body.strip()) and not re.search(r'\b(?:bonjour|salut|merci|oui|non|categorie|catigonier|site|unite|fournisseur|veux|pourquoi|comment)\b',n):name=body.strip()
    # Only a short literal name and optional category: rich requests retain
    # the existing extraction path, supplier/site scopes and correction logic.
    if creation:
        m=re.search(r"\b(?:creer?|crrer|crer|ajouter?)\s+(?:(?:un|une|nouvel|nouveau|le|les|cet|cette)\s+|l['’]\s*)?articles?\b",norm(body))
        tail=body[m.end():].strip(' .')
        cat=re.search(r'\b(?:la\s+)?'+category+r'\s*(?:(?:est|dois|doit)\s+|[:=]\s*)?(.+?)\s*$',norm(tail))
        if cat:
            label=tail[cat.start(1):cat.end(1)].strip(' .')
            if not re.fullmatch(r'[\w -]{1,100}',label) or re.search(r'\b(?:unite|site|fournisseur|tva|code)\b',norm(label)):return None
            tail=tail[:cat.start()].strip(' ,;.')
        if not tail or re.fullmatch(r'(?:de test|pour validation)',norm(tail)):name=None
        elif re.fullmatch(r'[\w *×./-]{1,70}',tail) and not re.search(r'\b(?:site|unite|designation|fournisseur|qui|est|nomme|nom|code|suivant|merci|et|sans)\b',norm(tail)):
            name=tail
        else:return None
    if name and (len(name)>70 or re.search(r'\b(?:site|unite|categorie|fournisseur|merci|et)\b',norm(name))):return None
    if name:return {'name':name,'category_label':label,'target_id':active[0]['id'] if len(active)==1 and (declaration or norm(active[0].get('designation',''))==norm(name)) else None}
    if creation and len(active)==1:return {'name':active[0].get('designation'),'target_id':active[0]['id'],'review':True}
    if creation and not active:return None if state.get('articles') else {'ask_name':True}
    return None
