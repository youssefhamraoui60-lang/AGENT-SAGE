"""Reconcile verified historical PDF references before another creation."""
import asyncio
import learning_memory
from creation import run_script
from telegram_batch import document_references
from understanding import normalized


async def known_receipt(text):
    refs=document_references(text)
    if len(refs)!=1 or 'DOCUMENT JOINT' not in text:
        return None
    rules=await asyncio.to_thread(learning_memory.approved_rules)
    for rule in rules:
        if rule['kind']!='interpretation' or not rule['rule_key'].startswith('document_receipt_'):
            continue
        data=rule['payload']
        if data.get('reference') not in refs or data.get('ice','__missing__') not in normalized(text) or str(data.get('year')) not in text:
            continue
        result=await asyncio.to_thread(run_script,'sob-read.ps1',{'kind':'order_lines','code':data['order']})
        rows=result.get('rows',[]) if result.get('ok') else []
        if not rows or any(r['BPCORD_0'].strip()!=data['client'] for r in rows):
            return 'Bon '+data['reference']+' déjà rapproché ; reçu Sage à vérifier avant toute nouvelle création.'
        return 'Bon '+data['reference']+' déjà créé dans TEST : '+data['order']+'. Aucun doublon créé ; toute modification doit être vérifiée.'
    return None
