import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from telegram_routing import RouteJournal, validate_policy, publish, privileged


POLICY={'source_chat_id':-1004375687420,'response_chat_id':-5586539927,'folder':'TEST','all_senders':True}


@pytest.mark.parametrize('change',[{'source_chat_id':-5586539927},{'folder':'OB'},{'all_senders':False},{'source_chat_id':'-1004375687420'}])
def test_invalid_routes_rejected(change):
    with pytest.raises(ValueError):validate_policy({**POLICY,**change})


def test_batch_claim_is_durable_and_each_source_message_is_unique(tmp_path):
    path=tmp_path/'routing.sqlite3';journal=RouteJournal(path)
    key=journal.claim(-1001,-2001,7,[1,2]);assert key
    journal.result(key,'Commande TEST créée')
    journal=RouteJournal(path)
    assert journal.claim(-1001,-2001,7,[1,2]) is None
    assert journal.claim(-1001,-2001,7,[2,3]) is None
    assert journal.begin_delivery(key)
    assert not journal.begin_delivery(key)
    journal.delivered(key,55)
    with journal.connection() as conn:
        row=conn.execute('SELECT status,destination_message FROM batches').fetchone()
        assert tuple(row)==('sent',55)


def test_uncertain_delivery_is_not_replayed(tmp_path):
    journal=RouteJournal(tmp_path/'routing.sqlite3');key=journal.claim(-1001,-2001,7,[1])
    journal.result(key,'Résultat');assert journal.begin_delivery(key)
    journal.delivery_uncertain(key)
    assert not journal.begin_delivery(key)
    assert journal.claim(-1001,-2001,7,[1]) is None


def test_result_published_only_to_response_group_with_original_message_link():
    calls=[]
    class Client:
        async def send_message(self,entity,text,**kwargs):
            calls.append((entity,text,kwargs));return SimpleNamespace(id=50)
    source=SimpleNamespace(id=-1004375687420,name='sob commandes',entity='source',is_group=True)
    target=SimpleNamespace(id=-5586539927,name='COMMANDES SOB',entity='response',is_group=True)
    result=asyncio.run(publish(Client(),source,target,[5209,5210],'🤖 SOB\nCommande TEST créée.'))
    assert result.id==50 and calls[0][0]=='response'
    assert 'https://t.me/c/4375687420/5209' in calls[0][1]
    assert '#5209, #5210' in calls[0][1]
    assert not calls[0][2].get('reply_to')


def test_other_users_cannot_change_approved_lessons():
    assert privileged('corriger article pointe 6 = PF-TP16X20')
    assert not privileged('Contact : Aicha\n20 sacs CPJ45')


def test_listener_accepts_other_users_and_never_replies_in_source(tmp_path,monkeypatch):
    import connect,telegram_routing
    from telegram_batch import OrderBatches
    source=SimpleNamespace(id=POLICY['source_chat_id'],name='sob commandes',entity='source',is_group=True)
    target=SimpleNamespace(id=POLICY['response_chat_id'],name='COMMANDES SOB',entity='response',is_group=True)
    calls=[];commands=[]
    class Client:
        def __init__(self,*a,**kw):self.handler=None
        async def connect(self):pass
        async def disconnect(self):pass
        async def is_user_authorized(self):return True
        async def iter_dialogs(self):
            yield source;yield target
        async def get_me(self):return SimpleNamespace(id=999)
        async def get_messages(self,entity,limit):return [SimpleNamespace(id=100)]
        def add_event_handler(self,handler,event):
            assert event=='source';self.handler=handler
        async def send_message(self,entity,text,**kwargs):
            calls.append((entity,text));return SimpleNamespace(id=len(calls))
        async def run_until_disconnected(self):
            for identifier,sender,text in [(101,55,'Contact : Aicha\nClient C01401 : 20 sacs CPJ45'),
                                           (102,66,'Contact : Rachida\nClient C10370 : 30 sacs CPJ45'),
                                           (103,55,'corriger article pointe 6 = PF-TP16X20'),
                                           (104,999,'🤖 SOB\nCommande déjà créée')]:
                await self.handler(SimpleNamespace(id=identifier,sender_id=sender,raw_text=text,
                    chat_id=source.id,message=SimpleNamespace(media=None)))
            await asyncio.sleep(.05)
    telethon=SimpleNamespace(TelegramClient=Client,events=SimpleNamespace(NewMessage=lambda chats:chats),errors=SimpleNamespace())
    monkeypatch.setitem(sys.modules,'telethon',telethon)
    monkeypatch.setattr(telegram_routing,'load_policy',lambda:dict(POLICY))
    journal=RouteJournal(tmp_path/'routing.sqlite3')
    monkeypatch.setattr(telegram_routing,'RouteJournal',lambda:journal)
    monkeypatch.setattr(connect,'OrderBatches',lambda process,**options:OrderBatches(process,delay=.001,aggregate=options.get('aggregate',True)))
    class Process:
        returncode=0
        async def communicate(self,data):
            assert json.loads(data)[-1]['role']=='user'
            return json.dumps({'reply':'🤖 SOB\nCommande TEST créée.'}).encode(),b''
    async def subprocess(*args,**kwargs):commands.append(args);return Process()
    monkeypatch.setattr(connect.asyncio,'create_subprocess_exec',subprocess)
    original_is_file=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda p:True if p.name=='personal.session' else original_is_file(p))
    monkeypatch.setattr(sys,'argv',['connect.py','--assistant','--resume','--api-id','1','--routing-policy'])
    asyncio.run(connect.main())
    assert len(commands)==2 and len(calls)==2
    assert all(call[0]=='response' for call in calls)
    assert any('telegram:'+str(source.id)+':55:101' in command for command in commands)
    assert any('telegram:'+str(source.id)+':66:102' in command for command in commands)
    with journal.connection() as conn:
        assert conn.execute("SELECT count(*) FROM batches WHERE status='sent'").fetchone()[0]==2


def test_audit_response_is_redirected_to_response_group(tmp_path,monkeypatch):
    import audit_replays
    monkeypatch.setattr(audit_replays,'DB',tmp_path/'audit.sqlite3')
    token=audit_replays.register(-1001,7,'test',[{'id':100,'text':'Client C01401'}])
    class Process:
        returncode=0
        async def communicate(self):return json.dumps({'reply':'Simulation seulement.'}).encode(),b''
    async def subprocess(*args,**kwargs):return Process()
    monkeypatch.setattr(audit_replays.asyncio,'create_subprocess_exec',subprocess)
    calls=[]
    class Client:
        async def send_message(self,*args,**kwargs):calls.append((args,kwargs))
    event=SimpleNamespace(raw_text=audit_replays.PREFIX+token+'\ntest',chat_id=-1001,sender_id=7,id=101)
    assert asyncio.run(audit_replays.dispatch(Client(),event,response_chat=-2001))
    assert calls[0][0][0]==-2001 and calls[0][1]['reply_to'] is None
