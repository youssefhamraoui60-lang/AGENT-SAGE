"""Ground cement trips in source text; never guess a truck load from history."""
import re
from decimal import Decimal
from understanding import shorthand,normalized

def apply(draft,text,canonical):
    caption=re.split(r'DOCUMENT JOINT[^\n]*\n',text,maxsplit=1,flags=re.I)[0]
    source=shorthand(caption)
    trips={}
    for m in re.finditer(r'(?i)\b(\d+(?:[.,]\d+)?)\s+voyage\s+CPJ(35|45)\b',source):
        code='CPJ'+m[2];trips.setdefault(code,[]).append(Decimal(m[1].replace(',','.')))
    if not trips:return
    for code,quantities in trips.items():
        # Repeated/corrected lines are not summed without an explicit link.
        candidates=[l for l in draft.get('lines',[]) if canonical(l.get('article') or '')==code]
        if len(quantities)!=1 or len(candidates)>1:
            for line in candidates:
                line.update(quantity=None,unit='voyage')
                line.pop('confirmed_sacks_per_trip',None)
            continue
        count=quantities[0]
        if not candidates:
            line={'article':code,'quantity':float(count),'unit':'voyage','price':None,'price_unit':None}
            draft['lines'].append(line)
        else:line=candidates[0]
        line.update(article=code,quantity=float(count),unit='voyage')
        # Require an unambiguous explicit loading statement, not a naked 560.
        factors={Decimal(m.replace(',','.')) for m in re.findall(r'(?i)\b(\d+(?:[.,]\d+)?)\s*sacs?\s*(?:par|/|pour\s+un)\s*(?:voyage|vys|vgs|vge|voy)\b',caption)}
        totals={Decimal(m.replace(',','.')) for m in re.findall(r'(?i)\b(?:total|soit)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*sacs?\b',caption)}
        if len(trips)!=1 or len(factors)>1 or len(totals)>1:continue
        factor=next(iter(factors)) if factors else None
        total=next(iter(totals)) if totals else None
        if factor is None and total is not None:factor=total/count
        if factor is not None and (total is None or total==factor*count):
            line['confirmed_sacks_per_trip']=float(factor)
        else:line.pop('confirmed_sacks_per_trip',None)
