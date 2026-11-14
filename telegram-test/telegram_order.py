"""Telegram direct creation, authorized by the user; web validation is unchanged."""
import asyncio
import json
import sys
import re
from contextlib import closing
from prepare import prepare
import creation
import learning_memory
from prepare import lookup


async def handle(history, owner):
    text=next((m['content'] for m in reversed(history) if m['role']=='user'),'')
    from message_intent import administrative_reply
    administrative=administrative_reply(text)
    if administrative:return administrative
    from delivery_status import is_followup, answer
    if is_followup(text):
        return await answer(text)
    from order_amendments import handle as amendment
    amendment_reply=await amendment(history,owner)
    if amendment_reply:
        return amendment_reply
    from telegram_batch import document_references
    if len(document_references(text))>1:
        return 'Plusieurs bons de commande distincts reçus ensemble. Ils doivent être traités séparément ; aucune création pour ce lot.'
    from document_receipts import known_receipt
    receipt=await known_receipt(text) if 'DOCUMENT JOINT' in text else None
    if receipt:
        return receipt
    from telegram_batch import contact_name
    rules=await asyncio.to_thread(learning_memory.approved_rules)
    excluded_owners=next((r['payload'].get('value',[]) for r in rules if r['kind']=='policy' and r['rule_key']=='creation_excluded_owners'),[])
    if owner in excluded_owners:
        return 'Création suspendue pour cette demande, selon ta dernière instruction. Vérifier le test déjà existant dans Sage.'
    excluded=next((r['payload'].get('value',[]) for r in rules if r['kind']=='policy' and r['rule_key']=='telegram_creation_excluded_contacts'),[])
    if any(contact_name(m['content']) in excluded for m in history if m['role']=='user'):
        return 'Commandes Bouchaib : création suspendue à ta demande.'
    if any(marker in text for marker in ('Document non lu :', 'Document conservé, lecture indisponible', 'Attention : texte tronqué')):
        if re.search(r'(?i)\b\d+(?:[.,]\d+)?\s*sacs?\s*(?:cpj\s*)?(?:35|45|55)\b',text):
            import drafts
            await asyncio.to_thread(drafts.save,owner,{'status':'attachment_requires_review'},history)
            return 'Texte de commande conservé, mais pièce jointe non lue. Précise si elle complète cette commande ou une autre ; aucune création pour éviter un oubli.'
        return 'Manque : contenu lisible et complet du document. Renvoie le PDF ou une image nette ; aucune commande créée.'
    correction=learning_memory.parse_correction(text)
    if correction:
        alias,code=correction
        # Validate the target as an existing Sage code, not a model invention.
        rows=await asyncio.to_thread(lookup,'article',code)
        if not any(r['ITMREF_0'].strip()==code for r in rows):
            return 'Correction non appliquée : code article Sage introuvable '+code+'.'
        await asyncio.to_thread(learning_memory.save,'article_alias',alias,{'code':code},
                                actor=owner,source='Correction explicite Telegram',approved=True)
        return 'Correction mémorisée dans la base : '+alias+' → '+code+'.'
    if re.match(r'(?i)^\s*(?:/?corrig(?:e|er)|correction|remplace)\b',text):
        await asyncio.to_thread(learning_memory.save,'interpretation','proposal_'+__import__('hashlib').sha256(text.encode()).hexdigest()[:20],
                                {'text':text[:1500]},actor=owner,source='Correction Telegram à structurer',approved=False)
        return 'Correction enregistrée dans la base, à préciser. Exemple : corriger article pointe 6 = PF-TP16X20.'
    # Owner includes group, sender and message id. A replay returns the same receipt.
    with closing(creation.connection()) as db:
        existing = db.execute('SELECT id FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 1', (owner,)).fetchone()
    if existing:
        with closing(creation.connection()) as db:
            row=db.execute('SELECT status,number FROM reviews WHERE id=?',(existing['id'],)).fetchone()
        if row['status']=='created':
            return 'Commande ' + row['number'] + ' déjà créée dans Sage TEST.'
        if row['status'] in ('pending', 'uncertain'):
            receipt = await asyncio.to_thread(creation.confirm, owner, existing['id'])
            return 'Commande ' + receipt['number'] + ' créée dans Sage TEST.'
        await asyncio.to_thread(creation.invalidate, owner)
    import drafts
    # Keep the request durable even when the AI provider is unavailable.
    await asyncio.to_thread(drafts.save, owner, {'status':'waiting_for_analysis'}, history)
    from telegram_batch import customer_codes
    all_source='\n'.join(m['content'] for m in history if m['role']=='user')
    if len(customer_codes(all_source))>1:
        return 'Plusieurs clients détectés. Les demandes doivent être séparées ; aucune commande créée pour ce lot.'
    from telegram_batch import named_customer
    source_parts=re.split(r'(?im)(?=^\s*Contact\s*:)',text)
    names={name for part in source_parts if (name:=named_customer(part))}
    if len(names)>1:
        return 'Plusieurs demandes avec des clients différents détectées. Aucune création pour ce lot ; traiter chaque client séparément.'
    modification=re.search(r'(?i)modification\s+au\s+niveau\s+de\s+cette\s+commande',text)
    if modification and not re.search(r'(?i)\b\d+(?:[.,]\d+)?\s*(?:sacs?|tonnes?|kg|cpj|rab)\b',text[:modification.start()]):
        await asyncio.to_thread(drafts.save,owner,{'status':'modification_requires_review'},history)
        return 'Modification reçue. Indique le numéro de commande Sage à corriger ; aucune nouvelle commande créée.'
    try:
        details = await prepare(history, details=True)
    except Exception:
        return 'Service IA indisponible. Demande conservée pour reprise ; aucune création déclenchée pour ce message.'
    await asyncio.to_thread(drafts.save,owner,details,history)
    if details.get('lines') and all(line['article']=='MANTD' for line in details['lines']) and not any(field.startswith('article ') for field in details.get('missing_fields',[])) and re.search(r'(?i)\b(?:rab\s*\d+|cpj\s*\d+|ciments?\s*(?:35|45)|briques?\b|power\s+(?:fix|colle))',all_source):
        return 'Des marchandises du message ne sont pas reprises. Préciser le client de chaque demande ; aucune commande créée.'
    if details.get('intent') == 'other':
        if 'DOCUMENT JOINT' in text:
            fields=list(dict.fromkeys(details.get('missing_fields',[])))
            return 'Document reçu, lecture incomplète : '+(', '.join(fields) if fields else 'type de demande à préciser')+'. Aucune commande créée.'
        return 'Indique le client, les articles, les quantités, les prix TTC et la date de livraison.'
    missing = [field for field in details.get('missing_fields', []) if not field.startswith('prix TTC ')]
    empty_prices = [line['article'] for line in details['lines'] if line['price'] is None]
    if not details['client']:
        missing.append('client Sage')
    if not details['lines']:
        missing.append('article et quantité')
    for line in details['lines']:
        if line['quantity'] is None:
            missing.append('quantité ' + line['article'])
    if not details['delivery']:
        missing.append('date de livraison')
    trip_codes=[field.removeprefix('tonnage du voyage ') for field in missing if field.startswith('tonnage du voyage ')]
    if trip_codes:
        other=[field for field in missing if not field.startswith('tonnage du voyage ') and field not in {prefix+code for code in trip_codes for prefix in ('unité ','quantité ')}]
        return ('Voyage '+', '.join(dict.fromkeys(trip_codes))+' reconnu. Précise les sacs par voyage (540/560/autre) ou le total de sacs.'
                +(' Autres manques : '+', '.join(dict.fromkeys(other))+'.' if other else '')+' Aucune commande créée.')
    if details['missing'] and not missing and not empty_prices:
        missing.append('article, client ou unité à préciser')
    if missing:
        return 'Manque : ' + ', '.join(dict.fromkeys(missing)) + '.'
    if empty_prices:
        # Keep NULL prices as a draft. Never convert an unknown price to zero
        # or report a successful Sage creation without an actual receipt.
        with closing(creation.connection()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS telegram_drafts(owner TEXT PRIMARY KEY, details TEXT NOT NULL)')
            db.execute('INSERT OR REPLACE INTO telegram_drafts(owner,details) VALUES(?,?)',
                       (owner, json.dumps(details, ensure_ascii=False)))
        return 'Brouillon enregistré. Derniers prix vérifiés ; prix laissés vides : ' + ', '.join(empty_prices) + '. Aucune commande créée.'
    # User explicitly authorized direct TEST creation for Telegram. Web keeps
    # its validation. Shared SQL checks and durable receipts remain mandatory.
    review = await asyncio.to_thread(creation.review, owner, details)
    preparation_only=next((r['payload'].get('value',[]) for r in rules
                           if r['kind']=='policy' and r['rule_key']=='preparation_only_document_references'),[])
    if set(document_references(text)) & set(preparation_only):
        return 'Bon '+', '.join(sorted(document_references(text)))+' préparé et vérifié dans TEST. Test sans création, selon ta demande.'
    receipt = await asyncio.to_thread(creation.confirm, owner, review['id'], human_validated=True)
    return 'Commande ' + receipt['number'] + ' créée dans Sage TEST.'


def short(text):
    prefix = '🤖 SOB\n'
    text = ' '.join(str(text).split())
    return prefix + (text if len(prefix + text) <= 200 else text[:200 - len(prefix) - 1] + '…')


if __name__ == '__main__':
    try:
        reply = asyncio.run(handle(json.load(sys.stdin), sys.argv[1]))
    except creation.CreationError as exc:
        reply = str(exc)
    except Exception:
        reply = 'Traitement indisponible. Vérifier le reçu avant toute nouvelle demande de création.'
    print(json.dumps({'reply': short(reply)}, ensure_ascii=False))
