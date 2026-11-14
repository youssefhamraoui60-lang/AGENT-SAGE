"""Keep the owner-scoped target of a supplier-to-article request across turns.

Only user-selected codes are retained. This module never reads or writes Sage.
"""
import re
from app.services.chat_turns import norm

def track(state,text):
    n=norm(text)
    pending=state.get('article_supplier_request')
    if pending and (pending.get('folder')!=state.get('supplier_target','TEST') or re.search(r'\b(?:annul\w*|cancel|machi|matdir\w*)\b',n)):
        state.pop('article_supplier_request',None)
        return None
    articles=list(dict.fromkeys(a['code_article'] for a in state.get('articles',[]) if a.get('code_article') and a.get('operation',{}).get('status')=='succeeded'))
    articles+=list(dict.fromkeys(r['code'] for r in state.get('tool_read_results',[]) if r.get('ok') and r.get('resource')=='article' and r.get('code') and r.get('folder','TEST')==state.get('supplier_target','TEST')))
    articles=list(dict.fromkeys(articles))
    explicit=[code for code in articles if re.search(r'(?<!\w)'+re.escape(norm(code))+r'(?!\w)',n)]
    link=bool(re.search(r'\b(?:ajout\w*|assoc\w*|rattach\w*|lier|lie|dire|direhame|dirhom|zid)\b',n))
    supplier=bool(re.search(r'\b(?:fourn\w*|frs)\b',n))
    if pending and re.search(r'\b(?:creer|creation|desactiv\w*|reactiv\w*|activ\w*|annul\w*)\b',n):
        state.pop('article_supplier_request',None)
        return None
    if not pending and link and supplier and (len(explicit)==1 or len(articles)==1):
        pending={'folder':state.get('supplier_target','TEST'),'article':(explicit or articles)[0],'supplier_codes':[],'request':text}
        state['article_supplier_request']=pending
    if not pending:return None
    if re.search(r'\b(?:cherche|recherche|consulte|consulter)\b',n) or re.search(r'\b(?:modifi\w*|corrig\w*)\b.*\b(?:telephone|ville|adresse|ice|nom)\b',n):
        state.pop('article_supplier_request',None)
        return None
    if explicit and explicit!=[pending['article']]:
        state.pop('article_supplier_request',None)
        return None
    codes=list(dict.fromkeys(c.upper() for c in re.findall(r'\bF\d+\b',text,re.I)))
    if codes:pending['supplier_codes']=codes
    return pending
