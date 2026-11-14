"""Narrow provenance proofs for normalized labels and explicit coreferences."""
import re
from app.services.modification_resolvers import norm as label_norm,CategoryResolver
from app.services.chat_turns import norm

def label(value):
    n=label_norm(value)
    n=re.sub(r'^(?:(?:c est|cest|est|dois|doit|deyalo)\s+)+','',n)
    n=re.split(r'\b(?:pas|mais)\b',n)[0].strip()
    return ' '.join(CategoryResolver.SYNONYMS.get(w,w) for w in n.split())

def resolve(field,value,text,state,target,search):
    n=norm(text)
    if field in ('unite','unite_achat','unite_vente'):
        from app.services.unit_references import proof
        verified=proof(value,text,state,state.get('supplier_target','TEST'))
        if verified:return verified
    if field in ('code_tva','niveau_taxe'):
        from decimal import Decimal,InvalidOperation
        result=(state.get('article_reference_choices') or {}).get('tax') or {}
        choices=result.get('choices',[]) if result.get('ok') and result.get('folder')==state.get('supplier_target','TEST') else []
        try:same_rate=Decimal(str(result.get('rate')))==Decimal(str((target or {}).get('taux_tva')).replace(',','.'))
        except InvalidOperation:same_rate=False
        eligible=[choice for choice in choices if not choice.get('conditional')]
        if same_rate and len({choice['code'] for choice in eligible})==1 and value==eligible[0]['code']:
            return {'source':'verified_tax_rate_reference','value':value,'rate':result['rate'],'folder':result['folder'],'requires_business_review':True}
    if field=='unite' and norm(str(value)) in ('u','unite','un') and re.search(r'/\s*(?:u|unite)\s*(?:/|$)',n):
        from app.services import chat_tools
        folder=state.get('supplier_target','TEST')
        result=chat_tools.run([{'id':'unit_alias','tool':'get_units','args':{'Unit':'UN','Unit2':'','Folder':folder}}]).get('unit_alias',{})
        if result.get('ok') and result.get('folder','TEST')==folder and any(str(row.get('UOM_0') or '').strip()=='UN' for row in result.get('rows',[])):
            return {'source':'verified_declared_unit_alias','value':'UN','declared_alias':'U/UNITE','reference':'UN','folder':folder}
    if field=='site' and target and re.search(r'\bmeme site\b',n) and not re.search(r'\bpas (?:le )?meme site\b',n):
        sites={str(a.get('site')).strip() for a in state.get('articles',[]) if a.get('id')!=target.get('id') and a.get('site') and len(a.get('requested_sites') or [a['site']])==1}
        if sites=={str(value)}:return {'source':'explicit_same_site','value':value}
    if field not in ('categorie','categorie_libelle','unite'):return None
    if field=='categorie' and isinstance(value,str) and re.search(r'(?<!\w)'+re.escape(norm(value))+r'(?!\w)',n):return None
    declared=re.search(r'\bcategorie\s+(?:(?:c est|cest|est|dois|doit|deyalo)\s+)?(.+?)(?=\bpas\b|[,.;]|$)',n)
    current_label=declared[1] if declared else None
    # A descriptive instruction about category defaults is not a new label.
    if current_label and re.search(r'\b(?:regarde|choisie|pas la designation)\b',current_label):current_label=None
    original=(target or {}).get('categorie_libelle')
    wanted=label(current_label or original or '')
    if not wanted or len(current_label or original or '')>100:return None
    result=state.get('category_search') or {}
    choices=result.get('choices',[]) if result.get('ok') and result.get('folder','TEST')==state.get('supplier_target','TEST') else []
    exact=[c for c in choices if wanted in (label(c.get('label','')),label(c.get('code','')))]
    if not exact and field in ('categorie','categorie_libelle'):
        result=search(current_label or original);choices=result.get('choices',[]) if result.get('ok') else []
        exact=[c for c in choices if wanted in (label(c.get('label','')),label(c.get('code','')))]
    if len(exact)!=1:return None
    reference=exact[0]
    if field=='categorie' and value==reference['code']:
        if (target or {}).get('categorie') and not current_label:return None
        return {'source':'verified_category_label','value':value,'reference':reference['code'],'reference_label':reference['label'],'declared_label':current_label or original}
    if field=='categorie_libelle' and label(value)==label(reference['label']):
        return {'source':'verified_category_label','value':reference['label'],'reference':reference['code']}
    if field=='unite' and re.search(r'\bstock\b.*\b(?:regarde|selon|categorie)\b',n):
        unit=str(reference.get('parameters',{}).get('STU_0','')).strip()
        if unit and value==unit and (not (target or {}).get('unite') or target['unite']==unit):return {'source':'explicit_category_stock_unit','value':unit,'reference':reference['code']}
    return None
