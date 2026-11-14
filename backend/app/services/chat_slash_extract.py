"""Strict slash-delimited article declarations; never infer missing segments."""
import re
from app.services.chat_turns import norm

def parse_labelled(message):
    """One complete labelled slash request; reject unknown tails/fields."""
    header=re.fullmatch(r'\s*(?:bonjour[!,\s]+)?(?:merci\s+de\s+)?cr[eé]er\s+(?:ce|cet|un)\s+(?:nouvel|nouveau)\s+article(?:\s+dans\s+sage\s+x3)?\s*:\s*(.+)',message,re.I|re.S)
    if not header:return None
    body=header[1].replace('**','').strip()
    body=re.sub(r'\s*cordialement[.!\s]*$','',body,flags=re.I).strip()
    body=re.sub(r"\s*merci\s+de\s+proposer\s+un\s+code\s+article\s+et\s+de\s+v[eé]rifier\s+qu['’]il\s+n['’]existe\s+pas\s+d[eé]j[aà][.!\s]*$",'',body,flags=re.I).strip()
    parts=[x.strip() for x in body.split('/')]
    if len(parts)!=6:return None
    label,unit=parts[:2]
    if not 0<len(label)<=70 or not re.fullmatch(r'[A-Z0-9_-]{1,3}',unit,re.I):return None
    data={'designation':label,'unite':unit.upper()}
    for part in parts[2:]:
        n=norm(part).strip().rstrip('.')
        if re.fullmatch(r'(?:article\s+)?non\s+gere\s+en\s+stock',n):
            key,value='gestion_stock','1'
        else:
            match=re.fullmatch(r'(categorie|tva|sites?)\s*:\s*(.+)',n)
            if not match:return None
            key={'categorie':'categorie','tva':'taux_tva','site':'site','sites':'site'}[match[1]];value=match[2].strip()
            if key=='categorie':
                if not re.fullmatch(r'[a-z0-9_-]{1,5}',value):return None
                value=value.upper()
            elif key=='taux_tva':
                if not re.fullmatch(r'\d{1,2}(?:[.,]\d+)?\s*%',value):return None
                value=value.rstrip('%').strip().replace(',','.')
            else:
                if not re.fullmatch(r'\d{3}(?:\s*(?:et|,)\s*\d{3})*',value):return None
                sites=re.findall(r'\d{3}',value)
                if len(set(sites))>20:return None
                value=sites[0] # Full declared selection is preserved by apply().
        if key in data:return None
        data[key]=value
    return data if {'categorie','taux_tva','site','gestion_stock'}<=data.keys() else None

def parse(message):
    labelled=parse_labelled(message)
    if labelled:return [labelled]
    body=message.strip()
    header=re.search(r'\barticles?\s*:',body,re.I)
    if header:body=body[header.end():]
    body=re.sub(r'\s*cordialement[.!\s]*$','',body,flags=re.I).strip()
    pattern=re.compile(r'([^/\n]{1,70}?)\s*/\s*(unit[eé]|UN)\s*/\s*([A-Z0-9_-]{1,5})\s*/\s*([^/\n]{1,100}?)\s*/\s*(?:article\s+)?non\s+g[eé]r[eé](?:r|e|s)?(?:\s*/)?',re.I)
    matches=list(pattern.finditer(body))
    if not 1<=len(matches)<=10:return None
    cursor=0;articles=[]
    for match in matches:
        if body[cursor:match.start()].strip():return None
        articles.append({'designation':match[1].strip(),'unite':'UN','categorie':match[3].upper(),'fournisseur_nom':match[4].strip(),'gestion_stock':'1'})
        cursor=match.end()
    if body[cursor:].strip():return None
    return articles
