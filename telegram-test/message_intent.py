"""Bounded administrative messages are not new sales orders."""
import re
from telegram_batch import has_goods_request

def administrative_reply(text):
    if 'DOCUMENT JOINT' in text or has_goods_request(text):return None
    body='\n'.join(s for s in text.splitlines() if not re.match(r'(?i)^\s*(?:Contact|Num[eé]ro)\s*:',s)).strip()
    if re.search(r'(?i)\bactiv(?:er|ation)\b',body):
        return 'Demande d’activation reçue. Précise la référence de la fiche ou de la commande existante ; aucune nouvelle commande créée.'
    if re.search(r'(?i)شيك|ch[eèé]ques?',body) and re.search(r'(?i)يجيب|r[eé]cup[eé]r|ramener|encaisser',body):
        return 'Consigne de récupération des chèques reçue. Précise la commande concernée pour la rattacher ; aucune nouvelle commande créée.'
    if re.fullmatch(r'(?i)(?:merci(?: beaucoup)?|ok|bien re[cç]u|شكرا)[.!\s]*',body):return 'Bien reçu.'
    return None
