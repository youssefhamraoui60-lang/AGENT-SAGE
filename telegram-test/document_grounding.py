"""Preserve structured document rows through the text model, without inference."""
import json,re
from decimal import Decimal
import jsonschema
from datetime import datetime
from document_vision import SCHEMA

def structured(text):
    if 'DOCUMENT JOINT' not in text:return []
    found=[]
    for raw in re.findall(r'(?m)^TRANSCRIPTION STRUCTUREE SOB : (.+)$',text):
        try:
            data=json.loads(raw);jsonschema.validate(data,SCHEMA);found.append(data)
        except (ValueError,jsonschema.ValidationError):continue
    return found

def explicit_delivery(text):
    if 'DOCUMENT JOINT' not in text:return None
    caption,body=text.split('DOCUMENT JOINT',1)
    if re.search(r'(?i)livrais|livrer|demain|aujourd',caption):return None
    body=body.replace('|',' ')
    dates=set()
    values=re.findall(r'(?i)DATE\s+(?:DE\s+)?LIVRAISON\s*:\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})',body)
    rows=body.splitlines()
    for i,row in enumerate(rows[:-1]):
        if re.search(r'(?i)DATE\s+(?:DE\s+)?LIVRAISON\s*:\s*$',row):
            below=re.findall(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b',rows[i+1])
            if len(below)==1:values.extend(below)
    for value in values:
        try:dates.add(datetime.strptime(re.sub(r'[.-]','/',value),'%d/%m/%Y').date().isoformat())
        except ValueError:continue
    return next(iter(dates)) if len(dates)==1 else None

def apply(draft,text,canonical=None):
    docs=structured(text)
    if not docs:
        if not apply_explicit_steel_table(draft,text):apply_explicit_cement_table(draft,text)
        apply_cement_unit_table(draft,text)
        if canonical:restore_complete_product_labels(draft,text,canonical)
        return
    if len(docs)!=1:return
    data=docs[0]
    if not data['lines']:return
    lines=[]
    for row in data['lines']:
        price=row.get('price')
        if row.get('price_kind')=='HT':
            rate=data.get('tax_percent')
            price=float(Decimal(str(price))*(1+Decimal(str(rate))/100)) if price is not None and rate is not None else None
        lines.append({'article':row['label'],'quantity':row.get('quantity'),'unit':row.get('unit'),
                      'price':price,'price_unit':row.get('price_unit')})
    draft['lines']=lines;draft['intent']='order'

def restore_complete_product_labels(draft,text,canonical):
    if 'DOCUMENT JOINT' not in text:return
    from understanding import normalized
    patterns={
        '30':r'afriflex30(?:w|vv)(?:60)?(?:ff)?(?:rlx)?',
        '40':r'afriflex40py(?:180)?(?:ff)?(?:rlx)?',
    }
    for family,pattern in patterns.items():
        source_labels=[]
        for raw in text.split('DOCUMENT JOINT',1)[1].splitlines():
            clean=re.sub(r'\s+',' ',raw.replace('|',' ')).strip()
            m=re.match(r'(?i)^(AFRIFLEX\s*30\s*(?:W|VV)\s*60\s*F\s*/\s*F|AFRIFLEX\s*40\s*PY\s*180\s*F\s*/\s*F)\s+RLX\b',clean)
            if m and re.fullmatch(pattern,normalized(m[1])) and canonical(m[1])!=m[1]:source_labels.append(m[1])
        candidates=[r for r in draft['lines'] if re.fullmatch(pattern,normalized(r.get('article') or ''))]
        if len(source_labels)==1 and len(candidates)==1:candidates[0]['article']=source_labels[0]
    brick_labels={}
    for raw in text.split('DOCUMENT JOINT',1)[1].splitlines():
        clean=re.sub(r'\s+',' ',raw.replace('|',' ')).strip()
        m=re.search(r'(?i)\bBRIQUES?\s*(?:ROUGES?\s*)?(?:D\s*)?0?(7|10|15)(?!\d)',clean)
        if m and re.search(r'\d',clean[:m.start()]+clean[m.end():]):
            label=m[0];code=canonical(label)
            if code!=label:brick_labels[code]=label
    if len(brick_labels)==1:
        for row in draft['lines']:
            if normalized(row.get('article') or '') in ('brique','briques','briquerouge','briquesrouges'):
                row['article']=next(iter(brick_labels.values()))

def apply_explicit_steel_table(draft,text):
    if 'DOCUMENT JOINT' not in text:return
    body=text.split('DOCUMENT JOINT',1)[1]
    rows=[]
    for raw in body.splitlines():
        clean=re.sub(r'\s+',' ',raw.replace('|',' ')).strip()
        m=re.fullmatch(r'(?i)(?:FER|RAB|ACIER(?: HA)?)\s*(?:T|D)?0?(6|8|10|12|14|16|20|25|32)\s+(\d+(?:[.,]\d+)?)\s*(TONNES?|KG)',clean)
        if m:rows.append({'article':'RABT6' if m[1]=='6' else 'RAB'+m[1],
                         'quantity':float(m[2].replace(',','.')),'unit':m[3],'price':None,'price_unit':None})
    candidate_rows=[r for r in body.splitlines() if re.match(r'(?i)^\s*(?:FER|RAB|ACIER HA)\s*(?:\||\s)+(?:[TD]?\s*)?[0-9IO]',r)]
    if not rows or len(candidate_rows)!=len(rows) or len({r['article'] for r in rows})!=len(rows):return
    # Do not discard mixed goods. Only a steel-only table can replace its rows.
    if re.search(r'(?im)^\s*(?:CIMENT|BRIQUE|CPJ|MADRIER|SIKA)\b',body):return
    prices=re.findall(r'(?is)COLONNE PRIX \(LECTURE AGRANDIE\)\s*:\s*PRIX\s*\|?\s*TTC/KG\s*\n\s*(\d+[.,]\d+)\s*(?=\n|$)',body)
    if len(set(prices))==1:
        for row in rows:row.update(price=float(prices[0].replace(',','.')),price_unit='KG')
    draft['lines']=rows;draft['intent']='order'
    return True

def apply_explicit_cement_table(draft,text):
    if 'DOCUMENT JOINT' not in text:return
    body=text.split('DOCUMENT JOINT',1)[1]
    if not re.search(r'(?i)PRIX\s*\|?\s*TTC\s*/\s*(?:T\b|TONNE)',body):return
    rows=[]
    for raw in body.splitlines():
        clean=re.sub(r'\s+',' ',raw.replace('|',' ')).strip()
        m=re.fullmatch(r'(?i)CIMENT\s*(35|45)(?:\s+[A-Z]+)*?\s+(\d+(?:[.,]\d+)?)\s+TONNES?\s+([\d ]+[.,]\d{2})\s+([\d ]+[.,]\d{2})',clean)
        if not m:continue
        qty,price,total=(Decimal(v.replace(' ','').replace(',','.')) for v in [m[2],m[3],m[4]])
        if abs(qty*price-total)>Decimal('.02'):return
        rows.append({'article':'CPJ'+m[1],'quantity':float(qty),'unit':'TONNE','price':float(price),'price_unit':'TONNE'})
    candidates=[r for r in body.splitlines() if re.match(r'(?i)^\s*CIMENT\s*\|?\s*(?:35|45)\b',r)]
    if not rows or len(rows)!=len(candidates):return
    if re.search(r'(?im)^\s*(?:FER|BRIQUE|MADRIER|SIKA)\b',body):return
    draft['lines']=rows;draft['intent']='order'

def apply_cement_unit_table(draft,text):
    """Check printed quantity × unit TTC price = line amount before repair."""
    if 'DOCUMENT JOINT' not in text:return
    body=text.split('DOCUMENT JOINT',1)[1].replace('|',' ')
    if not re.search(r'(?i)PRIX\s+U\s+TTC',body):return
    if re.search(r'(?i)\b(?:PU|PRIX)\b[^\n]*\bH\.?\s*T\.?\b',body):return
    rows=[];candidates=[]
    for raw in body.splitlines():
        clean=re.sub(r'\s+',' ',raw).strip()
        if not re.match(r'(?i)^(?:\d+\s+)?(?:CIMENT|CPJ)(?=\s|\d)',clean):continue
        candidates.append(clean)
        m=re.match(r'(?i)^(?:\d+\s+)?(?:CIMENT|CPJ)\s*(35|45)\s+(\d+(?:[.,]\d+)?)\s+(.+)$',clean)
        if not m:continue
        amounts=re.findall(r'\d[\d\s]*[.,]\d{2}(?!\d)',m[3])
        if len(amounts)!=2 or re.search(r'(?i)\b(?:TONNES?|KG)\b',m[3]):continue
        q=Decimal(m[2].replace(',','.'));price,total=(Decimal(re.sub(r'\s','',v).replace(',','.')) for v in amounts)
        if q<=0 or abs(q*price-total)>Decimal('.02'):continue
        rows.append({'article':'CPJ'+m[1],'quantity':float(q),'unit':None,'price':float(price),'price_unit':None})
    if not rows or len(rows)!=len(candidates):return
    draft['lines']=[l for l in draft['lines'] if not re.match(r'(?i)^(?:CPJ|CIMENT)',str(l.get('article') or ''))]+rows
    draft['intent']='order'

def issues(text):
    result=[]
    if 'LECTURE INCERTAINE A CONFIRMER' in text:result.append('lecture du document incertaine : confirmer les quantités/zones signalées')
    for data in structured(text):
        if data.get('uncertain') or any(r.get('uncertain') for r in data['lines']):result.append('lecture visuelle ambiguë : vérifier les zones signalées du document')
        for i,row in enumerate(data['lines'],1):
            if row.get('quantity') is None or not row.get('unit'):result.append(f'quantité/unité non lisible du document, ligne {i}')
            if row.get('price') is not None and row.get('price_kind')=='HT' and data.get('tax_percent') is None:result.append(f'taux TVA non explicite pour le prix HT, ligne {i}')
            if row.get('price') is not None and row.get('price_kind')=='unknown':result.append(f'base HT/TTC non lisible du prix document, ligne {i}')
    return list(dict.fromkeys(result))
