import asyncio
import creation
import drafts
import telegram_order


def test_complete_telegram_order_creates_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(creation, 'LEDGER', tmp_path / 'orders.sqlite3')
    details = {'intent': 'order', 'client': {'BPCNUM_0': 'C08705'},
               'lines': [{'article': 'CPJ35', 'quantity': 240, 'price': 75}],
               'delivery': '2026-11-09', 'missing': [], 'missing_fields': []}
    async def prepare(*args, **kwargs):
        return details
    monkeypatch.setattr(telegram_order, 'prepare', prepare)
    monkeypatch.setattr(drafts, 'save', lambda *args: None)
    calls = []
    monkeypatch.setattr(creation, 'review', lambda owner, value: {'id': 'review'})
    def confirm(owner, identifier, *, human_validated=False):
        calls.append((owner, identifier, human_validated))
        return {'number': '2026ARC15000'}
    monkeypatch.setattr(creation, 'confirm', confirm)
    reply = asyncio.run(telegram_order.handle([], 'telegram:123'))
    assert calls == [('telegram:123', 'review', True)]
    assert '2026ARC15000' in reply
    assert len(telegram_order.short(reply)) <= 200


def test_incomplete_telegram_order_reports_missing_without_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(creation, 'LEDGER', tmp_path / 'orders.sqlite3')
    async def prepare(*args, **kwargs):
        return {'intent': 'order', 'client': None, 'lines': [],
                'delivery': '2026-11-09', 'missing': ['client'], 'missing_fields': ['client Sage']}
    monkeypatch.setattr(telegram_order, 'prepare', prepare)
    monkeypatch.setattr(drafts, 'save', lambda *args: None)
    def forbidden(*args, **kwargs):
        raise AssertionError('Incomplete orders cannot be created')
    monkeypatch.setattr(creation, 'review', forbidden)
    reply = asyncio.run(telegram_order.handle([], 'telegram:123'))
    assert reply.startswith('Manque :')
    assert 'Brouillon' not in reply

def test_cement_trip_requests_loading_without_creating_or_reporting_a_unit_error(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    monkeypatch.setattr(drafts,'save',lambda *a:None)
    async def prepare(*a,**k):return {'intent':'order','client':{'BPCNUM_0':'C08705'},'lines':[{'article':'CPJ35','quantity':None,'price':80}],
        'delivery':'2026-11-13','missing':['chargement absent'],'missing_fields':['tonnage du voyage CPJ35','unité CPJ35']}
    monkeypatch.setattr(telegram_order,'prepare',prepare)
    monkeypatch.setattr(creation,'review',lambda *a:(_ for _ in ()).throw(AssertionError('Unknown load cannot create')))
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'C08705\n2 VYS CPJ35'}],'trip-loading-test'))
    assert '540/560/autre' in reply and 'total de sacs' in reply
    assert 'unité CPJ35' not in reply
    assert len(telegram_order.short(reply))<=200


def test_unreadable_document_gets_specific_reply_without_creation(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    async def prepare(*args,**kwargs):
        return {'intent':'other','client':None,'lines':[], 'missing_fields':['client Sage','articles et quantités']}
    monkeypatch.setattr(telegram_order,'prepare',prepare)
    monkeypatch.setattr(drafts,'save',lambda *args:None)
    def forbidden(*args,**kwargs):raise AssertionError('Unreadable document must not create')
    monkeypatch.setattr(creation,'review',forbidden)
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'DOCUMENT JOINT :\nTexte peu lisible'}],'doc-unreadable'))
    assert 'lecture incomplète' in reply and 'client Sage' in reply
    assert 'Indique le client' not in reply


def test_provider_failure_preserves_request_without_sql_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(creation, 'LEDGER', tmp_path / 'orders.sqlite3')
    async def unavailable(*args, **kwargs):
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr(telegram_order, 'prepare', unavailable)
    def forbidden(*args, **kwargs):
        raise AssertionError('No SQL creation during provider outage')
    monkeypatch.setattr(creation, 'review', forbidden)
    history=[{'role':'user','content':'Client C01401 : 20 sacs CPJ45'}]
    reply=asyncio.run(telegram_order.handle(history,'telegram:outage'))
    assert 'conservée' in reply
    with creation.connection() as conn:
        saved=conn.execute('SELECT history FROM sob_preparations WHERE owner=?',('telegram:outage',)).fetchone()
    import json
    assert json.loads(saved['history'])==history


def test_excluded_bouchaib_does_not_trigger_analysis_or_creation(monkeypatch):
    monkeypatch.setattr(telegram_order.learning_memory,'approved_rules',lambda:[{
        'kind':'policy','rule_key':'telegram_creation_excluded_contacts','payload':{'value':['bouchaib']}}])
    async def forbidden(*args, **kwargs):
        raise AssertionError('Bouchaib must not trigger creation preparation')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'Contact : Bouchaib\n04 t 12'}],'telegram:bouchaib'))
    assert 'suspendue' in reply


def test_modification_alone_never_creates_another_order(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    async def forbidden(*args,**kwargs):
        raise AssertionError('A modification cannot become another creation')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    history=[{'role':'user','content':'Contact : Wiam\nModification au niveau de cette commande :\n(C10121\n20 sacs CPJ45\n50 transport)\nPlus 40 sacs CPJ45'}]
    reply=asyncio.run(telegram_order.handle(history,'telegram:modification'))
    assert 'numéro de commande Sage' in reply
    with creation.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0


def test_user_withdrawn_request_is_blocked_before_analysis(monkeypatch):
    monkeypatch.setattr(telegram_order.learning_memory,'approved_rules',lambda:[{'kind':'policy','rule_key':'creation_excluded_owners','payload':{'value':['day:withdrawn']}}])
    async def forbidden(*args,**kwargs):raise AssertionError('Withdrawn request must not be prepared')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'Client C08101'}],'day:withdrawn'))
    assert 'suspendue' in reply


def test_mixed_clients_cannot_reach_sql_creation(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    async def forbidden(*args,**kwargs):raise AssertionError('Mixed clients cannot be analyzed as one order')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'C10121 : 20 sacs CPJ45\nC09328 : briques et200transport'}],'telegram:mixed'))
    assert 'Plusieurs clients' in reply


def test_missing_goods_cannot_be_replaced_by_transport_only(tmp_path,monkeypatch):
    monkeypatch.setattr(creation,'LEDGER',tmp_path/'orders.sqlite3')
    async def prepare(*args,**kwargs):
        return {'client':{'BPCNUM_0':'C08080'},'lines':[{'article':'MANTD','quantity':1,'price':250},{'article':'MANTD','quantity':1,'price':50}], 'missing':[], 'missing_fields':[], 'delivery':'2026-11-09','intent':'order'}
    monkeypatch.setattr(telegram_order,'prepare',prepare)
    def forbidden(*args,**kwargs):raise AssertionError('Dropped goods must prevent SQL creation')
    monkeypatch.setattr(creation,'review',forbidden)
    reply=asyncio.run(telegram_order.handle([{'role':'user','content':'5000 kg RAB12\nTrs250dh\nBrik said C08080\nTrs50dh'}],'telegram:lost-goods'))
    assert 'marchandises' in reply
