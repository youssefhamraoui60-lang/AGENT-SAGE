"""Read-only Telegram follow-ups. This module never calls order creation."""
import re
import asyncio
import learning_memory
from prepare import lookup
from creation import run_script


def is_followup(text):
    caption=text.split('DOCUMENT JOINT')[0]
    caption=re.sub(r'(?i)(?:sans|[eé]viter|pas\s+de)\s+retard','',caption)
    return bool(re.search(r'(?i)relanc|r[eé]clam|retard.{0,30}livraison|livraison.{0,20}retard|(?:[eé]tat|statut).{0,35}(?:commande|livraison)|o[uù]\s+en\s+est|quand.{0,25}livr',caption))


def format_status(rows, article=''):
    if not rows:
        return 'TEST : aucune commande correspondante retrouvée. Précise le numéro de commande ou la date de la demande.'
    orders={}
    for row in rows:
        orders.setdefault(row['SOHNUM_0'].strip(),set())
        if row.get('SDHNUM_0'):
            orders[row['SOHNUM_0'].strip()].add(row['SDHNUM_0'].strip())
    prefix='TEST'+(' '+article if article else '')+' : '
    parts=[]
    for number,docs in orders.items():
        part=number+' — '+('bon '+', '.join(sorted(docs))+' enregistré' if docs else 'aucun BL/BCH enregistré')
        if len(prefix+' ; '.join(parts+[part]))>170:
            parts.append('autres bons/commandes : préciser le numéro')
            break
        parts.append(part)
    reply=prefix+' ; '.join(parts)
    if len(orders)>1:
        reply+=' (dernières commandes).'
    elif any(orders.values()):
        reply+='. Livraison physique à confirmer.'
    return reply[:200]


async def answer(text):
    if re.search(r'(?i)cr[eé]er|nouvelle\s+commande',text):
        return 'Relance et création dans le même message : sépare les demandes. Aucune commande créée.'
    numbers=set(re.findall(r'\b20\d{2}ARC\d+\b',text,re.I))
    if len(numbers)>1:
        return 'Plusieurs commandes citées : précise celle dont tu souhaites connaître l’état.'
    articles=set('CPJ'+n for n in re.findall(r'(?i)\b(?:cpj|ciment)\s*(35|45)\b',text))
    if len(articles)>1:
        return 'Précise la commande concernée pour distinguer les livraisons CPJ35 et CPJ45.'
    article=next(iter(articles),'CPJ' if re.search(r'(?i)\b(?:cpj|ciment)\b',text) else '')
    try:
        if numbers:
            request={'kind':'delivery_status','code':next(iter(numbers)).upper(),'article':article}
        else:
            contact=re.search(r'(?im)^\s*Contact\s*:\s*(.+)$',text)
            reps=await asyncio.to_thread(lookup,'representative',contact[1].strip()) if contact else []
            representative=reps[0]['REPNUM_0'].strip() if len(reps)==1 else None
            body='\n'.join(line for line in text.splitlines() if not re.match(r'(?i)^\s*(?:Contact|Num[eé]ro)\s*:',line)).strip()
            client=re.split(r'(?i)\b(?:r[eé]clame|relance|signale|demande|retard)\b',body,maxsplit=1)[0].strip(' ,:')
            if not client:
                # "Relance pour CPJ Small palace" puts the customer after the intent.
                tail=re.sub(r'(?is)^\s*relance\s+(?:pour\s+)?(?:cpj\s*(?:35|45)?\s*)?', '',body)
                client=re.sub(r'[^\w\s.-]','',tail).strip(' .-')
                if client==body.strip(' .-'):
                    client=''
            if not client:
                return 'Relance reçue. Précise le client ou le numéro de commande pour vérifier le BL/BCH.'
            rules=await asyncio.to_thread(learning_memory.approved_rules)
            token=learning_memory.ACTIVE.set(tuple(rules))
            try:
                clients=await asyncio.to_thread(lookup,'client',client,representative=representative)
            finally:
                learning_memory.ACTIVE.reset(token)
            if len(clients)!=1:
                return 'Relance reçue. Client ambigu ou introuvable : précise son code Sage. Aucune commande créée.'
            request={'kind':'delivery_status','code':'recent','client':clients[0]['BPCNUM_0'].strip(),'article':article}
        result=await asyncio.to_thread(run_script,'sob-read.ps1',request)
        if not result.get('ok'):
            return 'Relance reçue. Lecture de l’état Sage indisponible ; aucune nouvelle commande créée.'
        return format_status(result['rows'],article)
    except Exception:
        return 'Relance reçue. Vérification Sage indisponible pour le moment ; aucune nouvelle commande créée.'
