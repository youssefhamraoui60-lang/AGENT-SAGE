import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import creation
import web


@pytest.fixture
def sample():
    return {'client': {'BPCNUM_0': 'C01401', 'CUR_0': 'MAD'}, 'missing': [],
            'delivery': (datetime.now(ZoneInfo('Europe/Paris')).date() + timedelta(days=2)).isoformat(),
            'lines': [{'article': 'CPJ45', 'quantity': 20, 'price': 81, 'unit': 'SAC'}],
            'reply': 'Brouillon seulement'}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(creation, 'LEDGER', tmp_path / 'orders.sqlite3')
    monkeypatch.setattr(creation, 'permissions', lambda: {'ready': True, 'missing': []})
    calls = []

    def execute(script, payload):
        calls.append((script, payload.copy()))
        if payload.get('mode') == 'preview':
            return {'ok': True, 'rows': [{'RESULTAT': 'PREVIEW', 'PLAN_JSON': '{"client":"C01401","ttc":1620}'}]}
        if payload.get('kind') == 'receipt':
            return {'ok': True, 'rows': []}
        return {'ok': True, 'rows': [{'NUMERO_COMMANDE': '2026ARC_TEST_STUB'}]}
    monkeypatch.setattr(creation, 'run_script', execute)
    return calls


def test_confirm_once_and_no_write_on_preview(sample, ledger):
    r = creation.review('owner', sample)
    assert [p['mode'] for _, p in ledger] == ['preview']
    first = creation.confirm('owner', r['id'], human_validated=True)
    assert first['status'] == 'created'
    assert creation.confirm('owner', r['id'], human_validated=True) == first
    assert [p['mode'] for _, p in ledger] == ['preview', 'create']
    assert ledger[-1][1]['expected_plan'] == '{"client":"C01401","ttc":1620}'
    assert len(ledger[-1][1]['reference']) == 20
    assert len(r['id']) == 32


def test_creation_requires_explicit_human_validation(sample,ledger):
    r=creation.review('owner',sample)
    with pytest.raises(creation.CreationError,match='Validation humaine obligatoire'):
        creation.confirm('owner',r['id'])
    assert [p['mode'] for _,p in ledger]==['preview']


def test_telegram_handoff_requires_operator_review_and_is_account_bound(sample,ledger,monkeypatch):
    import drafts
    history=[{'role':'user','content':'Client C01401 : 20 sacs CPJ45'}]
    drafts.save('telegram-source',sample,history);code=drafts.handoff('telegram-source')
    async def fake(history,**kwargs):return sample
    monkeypatch.setattr(web,'prepare',fake);web.sessions.clear()
    with TestClient(web.app) as a,TestClient(web.app) as b:
        result=a.post('/api/sob/preparations/load',json={'code':code},headers={'X-SOB-Actor':'operator-a'})
        assert result.status_code==200 and result.json()['review']
        assert all(payload.get('mode')=='preview' for _,payload in ledger)
        assert b.post('/api/sob/preparations/load',json={'code':code},headers={'X-SOB-Actor':'operator-b'}).status_code==404


def test_creation_always_replaces_trs_with_mantd(sample, ledger):
    sample['lines'] = [{'article': 'TRS', 'quantity': 50, 'price': 50}]
    payload = creation.build_payload(sample)
    assert payload['lines'][0]['article'] == 'MANTD'
    assert payload['lines'][0]['quantity'] == '1'
    assert payload['total'] == '50.00'


def test_fasm_customer_and_confirmed_pointe_articles(sample, ledger):
    sample['client']['BPCNUM_0'] = 'C10370'
    sample['lines'] = [
        {'article': 'PF-TP16X20', 'quantity': 5, 'price': 0},
        {'article': 'PF-TP08X20', 'quantity': 10, 'price': 0},
    ]
    payload = creation.build_payload(sample)
    assert payload['client'] == 'C10370'
    assert [line['article'] for line in payload['lines']] == ['PF-TP16X20', 'PF-TP08X20']
    assert payload['total'] == '0.00'


def test_customer_scope_uses_validated_references_not_two_sample_customers(sample):
    sample['client']['BPCNUM_0']='C10304'
    sample['representative']={'REPNUM_0':'REP032'}
    payload=creation.build_payload(sample)
    assert payload['client']=='C10304'
    assert payload['representative']=='REP032'


