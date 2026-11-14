import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'backend'))
from app.services import supplier_mail as m
from email.parser import BytesParser
from email import policy
from contextlib import closing
with closing(m.ledger()) as c:
    print('LEDGER '+json.dumps(c.execute('SELECT folder,status,conversation,result FROM messages').fetchall()))
client=m.connect()
try:
    client.select('INBOX',readonly=True)
    status,data=client.uid('search',None,'(OR SUBJECT "OB" SUBJECT "SOB")')
    results=[]
    for uid in data[0].split():
        status,parts=client.uid('fetch',uid,'(BODY.PEEK[HEADER] FLAGS)')
        header=next((p[1] for p in parts if isinstance(p,tuple)),None)
        if not header:continue
        msg=BytesParser(policy=policy.default).parsebytes(header)
        if not m.matches_subject(str(msg.get('Subject',''))):continue
        status,parts=client.uid('fetch',uid,'(BODY.PEEK[])')
        raw=next(p[1] for p in parts if isinstance(p,tuple))
        dest=Path('runtime/supplier-mail-inbox');dest.mkdir(exist_ok=True)
        (dest/(uid.decode()+'.eml')).write_bytes(raw)
        try:body=m.parse_message(raw);error=None
        except ValueError as e:body=None;error=str(e)
        results.append({'uid':uid.decode(),'subject':str(msg.get('Subject','')),'date':str(msg.get('Date','')),'text':body['text'] if body else None,'error':error})
    Path('runtime/supplier-mail-inventory.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=True))
finally:client.logout()
