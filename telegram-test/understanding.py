"""Reference ranking and bounded unit rules. No SQL or write capability."""
import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', value)


def name_score(query, name):
    a, b = normalized(query), normalized(name)
    if not a or not b:
        return 0
    if a == b or len(a) >= 5 and a in b:
        return 1
    words = re.findall(r'[A-Za-z0-9]+', query.lower())
    reversed_name = ''.join(reversed(words))
    name_words = re.findall(r'[A-Za-z0-9]+', unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower())
    return max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, reversed_name, b).ratio(),
               SequenceMatcher(None,''.join(sorted(words)),''.join(sorted(name_words))).ratio())


def shorthand(text):
    text=re.sub(r'(?im)^(\s*)(\d+(?:[.,]\d+)?)\s*t\s*0?(6|8|10|12|14|16|20|25|32)\s*$',
                lambda m:m[1]+m[2]+' tonnes '+('RABT6' if m[3]=='6' else 'RAB'+m[3]),text)
    text=re.sub(r'(?m)^(\s*)(\d+)\s*قناطر\s*0?(6|8|10|12|14|16|20|25|32)\s*$',
                lambda m:m[1]+m[2]+' quintaux '+('RABT6' if m[3]=='6' else 'RAB'+m[3]),text)
    text=re.sub(r'(?<!\w)(\d+(?:[.,]\d+)?)\s*t\s*(35|45)(?!\d)',
                lambda m:m[1]+' tonnes CPJ'+m[2], text, flags=re.I)
    return re.sub(r'\b(?:(\d+(?:[.,]\d+)?|un|une)\s*)?(?:voyages?|voiages?|voyge|vys|vgs|vge|voy)\s*(?:de\s+)?(?:cima|sima|ciments?|cpj)\s*(35|45)\b',
                  lambda m:(m[1] if m[1] and m[1].lower() not in ('un','une') else '1')+' voyage CPJ'+m[2],text,flags=re.I)


def customer_phrases(text):
    # Only captions, never arbitrary document footers or phone/contact fields.
    text=text.split('DOCUMENT JOINT:')[0]
    result=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line or len(line)<5 or len(line)>100:
            continue
        if re.match(r'^[+\d]',line) or re.match(r'(?i)^(contact|num[eé]ro|pour|livraison|le chauffeur|reg|lui|d[eé]part|trs|transport|plus|lot)\b',line):
            tail=re.search(r'(?i)\b(?:cpj|ciment|sima|cima)\s*(?:35|45|55)\s+(.+)$',line)
            if tail and len(tail[1])>=5 and not re.fullmatch(r'(?i)(lafarge|cimat|perfecto|temara)',tail[1]):
                result.append(tail[1])
            continue
        if normalized(line) in ('casa','casablanca','berrechid','settat','mohammedia','mohamadia','mediouna'):
            continue
        prefix=re.split(r'(?i)\s+(?:(?:un|une|1)\s+)?(?:voyage|vge)\b',line,maxsplit=1)[0]
        if len(prefix)>=5:
            result.append(prefix)
    return list(dict.fromkeys(result))


def choose_reference(kind, query, rows, representative=None):
    key, label = {'client': ('BPCNUM_0','BPCNAM_0'),
                  'representative': ('REPNUM_0','REPNAM_0'),
                  'article': ('ITMREF_0','ITMDES1_0')}[kind]
    exact = [r for r in rows if normalized(r[key]) == normalized(query)]
    if exact:
        return exact
    if kind == 'client' and representative:
        same = [r for r in rows if r['REP_0'].strip()==representative['REPNUM_0'].strip()]
        if same:
            rows = same
    if kind == 'article':
        # A supplier-specific duplicate does not supersede the base article.
        base = [r for r in rows if not re.search(r'_F\d+$', r[key])]
        if base:
            rows = base
    if kind == 'representative':
        words={normalized(w) for w in query.split()}
        short=[r for r in rows if len(r[label].split())==1 and normalized(r[label]) in words]
        if len(short)==1:
            return short
    exact_names = [r for r in rows if normalized(r[label]) == normalized(query)]
    if exact_names:
        return exact_names
    ranked = sorted(((name_score(query,r[label]),r) for r in rows), key=lambda item:item[0], reverse=True)
    if ranked and ranked[0][0] >= .86 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.08):
        return [ranked[0][1]]
    if kind == 'representative' and len(rows)==1:
        terms = [normalized(w) for w in query.split() if len(w)>=4]
        if any(t in normalized(rows[0][label]) for t in terms):
            return rows
    return rows if len(rows)>1 else []


