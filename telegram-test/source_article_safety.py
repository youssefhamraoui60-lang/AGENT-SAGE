"""Reject substitutions of explicit caption articles before any SOB write."""
import re
from understanding import shorthand


def explicit_caption_articles(text, canonical):
    caption=shorthand(re.split(r'DOCUMENT JOINT',text,maxsplit=1,flags=re.I)[0])
    found=set()
    for line in caption.splitlines():
        match=re.match(r'(?i)^\s*\d+(?:[.,]\d+)?\s*(?:kgs?|tonnes?|t|sacs?)\s+(?:de\s+)?((?:(?:rab|fer)\s*t?|cpj|ciment|cima|sima)\s*0?(?:35|45|55|6|8|10|12|14|16|20|25|32))\b',line)
        if match:
            code=canonical(match[1])
            if re.fullmatch(r'(?:RAB(?:T6|8|10|12|14|16|20|25|32)|CPJ(?:35|45|55_PP|35P))',code):found.add(code)
    return found


def missing_explicit_articles(text,resolved,canonical):
    required=explicit_caption_articles(text,canonical)
    actual={re.sub(r'_F\d+$','',line['article']) for line in resolved}
    return sorted(required-actual)


def ground_single_explicit_steel(draft,text,canonical):
    required={code for code in explicit_caption_articles(text,canonical) if code.startswith('RAB')}
    generic=[line for line in draft.get('lines',[]) if re.sub(r'[^a-z]','',str(line.get('article') or '').casefold()) in ('rab','fer','acier','ferabeton','acierha')]
    if len(required)==1 and len(generic)==1:
        generic[0]['article']=next(iter(required))
        return True
    return False


def ground_explicit_caption_quantities(draft,text,canonical):
    """A single unambiguous written quantity wins over model unit arithmetic."""
    caption=shorthand(re.split(r'DOCUMENT JOINT',text,maxsplit=1,flags=re.I)[0])
    facts={}
    for raw in caption.splitlines():
        m=re.match(r'(?i)^\s*(\d+(?:[.,]\d+)?)\s*(kgs?|tonnes?|t|sacs?|quintaux)\s+(?:de\s+)?((?:(?:rab|fer)\s*t?|cpj|ciment|cima|sima)\s*0?(?:35|45|55|6|8|10|12|14|16|20|25|32))\b',raw)
        if m:facts.setdefault(canonical(m[3]),[]).append((float(m[1].replace(',','.')),m[2]))
    for code,values in facts.items():
        matched=[r for r in draft.get('lines',[]) if canonical(r.get('article') or '')==code]
        if len(values)==1 and len(matched)==1:
            matched[0].update(quantity=values[0][0],unit=values[0][1])


def brick_dimension_supported(text,code):
    code=re.sub(r'_F\d+$','',code)
    m=re.match(r'^BQ(7|10|15)',code)
    if not m:return True
    clean=re.sub(r'\s+',' ',text.replace('|',' '))
    if re.search(r'(?i)(?<!\w)'+re.escape(code)+r'(?!\w)',clean):return True
    return bool(re.search(r'(?i)\b(?:briques?|br)\s*(?:[:=]\s*)?(?:rouges?\s*)?(?:[dø]\s*)?0?'+m[1]+r'(?!\d)',clean))
