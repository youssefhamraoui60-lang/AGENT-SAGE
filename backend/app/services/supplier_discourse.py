"""Separate task/language clarification from literal supplier identity."""
import re
from app.services.chat_turns import norm,SUPPLIER_WORD

OFF_TOPIC_REPLY='Désolé, cette conversation est réservée aux fournisseurs. Indiquez les informations du fournisseur à préparer.'

def off_topic(text):
    return bool(re.fullmatch(r"(?:(?:bonjour|salut|slt)[, ]+)?(?:je veux|je voudrais|j['’]ai envie de|bghit)\s+(?:manger|dormir|cuisiner|jouer)(?:\s+[^\n]{0,100})?[.!?\s]*",norm(text)))

def explicit_name(text):
    n=norm(text).strip(' .!')
    match=re.fullmatch(r"(?:(?:non|correction|corrige|corriger|rectifie|rectifier)[,: ]+)?(?:le\s+)?nom(?:\s+(?:de|du)\s+(?:(?:le|mon|notre)\s+)?"+SUPPLIER_WORD+r"s?)?\s*(?:est\s*[:=]?|c['’]est\s*[:=]?|:|=)\s*(.+)",n)
    if not match:
        match=re.fullmatch(r"(?:(?:non|correction)[,: ]+)?(?:(?:le|ce|mon|notre|un)\s+)?"+SUPPLIER_WORD+r"\s+(?:s['’]appelle|se nomme|est nomme|a pour nom)\s+(.+)",n)
    if not match:return None
    if re.search(r'\b(?:ice|if|rc|telephone|tel|ville|adresse|paiement|devise|articles?)\s*(?::|=|\d)',match[1]):return None
    return text.strip()[match.start(1):match.end(1)].strip(' .!')

def language_clarification(text):
    n=norm(text).strip(' .!')
    if explicit_name(text):return False
    if re.search(r'\b(?:ice|if|rc|adresse|telephone|nom)\s*[:=]',n):return False
    if re.search(r'\b(?:creer?|ajouter?)\b',n):
        supplier=re.search(r'\b'+SUPPLIER_WORD+r's?\b\s*(.*)',n)
        if supplier and re.sub(r'\b(?:mais|en|on|darija|arabe|francais|la|le)\b|[,.;: ]','',supplier[1]):return False
    language=r'(?:darija|darij[a]?|arabe|francais)'
    # A language remark is not a company name; explicit names remain literal.
    return bool(re.search(r'\b'+language+r'\b',n) and (
        re.search(r'\b(?:parle|parler|dis|dire|dit|explique|en|on)\s+(?:la\s+)?'+language+r'\b',n)
        or re.search(r'\bpas\s+(?:le\s+)?nom\b',n)))

def bare_request(text):
    n=norm(text).strip(' .!?')
    return bool(re.fullmatch(r'.*\b(?:creer?|ajouter?|prepare|preparer|zid|nzid)\s+(?:(?:un|le|une|la|nouveau|nouvelle|fiche|wahed|wahad|wahade|wahd)\s+)*'+SUPPLIER_WORD+r's?',n))

def mistaken_language_name(value):
    return bool(re.fullmatch(r'(?:(?:mais|en|on|le|la|pas|sample)\s+)*(?:darija|arabe|francais)',norm(value or '').strip(' .!')))
