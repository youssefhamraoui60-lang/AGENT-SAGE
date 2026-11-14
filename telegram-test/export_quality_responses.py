import asyncio,json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from telethon import TelegramClient
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runtime/sob-quality-audit-20261112'
async def main():
    client=TelegramClient(str(OUT/'audit.session'),38572478,'existing-session-only',receive_updates=False)
    try:
        await client.connect()
        groups=[g async for g in client.iter_dialogs() if g.id==-5586539927]
        if len(groups)!=1:raise RuntimeError('Response group missing')
        start=datetime(2026,11,11,tzinfo=ZoneInfo('Europe/Paris'));end=datetime(2026,11,13,tzinfo=ZoneInfo('Europe/Paris'))
        rows=[]
        async for m in client.iter_messages(groups[0].entity,offset_date=end,limit=None):
            if m.date<start:break
            rows.append({'id':m.id,'date':m.date.astimezone(ZoneInfo('Europe/Paris')).isoformat(),'sender':m.sender_id,'text':m.message or '', 'reply_to':m.reply_to_msg_id})
        rows.reverse();(OUT/'response-messages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'response_messages':len(rows)}))
    finally:await client.disconnect()
asyncio.run(main())
