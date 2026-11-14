"""One scoped historical request through the unchanged TEST SOB engine."""
import asyncio,json,re,sys
from datetime import date
from pathlib import Path
import creation
import telegram_order
import learning_memory
from telegram_routing import RULE,validate_policy


def normalized(text):return re.sub(r'\s+',' ',text).strip().casefold()


def prior_receipts(request):
    prefix='telegram:'+str(request['source'])+':'
    ids=set(request['ids']);created=[];uncertain=[];text_matches=[]
    content=normalized('\n\n'.join(m['content'] for m in request['history']))
    with creation.connection() as conn:
        rows=conn.execute("SELECT owner,status,number,payload FROM reviews WHERE status IN ('created','pending','uncertain')").fetchall()
        for row in rows:
            parts=row['owner'].split(':')
            linked=row['owner'].startswith(prefix) and parts[-1].isdigit() and int(parts[-1]) in ids
            if linked:
                (created if row['status']=='created' else uncertain).append(dict(row));continue
            if row['status']!='created' or json.loads(row['payload']).get('order_date')!=request['day']:continue
            history=conn.execute('SELECT history FROM sob_preparations WHERE owner=?',(row['owner'],)).fetchone()
            if not history:continue
            messages=[m['content'] for m in json.loads(history['history']) if m.get('role')=='user']
            if content and (content in {normalized(m) for m in messages} or content==normalized('\n\n'.join(messages))):text_matches.append(dict(row))
    return created,uncertain,text_matches


async def process(request):
    date.fromisoformat(request['day'])
    route=next(r['payload'] for r in learning_memory.approved_rules() if r['kind']=='policy' and r['rule_key']==RULE)
    validate_policy(route)
    if request['source']!=route['source_chat_id']:raise ValueError('Replay source does not match authorized route')
    scope=next(r['payload'] for r in learning_memory.approved_rules() if r['kind']=='policy' and r['rule_key']=='telegram_replay_'+request['day'])
    if scope['folder']!='TEST' or max(request['ids'])>scope['max_message_id']:raise ValueError('Replay exceeds authorized snapshot')
    created,uncertain,text_matches=prior_receipts(request)
    if created:
        numbers=sorted({r['number'] for r in created})
        return {'status':'already_created','numbers':numbers,'reply':'Commande déjà créée dans TEST : '+', '.join(numbers)+'. Aucun doublon créé.'}
    if uncertain:
        return {'status':'requires_readback','reply':'Une création est en cours ou incertaine pour ces messages. Vérifier le reçu TEST avant toute reprise.'}
    if text_matches:
        numbers=sorted({r['number'] for r in text_matches})
        return {'status':'potential_duplicate','numbers':numbers,'reply':'Demande identique à une demande déjà créée dans TEST : '+', '.join(numbers)+'. Vérifier avant une seconde création.'}
    owner='telegram:'+str(request['source'])+':'+str(request['sender'])+':'+str(request['ids'][0])
    try:reply=await telegram_order.handle(request['history'],owner)
    except creation.CreationError as exc:reply=str(exc)
    except Exception as exc:return {'status':'requires_review','reply':'Analyse indisponible ('+type(exc).__name__+'). Demande conservée pour vérification, aucune nouvelle tentative automatique.'}
    with creation.connection() as conn:
        receipt=conn.execute('SELECT status,number,payload FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 1',(owner,)).fetchone()
    result={'status':'needs_data','reply':reply,'owner':owner}
    if receipt and receipt['status']=='created':
        result.update(status='created',number=receipt['number'],reference=json.loads(receipt['payload'])['reference'])
    elif receipt and receipt['status'] in ('pending','uncertain'):result['status']='requires_readback'
    elif reply.startswith('Bon ') and 'déjà créé dans TEST' in reply:result['status']='already_created'
    elif 'Test sans création' in reply:result['status']='preparation_only'
    return result


if __name__=='__main__':
    if '--authorize' in sys.argv:
        day=sys.argv[sys.argv.index('--authorize')+1];maximum=int(sys.argv[sys.argv.index('--max-id')+1]);date.fromisoformat(day)
        learning_memory.save('policy','telegram_replay_'+day,{'day':day,'source_chat_id':-1004375687420,'response_chat_id':-5586539927,'max_message_id':maximum,'folder':'TEST'},actor='operator',source='Instruction utilisateur : reprendre les demandes du 11 novembre 2026 en évitant les doublons ; créations TEST et réponses dans COMMANDES SOB.',approved=True)
        print(json.dumps({'authorized_day':day,'maximum':maximum,'folder':'TEST'}))
    else:
        print(json.dumps(asyncio.run(process(json.load(sys.stdin))),ensure_ascii=False))
