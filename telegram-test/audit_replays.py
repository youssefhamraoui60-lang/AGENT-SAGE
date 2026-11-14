"""Owner-authorized Telegram replays: SQL preview only, never order creation."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'runtime/sob-audit-replays.sqlite3'
PREFIX='🧪 SOB AUDIT '
LIMIT=asyncio.Semaphore(2)


def connection():
    db=sqlite3.connect(DB,timeout=20)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS requests(token TEXT PRIMARY KEY,chat INTEGER,sender INTEGER,caption TEXT,sources TEXT,expires REAL,status TEXT,result TEXT)')
    return db


def register(chat,sender,caption,sources):
    import secrets
    token=secrets.token_hex(16)
    with connection() as db:
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,NULL)',(token,chat,sender,caption,json.dumps(sources,ensure_ascii=False),time.time()+14400,'queued'))
    return token


async def dispatch(client,event,response_chat=None):
    text=event.raw_text or ''
    if not text.startswith(PREFIX):return False
    head,_,caption=text.partition('\n')
    token=head.removeprefix(PREFIX)
    if not re.fullmatch(r'[a-f0-9]{32}',token):return True
    with connection() as db:
        row=db.execute('SELECT * FROM requests WHERE token=?',(token,)).fetchone()
    if not row or row['chat']!=event.chat_id or row['sender']!=event.sender_id or row['caption']!=caption or row['expires']<time.time():return True
    async with LIMIT:
        proc=await asyncio.create_subprocess_exec(str(ROOT/'backend/.venv/Scripts/python.exe'),'-X','utf8',str(Path(__file__)),token,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            output,_=await asyncio.wait_for(proc.communicate(),240)
            result=json.loads(output.decode('utf-8'))
            reply=result['reply']
        except Exception:
            if proc.returncode is None:proc.kill();await proc.wait()
            reply='Test conservé, analyse indisponible. Aucune création déclenchée.'
        reply='🤖 SOB\n'+' '.join(reply.split())
        if len(reply)>200:reply=reply[:199]+'…'
        await client.send_message(response_chat if response_chat is not None else event.chat_id,reply,
                                  reply_to=None if response_chat is not None else event.id,parse_mode=None)
    return True


async def run(token):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM requests WHERE token=?',(token,)).fetchone()
        if not row or row['expires']<time.time():return {'reply':'Test expiré. Aucune création.'}
        if row['status']=='done':return json.loads(row['result'])
        if row['status']!='queued':return {'reply':'Test déjà en cours. Aucune création.'}
        db.execute("UPDATE requests SET status='running' WHERE token=?",(token,))
    result={'status':'error','reply':'Test indisponible. Aucune création.'}
    try:
        from prepare import prepare
        from creation import build_payload,run_script
        from document_memory import decode
        from read_documents_layout import read
        texts=[]
        sources=json.loads(row['sources'])
        for source in sources:
            text=source['text']
            if source.get('file'):
                path=Path(source['file']).resolve()
                if not path.is_relative_to((ROOT/'runtime/telegram-test/documents').resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Document source modifié')
                doc=await asyncio.to_thread(decode,path,read)
                if not doc.get('ok'):raise ValueError('Document illisible')
                text+='\nDOCUMENT JOINT (données à vérifier avant validation) :\n'+doc['text']
            texts.append(text)
        details=await prepare([{'role':'user','content':'\n\n'.join(texts)}],details=True)
        result={'status':'needs_review','details':details,'reply':'Test '+str(sources[0]['id'])+' : manque '+', '.join(details.get('missing_fields',[]))+'. Aucune création.'}
        if not details['missing'] and not details.get('missing_fields') and details['client'] and details['lines']:
            payload=build_payload(details)
            assert payload['mode']=='preview'
            sql=await asyncio.to_thread(run_script,'sob-execute.ps1',payload)
            result['sql']=sql
            result['status']='sql_preview_passed' if sql.get('ok') else 'sql_preview_refused'
            result['reply']='Test '+str(sources[0]['id'])+' : '+('prêt, client '+details['client']['BPCNUM_0']+', TTC '+payload['total']+' MAD' if sql.get('ok') else 'contrôle SQL refusé')+'. Aucune création.'
    except Exception as exc:
        result.update(error=type(exc).__name__+': '+str(exc)[:200])
        if type(exc).__name__=='CreationError':result['reply']='Test '+str(sources[0]['id'])+' : '+str(exc)+' Aucune création.'
    with connection() as db:db.execute("UPDATE requests SET status='done',result=? WHERE token=?",(json.dumps(result,ensure_ascii=False),token))
    return result


if __name__=='__main__':
    print(json.dumps(asyncio.run(run(sys.argv[1])),ensure_ascii=False))