def normalize_quantity(line, article):
    """Convert only defined units, never treat arbitrary packs as kilograms."""
    raw_unit=str(line.get('unit') or '').strip()
    unit = {'طن':'tonne','قنطار':'quintal','قناطر':'quintaux','كيلو':'kg','كلغ':'kg','كيس':'sac','اكياس':'sac'}.get(raw_unit,normalized(raw_unit))
    if unit in ('vys','vgs','vge','voy','voiage','voiages','voyge'):unit='voyage'
    qty = line.get('quantity')
    if qty is None:
        if unit in ('voyage','voyages','vge','vgs','vys','voy'):
            qty=1
        else:
            return
    code = article['ITMREF_0'].strip()
    sales = article['SAU_0'].strip().upper()
    if unit=='ss' and code.startswith('CPJ') and sales=='SAC':unit='sac'
    if unit in ('plt','plts'):unit='palette'
    # A trip is a logistics unit, not a fixed cement package. A global historical
    # 560/540 rule cannot prove the load of this request. Source confirmation only.
    if unit in ('voyage','voyages','vge','vgs','vys','voy') and code in ('CPJ35','CPJ45','CPJ35P'):
        factor=line.get('confirmed_sacks_per_trip')
        if factor is None:
            line['requires_pack_confirmation']=True
            line['conversion_rule']=f'{qty} voyage(s) {code} : chargement à confirmer (540 ou 560 sacs, ou quantité explicite)'
            return
        factor=Decimal(str(factor))
        if not factor.is_finite() or factor<=0:raise ValueError('Invalid confirmed load')
        line.update(quantity=float(Decimal(str(qty))*factor),unit=sales,
                    conversion_rule=f'{qty} voyage(s) × {factor} sacs explicitement confirmés',requires_pack_confirmation=False)
        return
    import learning_memory
    for rule in learning_memory.policy('verified_unit_equivalences',[]):
        if rule.get('article')==code and normalized(rule.get('from',''))==unit and rule.get('to')==sales:
            factor=Decimal(str(rule['factor']))
            if qty is not None and factor.is_finite() and factor>0:
                line['quantity']=float(Decimal(str(qty))*factor)
                line['unit']=sales
                line['conversion_rule']='Equivalence article/unité vérifiée dans la mémoire'
                return
    if not unit or unit in ('un','u','unite','unites','piece','pieces'):
        line['unit']=sales
        line['unit_source']='Unité de vente de la fiche article Sage'
        return
    multiplier = None
    if unit in ('t','tn','ton','tonne','tonnes','tons'):
        if sales == 'KG': multiplier=Decimal(1000)
        elif sales == 'SAC' and code in ('CPJ35','CPJ45','CPJ35P'): multiplier=Decimal(20)
    elif unit in ('quintal','quintaux','q','qtx') and sales == 'KG': multiplier=Decimal(100)
    # These package sizes are observed independently in the reviewed OB orders.
    elif unit in ('palette','palettes'):
        if code in ('CPJ35','CPJ45','CPJ35P'): multiplier=Decimal(30)
        elif code=='BQ7': multiplier=Decimal(335)
    elif unit in ('voyage','voyages','vge') and code.endswith('_30M3') and sales=='30M':
        # This Sage item itself is sold as one load of 30 cubic metres.
        line['unit']=sales
    elif unit in ('fardou','fardeau','fardeaux') and code in ('RABT6','RAB8','RAB10','RAB12','RAB14','RAB16'): multiplier=Decimal(2000)
    elif unit in ('barre','barres') and code=='RAB10': multiplier=Decimal('7.69')
    if multiplier is not None:
        line['quantity']=float(Decimal(str(qty))*multiplier)
        line['unit']=sales
        line['conversion_rule']=f'{qty} {unit} -> {line["quantity"]} {sales}'
        line['requires_pack_confirmation']=unit in ('palette','palettes','voyage','voyages','vge','fardou','fardeau','fardeaux','barre','barres')
    elif unit in ('sac','sacs') and sales=='SAC' or unit in ('kg','kgs','kilo','kilos') and sales=='KG' or unit in ('rlx','rouleau','rouleaux') and sales=='RLX':
        line['unit']=sales
    elif unit in ('un','u','unite','unites','piece','pieces') and sales=='UN':
        line['unit']=sales
