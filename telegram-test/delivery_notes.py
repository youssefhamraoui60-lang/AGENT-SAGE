"""Lossless conventional address abbreviations for Sage's 100-char field."""
import re

def compact(note):
    value=re.sub(r'\s+',' ',note or '').strip()
    if len(value)<=100:return value
    replacements=[
        (r'^\s*(?:Lieu de livraison|Livraison)\s*(?:[àa]\s*)?:\s*',''),
        (r'^\s*Livraison\s+[àa]\s+',''),
        (r'\bContacts?\s+sur\s+place\s*:\s*',''),
        (r'\bContacts?\s*:\s*',''),
        (r'\bContacter\s+',''),
        (r'\bMerci\s+de\s+(?:nous\s+)?livrer\s+',''),
        (r'\bpr[eé]fecture\s+d[’\x27]arrondissements?\b','Préf.'),
        (r'\bpr[eé]fecture\b','Préf.'),
        (r'\barrondissement\b','Arr.'),(r'\bquartier\b','Q.'),
        (r'\bCasablanca\b','Casa'),(r'\bSidi\b','Sd'),
        (r'\bboulevard\b','Bd'),(r'\bavenue\b','Av.'),
        (r'\b(?:Mr|Monsieur)\s+',''),
    ]
    for pattern,replacement in replacements:value=re.sub(pattern,replacement,value,flags=re.I)
    value=re.sub(r'(?<!\d)(?:0[567](?:[ .-]?\d){8}|\+212[567](?:[ .-]?\d){8})(?!\d)',lambda m:re.sub(r'[ .-]','',m[0]),value)
    value=re.sub(r'\s*([,;/])\s*',r'\1',value)
    value=re.sub(r'\s*:\s*',':',value)
    return re.sub(r'\s+',' ',value).strip()
