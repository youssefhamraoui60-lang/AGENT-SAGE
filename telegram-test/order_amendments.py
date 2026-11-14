"""Recognize explicit late transport supplements without duplicating orders.

Requests are durable; this module never claims an UPDATE it has not executed.
"""
import asyncio
import json
import re
import time
from contextlib import closing

import creation
import drafts
import learning_memory
from telegram_batch import contact_name, document_references
from understanding import normalized


def transport_supplement(text):
    parts=re.split(r'(?im)(?=^\s*Contact\s*:)',text)
    if len(parts)>2 and 'DOCUMENT JOINT' in ''.join(parts[:-1]):
        contacts={contact_name(s) for s in parts if contact_name(s)}
        if len(contacts)!=1:
            return None
        text=parts[-1]
    caption=text.split('DOCUMENT JOINT')[0]
    lines=[s.strip() for s in caption.splitlines() if s.strip()
           and not re.match(r'(?i)^(?:Contact|Num[eé]ro)\s*:',s)]
    lines=[s for s in lines if not re.fullmatch(r'2026ARC\d+',s,re.I)]
    if len(lines)!=1:
        return None
    match=re.fullmatch(r'(?i)(?:\+|ajouter\s+|plus\s+)(\d+(?:[.,]\d{1,2})?)\s*(?:dh|mad)\s+(?:de\s+)?(?:frais\s+de\s+)?transport[.!]?',lines[0])
    value=float(match[1].replace(',','.')) if match else None
    return value if value is not None and value>0 else None


async def handle(history,owner):
    current=next((m['content'] for m in reversed(history) if m['role']=='user'),'')
    amount=transport_supplement(current)
    if amount is None:
        return None
    contact=contact_name(current)
    sources=[m['content'] for m in history if m['role']=='user'
             and contact and contact_name(m['content'])==contact]
    documents=[s for s in sources if 'DOCUMENT JOINT' in s]
    document=documents[-1] if documents else ''
    refs=document_references(document)
    numbers=set(re.findall(r'\b2026ARC\d+\b',current,re.I))
    target=None;client=None;reference=None
    if len(numbers)==1:
        target=next(iter(numbers)).upper()
    elif len(refs)==1:
        reference=next(iter(refs))
        rules=await asyncio.to_thread(learning_memory.approved_rules)
        candidates=[r['payload'] for r in rules if r['kind']=='interpretation'
                    and r['rule_key'].startswith('document_receipt_')
                    and r['payload'].get('reference')==reference
                    and r['payload'].get('ice','__missing__') in normalized(document)
                    and str(r['payload'].get('year')) in document]
        if len(candidates)==1:
            target=candidates[0]['order'];client=candidates[0]['client']
    # After a completed creation, connect.py clears conversational history.
    # Find only this account/group/contact's most recent successful request.
    elif contact:
        scope=owner.rsplit(':',1)[0]+':'
        with closing(creation.connection()) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='sob_preparations'").fetchone()
            rows=db.execute("SELECT R.number,P.history,P.updated FROM reviews R JOIN sob_preparations P ON P.owner=R.owner WHERE R.status='created' AND substr(R.owner,1,?)=? AND P.updated>=? ORDER BY P.updated DESC LIMIT 30",(len(scope),scope,time.time()-7200)).fetchall() if exists else []
        recent_targets=set()
        for row in rows:
            messages=json.loads(row['history'])
            last=next((m['content'] for m in reversed(messages) if m['role']=='user'),'')
            if contact_name(last)==contact:
                recent_targets.add(row['number'])
        if len(recent_targets)==1:
            target=recent_targets.pop()
    details={'status':'amendment_requires_review','operation':'add_line','article':'MANTD',
             'quantity':1,'price':amount,'order':target,'document_reference':reference}
    if not target:
        reply=f'Complément transport {amount:g} DH reçu. Indique le numéro de commande TEST à compléter ; aucune nouvelle commande créée.'
    else:
        result=await asyncio.to_thread(creation.run_script,'sob-read.ps1',{'kind':'order_lines','code':target})
        rows=result.get('rows',[]) if result.get('ok') else []
        if not rows or (client and any(r['BPCORD_0'].strip()!=client for r in rows)):
            details['status']='amendment_receipt_unverified'
            reply=f'Complément +{amount:g} DH conservé. Commande {target} non retrouvée ou reçu non vérifié dans TEST : indique son numéro actuel. Aucun ajout effectué.'
        else:
            details['client']=rows[0]['BPCORD_0'].strip()
            reply=f'Complément pour {target} : ajouter MANTD, quantité 1, +{amount:g} DH TTC. Modification conservée, non appliquée : le compte SQL ne permet pas les mises à jour.'
    await asyncio.to_thread(drafts.save,owner,details,history)
    return reply
