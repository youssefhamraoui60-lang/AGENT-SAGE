"""Explicit dated Telegram backfill, shared source journal, TEST engine only."""
import argparse,asyncio,collections,hashlib,json,sqlite3,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from telethon import TelegramClient
from telegram_routing import ROOT,RouteJournal,load_policy,publish


def dump(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8');temporary.replace(path)


def build_request(rows,group,source,day):
    ids=group['ids'];senders={rows[mid]['sender_id'] for mid in ids}
    if len(senders)!=1:raise ValueError('Cannot merge messages from different senders')
    parts=[]
    for mid in ids:
        row=rows[mid];text=row['text']
        if mid in group.get('superseded_document_ids',[]):
            text+='\nDocument initial remplacé par la version explicitement rectifiée jointe à cette même demande.'
        elif row.get('file'):
            decoded=row.get('layout_text','')
            text+=('\nDOCUMENT JOINT :\n'+decoded if len(decoded.strip())>=15 else '\nDocument conservé, lecture indisponible : contenu à préciser.')
        elif row.get('media'):text+='\nDocument non lu : format ou taille non pris en charge.'
        parts.append(text)
    return {'source':source,'sender':next(iter(senders)),'ids':ids,'day':day,'history':[{'role':'user','content':'\n\n'.join(parts)}]}


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);args=parser.parse_args()
    day=datetime.strptime(args.date,'%Y-%m-%d').date()
    out=ROOT/'runtime'/('sob-day-'+day.strftime('%Y%m%d'))
    source_rows=json.loads((out/'messages-reviewed.json').read_text(encoding='utf-8'))
    groups=json.loads((out/'day-plan-reviewed.json').read_text(encoding='utf-8'))
    if any(datetime.fromisoformat(r['date']).astimezone(ZoneInfo('Europe/Paris')).date()!=day for r in source_rows):raise ValueError('Source date mismatch')
    covered=[mid for g in groups for mid in g['ids']]
    if sorted(covered)!=sorted(r['id'] for r in source_rows) or len(covered)!=len(set(covered)):raise ValueError('Source coverage mismatch')
    route=load_policy();journal=RouteJournal();rows={r['id']:r for r in source_rows}
    source_session=ROOT/'runtime/telegram-test/personal.session';session=out/'replay.session'
    with sqlite3.connect(source_session.as_uri()+'?mode=ro',uri=True) as src:
        with sqlite3.connect(session) as dst:src.backup(dst)
    client=TelegramClient(str(session),38572478,'existing-session-only',receive_updates=False)
    results_path=out/'replay-results.json'
    results=json.loads(results_path.read_text(encoding='utf-8')) if results_path.exists() else []
    prior={tuple(r['message_ids']):r for r in results}
    try:
        await client.connect()
        if not await client.is_user_authorized():raise RuntimeError('Telegram session unavailable')
        dialogs=[dialog async for dialog in client.iter_dialogs() if dialog.is_group]
        source=next(g for g in dialogs if g.id==route['source_chat_id']);destination=next(g for g in dialogs if g.id==route['response_chat_id'])
        limit=asyncio.Semaphore(2);save_lock=asyncio.Lock()
        async def one(group):
            ids=group['ids'];old=prior.get(tuple(ids))
            if old and old.get('published'):return
            request=build_request(rows,group,source.id,args.date)
            async with limit:
                key=journal.claim_replay(source.id,destination.id,request['sender'],ids,args.date)
                if not key:
                    if old:return
                    item={'message_ids':ids,'status':'already_claimed','reply':'Demande déjà réservée ou en cours ; aucun renvoi automatique.','production_writes':0,'published':False}
                else:
                    if group.get('ignore'):
                        outcome={'status':'not_order','reply':group['reason']}
                    elif group.get('excluded'):
                        outcome={'status':'excluded','reply':'Création suspendue selon les règles approuvées.'}
                    elif group.get('uncertain'):
                        outcome={'status':'needs_group_review','reply':'À vérifier : '+group['reason']+' Aucune nouvelle commande créée.'}
                    else:
                        process=await asyncio.create_subprocess_exec(str(ROOT/'backend/.venv/Scripts/python.exe'),'-X','utf8',str(Path(__file__).with_name('replay_request.py')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                        try:
                            stdout,stderr=await asyncio.wait_for(process.communicate(json.dumps(request,ensure_ascii=False).encode('utf-8')),300)
                            if process.returncode:raise RuntimeError('SOB replay engine failed')
                            outcome=json.loads(stdout.decode('utf-8'))
                        except Exception as exc:
                            if process.returncode is None:process.kill();await process.wait()
                            outcome={'status':'requires_readback','reply':'Traitement interrompu ('+type(exc).__name__+'). Vérifier le reçu TEST avant toute reprise.'}
                    item={'message_ids':ids,'date':rows[ids[0]]['date'],'contact':group['contact'],**outcome,'production_writes':0,'published':False,'route_key':key}
                    journal.result(key,outcome['reply'])
                    # Save the SQL outcome before the external publication.
                    async with save_lock:
                        results[:]=[r for r in results if tuple(r['message_ids'])!=tuple(ids)]+[item]
                        dump(results_path,results)
                    if journal.begin_delivery(key):
                        try:
                            sent=await publish(client,source,destination,ids,'🤖 SOB — Reprise du '+day.strftime('%d/%m/%Y')+'\n'+outcome['reply'])
                            journal.delivered(key,sent.id);item.update(published=True,destination_message=sent.id)
                        except Exception as exc:
                            journal.delivery_uncertain(key);item['publication_error']=type(exc).__name__
                async with save_lock:
                    results[:]=[r for r in results if tuple(r['message_ids'])!=tuple(ids)]+[item]
                    dump(results_path,results)
                print(json.dumps({k:item[k] for k in ('message_ids','status','number','numbers','reply','published') if k in item},ensure_ascii=False),flush=True)
        buckets=collections.defaultdict(list)
        for group in groups:buckets[group['contact']].append(group)
        async def contact(items):
            for group in items:await one(group)
        await asyncio.gather(*(contact(items) for items in buckets.values()))
        summary={'date':args.date,'source_group':source.name,'response_group':destination.name,'messages':len(source_rows),'groups':len(groups),'covered_messages':len({mid for r in results for mid in r['message_ids']}),'statuses':dict(collections.Counter(r['status'] for r in results)),'published':sum(bool(r.get('published')) for r in results),'created_numbers':[r['number'] for r in results if r.get('status')=='created' and r.get('number')],'production_writes':0}
        dump(out/'replay-summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    finally:await client.disconnect()

if __name__=='__main__':asyncio.run(main())
