"""Per-draft site additions and explicit coreferences, never cross-draft guesses."""
import re
from app.services.chat_turns import norm

def known(article):
    return list(dict.fromkeys([*(article.get('declared_site_codes') or []),*(article.get('requested_sites') or []),*([article['site']] if article.get('site') else [])]))

def both(text):return bool(re.search(r'\b(?:les?\s+deux|les?\s+2|tous\s+les\s+sites)\b',norm(text))) and 'site' in norm(text)

def additive(text):return bool(re.search(r'\b(?:ajout\w*|rajout\w*|aussi|egalement)\b',norm(text))) and not re.search(r'\b(?:remplac\w*|uniquement|seulement|retir\w*)\b',norm(text))

def merge(article,values,text):
    prior=known(article)
    incoming=values.get('requested_sites') or ([values['site']] if values.get('site') else [])
    if both(text) and len(prior)==2:incoming=prior
    elif incoming and additive(text):incoming=list(dict.fromkeys([*(article.get('requested_sites') or ([article['site']] if article.get('site') else [])),*incoming]))
    if incoming:
        values['requested_sites']=incoming;values['site']=incoming[0]
        article['declared_site_codes']=list(dict.fromkeys([*prior,*incoming]))
