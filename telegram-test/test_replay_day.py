import asyncio,json
from contextlib import contextmanager
from pathlib import Path
import pytest
import creation
import replay_request as engine
from telegram_routing import RouteJournal

SOURCE=-1004375687420
DAY='2026-11-11'

@pytest.fixture
def replay_input():return {'source':SOURCE,'sender':7,'ids':[5134],'day':DAY,'history':[{'role':'user','content':'Contact : TEST\nClient C01401 : 20 sacs CPJ45'}]}

@pytest.fixture
def ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    with creation.connection() as conn:
        conn.execute('CREATE TABLE sob_preparations(owner TEXT PRIMARY KEY,details TEXT,history TEXT,updated REAL)')
    def insert(owner,status,number='2026ARC15000',history=None,day=DAY):
        with creation.connection() as conn:
            conn.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)',('review-'+owner,owner,json.dumps({'order_date':day,'reference':'SOB-EXISTING'}),'plan',9999999999,status,number,None))
            if history:conn.execute('INSERT INTO sob_preparations VALUES(?,?,?,?)',(owner,'{}',json.dumps(history),0))
    return insert

@pytest.fixture
def authorized(monkeypatch):
    monkeypatch.setattr(engine.learning_memory,'approved_rules',lambda:[
        {'kind':'policy','rule_key':'telegram_group_routing','payload':{'source_chat_id':SOURCE,'response_chat_id':-5586539927,'folder':'TEST','all_senders':True}},
        {'kind':'policy','rule_key':'telegram_replay_'+DAY,'payload':{'day':DAY,'source_chat_id':SOURCE,'folder':'TEST','max_message_id':5225}}])
    async def forbidden(*args):pytest.fail('Existing or uncertain requests must not execute again')
    monkeypatch.setattr(engine.telegram_order,'handle',forbidden)


def test_existing_source_receipt_is_not_recreated(replay_input,ledger,authorized):
    ledger('telegram:'+str(SOURCE)+':7:5134','created')
    result=asyncio.run(engine.process(replay_input))
    assert result['status']=='already_created' and result['numbers']==['2026ARC15000']


def test_pending_source_is_not_replayed(replay_input,ledger,authorized):
    ledger('telegram:'+str(SOURCE)+':7:5134','uncertain',number=None)
    assert asyncio.run(engine.process(replay_input))['status']=='requires_readback'


def test_same_day_copy_in_private_group_is_flagged_before_creation(replay_input,ledger,authorized):
    ledger('telegram:-5586539927:7:900','created',history=replay_input['history'])
    result=asyncio.run(engine.process(replay_input))
    assert result['status']=='potential_duplicate'


def test_old_identical_order_is_not_automatically_the_same_request(replay_input,ledger):
    ledger('telegram:-5586539927:7:900','created',history=replay_input['history'],day='2026-11-10')
    assert engine.prior_receipts(replay_input)==([],[],[])


def test_replay_scope_rejects_future_unapproved_message(replay_input,ledger,authorized):
    replay_input['ids']=[6000]
    with pytest.raises(ValueError,match='snapshot'):asyncio.run(engine.process(replay_input))


def test_dated_replay_preserves_old_sent_batch_and_cannot_repeat(tmp_path):
    journal=RouteJournal(tmp_path/'route.sqlite3')
    original=journal.claim(SOURCE,-5586539927,7,[5134])
    journal.result(original,'Manque client');assert journal.begin_delivery(original);journal.delivered(original,900)
    retry=journal.claim_replay(SOURCE,-5586539927,7,[5134],DAY);assert retry and retry!=original
    assert journal.claim_replay(SOURCE,-5586539927,7,[5134],DAY) is None
    with journal.connection() as conn:assert conn.execute('SELECT count(*) FROM batches').fetchone()[0]==2


def test_dated_replay_cannot_interfere_with_live_execution(tmp_path):
    journal=RouteJournal(tmp_path/'route.sqlite3')
    assert journal.claim(SOURCE,-5586539927,7,[5134])
    assert journal.claim_replay(SOURCE,-5586539927,7,[5134,5135],DAY) is None


def test_new_request_reports_created_only_with_actual_receipt(replay_input,ledger,authorized,monkeypatch):
    async def handle(history,owner):
        ledger(owner,'created','2026ARC15001',history=history)
        return 'Commande 2026ARC15001 créée dans Sage TEST.'
    monkeypatch.setattr(engine.telegram_order,'handle',handle)
    result=asyncio.run(engine.process(replay_input))
    assert result['status']=='created' and result['number']=='2026ARC15001'


def test_sql_readback_rejects_wrong_quantity_price_or_customer():
    from report_replay import verified
    payload={'client':'C01401','lines':[{'line':1000,'article':'CPJ45','quantity':'20','price':'81'}]}
    row={'SOHNUM_0':'2026ARC15100','BPCORD_0':'C01401','SOPLIN_0':1000,'ITMREF_0':'CPJ45','QTY_0':'20.00000','NETPRIATI_0':'81.00000'}
    assert verified(payload,[row],'2026ARC15100')
    assert not verified(payload,[{**row,'QTY_0':'21'}],'2026ARC15100')
    assert not verified(payload,[{**row,'NETPRIATI_0':'80'}],'2026ARC15100')
    assert not verified(payload,[{**row,'BPCORD_0':'C10370'}],'2026ARC15100')
    assert not verified(payload,[],'2026ARC15100')
