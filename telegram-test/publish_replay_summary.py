"""Publish a verified replay summary once, only in the configured response group."""
import argparse,asyncio,json
from pathlib import Path
from telethon import TelegramClient
from telegram_routing import ROOT,RouteJournal,load_policy

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);args=parser.parse_args()
    out=ROOT/'runtime'/('sob-day-'+args.date.replace('-',''))
    summary=json.loads((out/'replay-summary.json').read_text(encoding='utf-8'))
    route=load_policy();journal=RouteJournal();key=args.date+':'+summary['last_source_time']
    counts=summary['statuses']
    lines=['🤖 SOB — Bilan de la reprise du '+args.date,
        str(summary['messages'])+' messages source / '+str(summary['groups'])+' lots examinés.',
        str(counts.get('created',0))+' nouvelles commandes TEST ; '+str(summary.get('sql_verified',0))+' vérifiées par relecture SQL.',
        str(counts.get('already_created',0))+' demandes déjà créées ; '+str(counts.get('potential_duplicate',0))+' copie potentielle signalée sans création.',
        str(counts.get('needs_data',0))+' demandes à compléter ; '+str(counts.get('needs_group_review',0))+' rattachements ou corrections à vérifier.',
        str(counts.get('not_order',0))+' message hors création de commande.',
        str(summary['published'])+' réponses détaillées publiées dans ce groupe.',
        'Snapshot jusqu’au '+summary['last_source_time']+'. Les nouveaux messages continuent d’être traités en direct.',
        'Aucune écriture dans OB.']
    if summary.get('sql_unverified'):lines.append('Relecture à vérifier : '+', '.join(summary['sql_unverified']))
    text='\n'.join(lines)
    with journal.connection() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS replay_summaries(key TEXT PRIMARY KEY,status TEXT NOT NULL,message INTEGER)')
        if not conn.execute("INSERT OR IGNORE INTO replay_summaries VALUES(?,'sending',NULL)",(key,)).rowcount:
            print(json.dumps({'status':'already_claimed'}));return
    client=TelegramClient(str(out/'replay.session'),38572478,'existing-session-only',receive_updates=False)
    try:
        await client.connect()
        if not await client.is_user_authorized():raise RuntimeError('Existing session unavailable')
        message=await client.send_message(route['response_chat_id'],text,parse_mode=None)
        with journal.connection() as conn:conn.execute("UPDATE replay_summaries SET status='sent',message=? WHERE key=?",(message.id,key))
        print(json.dumps({'status':'sent','response_group':route['response_name'],'message_id':message.id}))
    except Exception:
        with journal.connection() as conn:conn.execute("UPDATE replay_summaries SET status='delivery_uncertain' WHERE key=?",(key,))
        raise
    finally:await client.disconnect()

if __name__=='__main__':asyncio.run(main())
