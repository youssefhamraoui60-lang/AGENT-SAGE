"""Read-only discovery of the two existing SOB groups."""
import asyncio,json,sqlite3
from pathlib import Path
from telethon import TelegramClient
ROOT=Path(__file__).resolve().parents[1]
async def main():
    source=ROOT/'runtime/telegram-test/personal.session'
    directory=ROOT/'runtime/sob-routing-inspection';directory.mkdir(parents=True,exist_ok=True)
    target=directory/'reader.session'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
        with sqlite3.connect(target) as dst:src.backup(dst)
    client=TelegramClient(str(target),38572478,'existing-session-only',receive_updates=False)
    try:
        await client.connect()
        if not await client.is_user_authorized():raise RuntimeError('Telegram session unavailable')
        rows=[]
        async for dialog in client.iter_dialogs():
            if not dialog.is_group or 'sob' not in dialog.name.casefold():continue
            participants=await client.get_participants(dialog.entity,limit=0)
            recent=await client.get_messages(dialog.entity,limit=1)
            rows.append({'id':dialog.id,'name':dialog.name,'participants':participants.total,'latest_id':recent[0].id if recent else None,'latest_date':recent[0].date.isoformat() if recent else None})
        (directory/'groups.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(rows,ensure_ascii=True))
    finally:await client.disconnect()
if __name__=='__main__':asyncio.run(main())
