"""Read-only export for evaluation. Never sends messages or creates orders."""
import asyncio
import json
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from telethon import TelegramClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runtime/sob-audit'


async def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--out')
    args=parser.parse_args()
    if args.out:OUT=Path(args.out).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'runtime/telegram-test/personal.session'
    target = OUT / 'audit.session'
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
    client = TelegramClient(str(target), 38572478, 'existing-session-only', receive_updates=False)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError('Existing session unavailable')
        groups = [d async for d in client.iter_dialogs() if d.name.casefold() == 'sob commandes']
        if len(groups) != 1:
            raise RuntimeError('Group not uniquely identified')
        rows = []
        downloaded = 0
        since=datetime.fromisoformat(args.start).replace(tzinfo=ZoneInfo('Europe/Paris')) if args.start else None
        until=datetime.fromisoformat(args.end).replace(tzinfo=ZoneInfo('Europe/Paris')) if args.end else None
        async for message in client.iter_messages(groups[0].entity, limit=None if since else 200,offset_date=until):
            if since and message.date<since:break
            row = {'id': message.id, 'date': message.date.astimezone(ZoneInfo('Europe/Paris')).isoformat(),
                   'sender_id': message.sender_id, 'text': message.message or '',
                   'reply_to': message.reply_to_msg_id, 'grouped_id': message.grouped_id,
                   'service': bool(message.action), 'file': None}
            if message.file:
                mime = message.file.mime_type or ''
                row['media'] = {'mime': mime, 'size': message.file.size, 'name': message.file.name}
                if (mime == 'application/pdf' or mime.startswith('image/')) and message.file.size <= 10_000_000 and downloaded + message.file.size <= 500_000_000:
                    folder = OUT / 'attachments' / str(message.id)
                    folder.mkdir(parents=True, exist_ok=True)
                    path = await client.download_media(message, file=str(folder) + '/')
                    row['file'] = str(Path(path).relative_to(OUT)) if path else None
                    downloaded += message.file.size
            rows.append(row)
        rows.reverse()
        (OUT / ('messages-week.json' if since else 'messages-200.json')).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'count': len(rows), 'oldest': rows[0]['date'] if rows else None,
                          'newest': rows[-1]['date'] if rows else None,
                          'attachments_downloaded': sum(bool(r['file']) for r in rows),
                          'downloaded_bytes': downloaded}, ensure_ascii=False))
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
