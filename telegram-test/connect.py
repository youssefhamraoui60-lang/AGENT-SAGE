"""Test Telegram autonome : authentification et lecture, sans lien avec Sage."""
import asyncio
import getpass
import os
import json
import sys
import argparse
from pathlib import Path
from telegram_batch import OrderBatches,client_scoped_history


def display(message):
    # Neutralise les séquences de contrôle provenant des messages distants.
    text = message.message or '[Message sans texte / média non téléchargé]'
    text = ''.join(c for c in text if c.isprintable() or c == '\n')
    print(f'\n[{message.date.astimezone():%Y-%m-%d %H:%M:%S}] #{message.id}\n{text}', flush=True)


async def main():
    from telethon import TelegramClient, events, errors

    parser = argparse.ArgumentParser()
    parser.add_argument('--assistant', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Session existante uniquement, sans nouvelle authentification')
    parser.add_argument('--api-id', default=os.environ.get('TELEGRAM_API_ID'))
    parser.add_argument('--group')
    parser.add_argument('--routing-policy', action='store_true', help='Use the approved source/response routing stored in PostgreSQL')
    parser.add_argument('--resume-after',type=int,help='Explicit deployment checkpoint; replay only newer unclaimed source messages')
    args = parser.parse_args()
    assistant_mode = args.assistant
    routing = None
    if args.routing_policy:
        if not assistant_mode: raise ValueError('Routing requires assistant mode')
        from telegram_routing import load_policy
        routing = load_policy()
        args.group = str(routing['source_chat_id'])
    print('SOB — Assistant DeepSeek' if assistant_mode else 'SOB — Test Telegram personnel (lecture uniquement)')
    print('Création directe Sage TEST si données complètes.' if assistant_mode else 'Lecture seule. Aucune commande créée.')
    raw_id = args.api_id or input('API ID (my.telegram.org) : ').strip()
    if not raw_id.isdecimal() or int(raw_id) <= 0:
        raise ValueError('API ID invalide : un entier positif est requis.')
    # api_hash is only used for a new sign-in, which resume mode forbids.
    api_hash = 'existing-session-only' if args.resume else os.environ.get('TELEGRAM_API_HASH') or getpass.getpass('API hash (masqué) : ')
    if not args.resume and (len(api_hash) != 32 or any(c not in '0123456789abcdefABCDEF' for c in api_hash)):
        raise ValueError('API hash invalide : 32 caractères hexadécimaux requis.')
    session_dir = Path(__file__).resolve().parents[1] / 'runtime' / 'telegram-test'
    session_dir.mkdir(parents=True, exist_ok=True)
    if args.resume and not (session_dir / 'personal.session').is_file():
        raise RuntimeError('Session Telegram absente : connexion interactive nécessaire.')
    client = TelegramClient(str(session_dir / 'personal'), int(raw_id), api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if args.resume:
                raise RuntimeError('Session Telegram expirée : connexion interactive nécessaire.')
            phone = input('Numéro Telegram avec indicatif pays (+33...) : ').strip()
            sent = await client.send_code_request(phone)
            code = getpass.getpass('Code reçu dans Telegram (masqué) : ').replace(' ', '')
            try:
                await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
            except errors.SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass('Mot de passe Telegram 2FA (masqué) : '))
        print('\nCONNEXION RÉUSSIE avec ton compte personnel.')
        groups = [dialog async for dialog in client.iter_dialogs() if dialog.is_group]
        if not groups:
            print('Aucun groupe accessible trouvé pour ce compte.')
            return
        for index, dialog in enumerate(groups, 1):
            title = ''.join(c for c in dialog.name if c.isprintable())
            print(f'{index}. {title}')
        selected = None
        if args.group:
            matches = [g for g in groups if g.name.casefold() == args.group.casefold() or str(g.id) == args.group]
            if len(matches) != 1:
                raise ValueError('Groupe absent ou ambigu.')
            selected = matches[0]
        while selected is None:
            selection = input('\nNuméro du groupe à lire (q pour quitter) : ').strip()
            if selection.lower() == 'q':
                return
            if selection.isdecimal() and 1 <= int(selection) <= len(groups):
                selected = groups[int(selection) - 1]
                break
            print('Choisis un numéro dans la liste.')
        group = selected
        reply_group = group
        journal = None
        if routing:
            matches = [g for g in groups if g.id == routing['response_chat_id']]
            if len(matches) != 1: raise ValueError('Response group missing or ambiguous')
            reply_group = matches[0]
            from telegram_routing import RouteJournal
            journal = RouteJournal()
            print('SOURCE : '+group.name+' -> REPONSES : '+reply_group.name+' ; Sage TEST', flush=True)
        seen = set()
        histories = {}
        lock = asyncio.Lock()
        me = await client.get_me()
        cutoff = (await client.get_messages(group.entity, limit=1))
        last_existing = cutoff[0].id if cutoff else 0
        if args.resume_after is not None:
            if not routing or args.resume_after<0 or args.resume_after>last_existing:raise ValueError('Invalid source resume checkpoint')
            last_existing=args.resume_after

        async def process_batch(key, batch_messages):
            async with lock:
                route_key = journal.claim(group.id, reply_group.id, key[1], [mid for mid, _ in batch_messages]) if journal else None
                if journal and not route_key:
                    print('SOB : lot deja pris en charge, aucun nouvel envoi.', flush=True)
                    return
                content='\n\n'.join(text for _, text in batch_messages)[:20000]
                history=client_scoped_history(histories.get(key,[]),content)
                histories[key]=history
                history.append({'role': 'user', 'content': content})
                history[:] = history[-8:]
                python = Path(__file__).resolve().parents[1] / 'backend/.venv/Scripts/python.exe'
                proc = await asyncio.create_subprocess_exec(
                    str(python), '-X', 'utf8', str(Path(__file__).with_name('telegram_order.py')),
                    f'telegram:{group.id}:{key[1]}:{batch_messages[0][0]}',
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(json.dumps(history, ensure_ascii=False).encode('utf-8')), 180)
                    reply = json.loads(stdout.decode('utf-8'))['reply']
                except Exception:
                    if proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                    reply = '🤖 SOB\nRésultat indisponible. Vérifier dans Sage avant de renvoyer la commande.'
                history.append({'role': 'assistant', 'content': reply[:7000]})
                if journal:
                    from telegram_routing import publish
                    journal.result(route_key, reply)
                    if journal.begin_delivery(route_key):
                        try:
                            published = await publish(client, group, reply_group, [mid for mid, _ in batch_messages], reply)
                            journal.delivered(route_key, published.id)
                        except Exception:
                            journal.delivery_uncertain(route_key)
                            print('SOB : resultat conserve ; publication a verifier dans le groupe de reponses.', flush=True)
                else:
                    await client.send_message(group.entity, reply[:200], reply_to=batch_messages[-1][0], parse_mode=None)
                print(f'SOB : réponse envoyée au lot de {len(batch_messages)} messages.', flush=True)
                if reply.startswith('\U0001f916 SOB\nCommande '):
                    histories.pop(key, None)

        batcher = OrderBatches(process_batch, aggregate=False)
        print('Agrégation désactivée : chaque message est traité séparément, sans délai de regroupement.', flush=True)

        ingestion_lock = asyncio.Lock()

        async def on_message(event):
            # Media decoding must finish before a following text complement is
            # batched. Telethon otherwise handles these callbacks concurrently.
            from audit_replays import PREFIX, dispatch as dispatch_audit
            if (event.raw_text or '').startswith(PREFIX):
                if event.sender_id != me.id: return
                await dispatch_audit(client,event,response_chat=reply_group.entity if routing else None)
                return
            async with ingestion_lock:
                await ingest_message(event)

        async def ingest_message(event):
            if event.id not in seen:
                seen.add(event.id)
                if not args.resume:
                    display(event.message)
                if assistant_mode and event.id > last_existing and (event.raw_text or event.message.media):
                    # Replies carry this marker: avoid reacting to our own messages.
                    if (event.raw_text or '').startswith('🤖 SOB'):
                        return
                    # Personal-account prototype: only the owner's requests trigger replies.
                    if not routing and event.sender_id != me.id:
                        return
                    if routing:
                        from telegram_routing import privileged
                        if event.sender_id is None or (event.sender_id != me.id and privileged(event.raw_text or '')): return
                    from audit_replays import dispatch as dispatch_audit
                    if await dispatch_audit(client,event,response_chat=reply_group.entity if routing else None):
                        return
                    text=event.raw_text or ''
                    if event.message.media:
                        file=event.message.file
                        mime=getattr(file,'mime_type','') or ''
                        if not file or getattr(file,'size',0)>10*1024*1024 or not (mime=='application/pdf' or mime.startswith('image/')):
                            text+='\nDocument non lu : format PDF/image et taille maximale 10 Mo requis. Données de commande à préciser.'
                        else:
                            directory=session_dir/'documents'/str(group.id)/str(event.id)
                            directory.mkdir(parents=True,exist_ok=True)
                            target=directory/('document.pdf' if mime=='application/pdf' else 'image.jpg')
                            try:
                                await client.download_media(event.message,file=str(target))
                                python=Path(__file__).resolve().parents[1]/'backend/.venv/Scripts/python.exe'
                                proc=await asyncio.create_subprocess_exec(str(python),'-X','utf8',str(Path(__file__).with_name('document_cli.py')),str(target),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                                try:output,_=await asyncio.wait_for(proc.communicate(),120)
                                except asyncio.TimeoutError:
                                    proc.kill();await proc.wait();raise
                                decoded=json.loads(output.decode('utf-8'))
                                if not decoded.get('ok'):
                                    raise ValueError('Unreadable document')
                                text+='\nDOCUMENT JOINT (données à vérifier avant validation) :\n'+decoded['text']
                                if decoded.get('truncated'):text+='\nAttention : texte tronqué, document à vérifier.'
                            except Exception:
                                text+='\nDocument conservé, lecture indisponible : client et lignes à préciser avant validation.'
                    batcher.add(group.id, event.sender_id, event.id, text)

        client.add_event_handler(on_message, events.NewMessage(chats=group.entity))
        if args.resume_after is not None:
            from types import SimpleNamespace
            from datetime import datetime,timezone,timedelta
            with journal.connection() as conn:
                handled={r['message'] for r in conn.execute('SELECT message FROM source_messages WHERE source=? AND message>?',(group.id,args.resume_after))}
            recent_cutoff=datetime.now(timezone.utc)-timedelta(minutes=10)
            async with ingestion_lock:
                async for pending in client.iter_messages(group.entity,min_id=args.resume_after,reverse=True):
                    if pending.id in handled or pending.date<recent_cutoff:
                        seen.add(pending.id)
                        continue
                    await ingest_message(SimpleNamespace(id=pending.id,raw_text=pending.message or '',sender_id=pending.sender_id,message=pending,chat_id=group.id,reply=pending.reply))
            print('Reprise source après '+str(args.resume_after)+' terminée ; journal anti-doublons conservé.',flush=True)
        print('\nLecture des 10 derniers messages :')
        messages = await client.get_messages(group.entity, limit=10)
        for message in reversed(messages):
            if message.id not in seen:
                seen.add(message.id)
                if not args.resume:
                    display(message)
        if not messages:
            print('Historique vide ou inaccessible ; la connexion est établie.')
        print('\nÉCOUTE ACTIVE — nouveaux messages de ce groupe. Ctrl+C pour arrêter.', flush=True)
        if routing:
            print('Routage actif : demandes de tous les utilisateurs du groupe source ; reponses uniquement dans le groupe destination.', flush=True)
        elif assistant_mode:
            print('DeepSeek actif : réponses dans le groupe choisi aux NOUVEAUX messages de ton compte. Renvoie ta demande pour préparer une commande.', flush=True)
        try:
            await client.run_until_disconnected()
        finally:
            await batcher.close()
    finally:
        await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print('\nTest arrêté.')
    except Exception as exc:
        # Le texte des exceptions peut contenir des données privées.
        print(f'\nÉchec ({type(exc).__name__}). Vérifie la connexion, les identifiants et le code Telegram.')
        raise SystemExit(1)