def test_owner_and_revision_and_expiry(sample, ledger):
    r = creation.review('owner', sample)
    with pytest.raises(creation.CreationError):
        creation.confirm('other-owner', r['id'])
    creation.invalidate('owner')
    with pytest.raises(creation.CreationError):
        creation.confirm('owner', r['id'], human_validated=True)
    r = creation.review('owner', sample)
    with creation.connection() as db:
        db.execute('UPDATE reviews SET expires=0 WHERE id=?', (r['id'],))
    with pytest.raises(creation.CreationError):
        creation.confirm('owner', r['id'], human_validated=True)
    assert all(p.get('mode') != 'create' for _, p in ledger)


def test_missing_rights_never_writes(sample, ledger, monkeypatch):
    r = creation.review('owner', sample)
    monkeypatch.setattr(creation, 'permissions', lambda: {'ready': False, 'missing': ['INSERT']})
    with pytest.raises(creation.CreationError, match='Droits'):
        creation.confirm('owner', r['id'], human_validated=True)
    assert all(p.get('mode') != 'create' for _, p in ledger)


def test_ambiguous_result_only_reconciles(sample, ledger, monkeypatch):
    r = creation.review('owner', sample)
    original = creation.run_script
    attempts = []

    def lost(script, payload):
        if payload.get('mode') == 'create':
            attempts.append(payload)
            raise creation.CreationError('timeout')
        return original(script, payload)
    monkeypatch.setattr(creation, 'run_script', lost)
    with pytest.raises(creation.CreationError):
        creation.confirm('owner', r['id'], human_validated=True)
    with pytest.raises(creation.CreationError, match='incertain'):
        creation.confirm('owner', r['id'], human_validated=True)
    assert len(attempts) == 1
    monkeypatch.setattr(creation, 'run_script', lambda *args: {'ok': True, 'rows': [{'SOHNUM_0': 'RECOVERED_STUB'}]})
    assert creation.confirm('owner', r['id'], human_validated=True)['number'] == 'RECOVERED_STUB'


def test_known_rollback_does_not_retry(sample, ledger, monkeypatch):
    r = creation.review('owner', sample)
    monkeypatch.setattr(creation, 'run_script', lambda *args: {'ok': False, 'code': 62008})
    with pytest.raises(creation.CreationError, match='annulée'):
        creation.confirm('owner', r['id'], human_validated=True)
    with pytest.raises(creation.CreationError, match='remplacé'):
        creation.confirm('owner', r['id'], human_validated=True)


@pytest.mark.parametrize('change', ['client', 'article', 'qty', 'price', 'missing', 'delivery'])
def test_incomplete_or_unsupported_never_creates(sample, ledger, change):
    if change == 'client': sample['client']['BPCNUM_0'] = 'INVALID;SQL'
    if change == 'article': sample['lines'][0]['article'] = 'INVALID;SQL'
    if change == 'qty': sample['lines'][0]['quantity'] = -1
    if change == 'price': sample['lines'][0]['price'] = float('nan')
    if change == 'missing': sample['missing'] = ['unit mismatch']
    if change == 'delivery': sample['delivery'] = None
    with pytest.raises(creation.CreationError):
        creation.review('owner', sample)
    assert ledger == []


def test_api_no_chat_creation_stale_owner_csrf_and_receipt(sample, ledger, monkeypatch):
    async def fake(history, **kwargs):
        return sample
    monkeypatch.setattr(web, 'prepare', fake)
    web.sessions.clear()
    with TestClient(web.app) as a, TestClient(web.app) as b:
        result = a.post('/api/sob/chat', json={'message': 'ma commande'})
        assert result.status_code == 200
        rid = result.json()['review']['id']
        assert ledger[-1][1]['mode'] == 'preview'
        assert b.post('/api/sob/orders/confirm', json={'review_id': rid}).status_code == 409
        assert a.post('/api/sob/orders/confirm', json={'review_id': rid}, headers={'origin': 'https://other.example'}).status_code == 403
        newer = a.post('/api/sob/chat', json={'message': 'corrige'})
        assert a.post('/api/sob/orders/confirm', json={'review_id': rid}).status_code == 409
        rid = newer.json()['review']['id']
        created = a.post('/api/sob/orders/confirm', json={'review_id': rid})
        assert created.status_code == 200
        assert a.post('/api/sob/orders/confirm', json={'review_id': rid}).json() == created.json()
        assert a.get('/api/sob/conversation').json()['receipt']['number'] == '2026ARC_TEST_STUB'
        assert a.post('/api/sob/chat', json={'message': 'merci'}).status_code == 409
        assert sum(p.get('mode') == 'create' for _, p in ledger) == 1
