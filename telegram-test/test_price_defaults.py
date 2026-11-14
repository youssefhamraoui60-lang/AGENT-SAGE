import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import prepare as module
from app.core.config import settings
from app.services import ai_provider


@pytest.mark.parametrize('explicit,historical,expected', [(None, 82, 82), (None, None, 0), (81, 82, 81), (0, 82, 0)])
def test_price_and_delivery_defaults(monkeypatch, explicit, historical, expected):
    calls = []
    draft = {'client': 'C01401', 'representative': None, 'intent': 'order', 'delivery': None,
             'question': '', 'lines': [{'article': 'CPJ45', 'quantity': 20, 'unit': 'SAC', 'price': explicit}]}

    async def complete(*args, **kwargs):
        return {'message': {'content': json.dumps(draft)}}

    def lookup(kind, code, client=None):
        if kind == 'client':
            return [{'BPCNUM_0': 'C01401', 'BPCNAM_0': 'Client', 'CUR_0': 'MAD', 'REP_0': 'REP1', 'VACBPR_0': 'MAR'}]
        if kind == 'article':
            return [{'ITMREF_0': 'CPJ45', 'ITMDES1_0': 'Ciment', 'SAU_0': 'SAC', 'VACITM_0': 'T20', 'SITE_OK': 1}]
        calls.append((kind, code, client))
        return [] if historical is None else [{'PRICE_TTC': historical, 'SOHNUM_0': 'HISTORY_TEST'}]

    monkeypatch.setattr(settings, 'ai_provider', 'deepseek')
    monkeypatch.setattr(ai_provider, 'complete', complete)
    monkeypatch.setattr(module, 'lookup', lookup)
    result = asyncio.run(module.prepare([{'role': 'user', 'content': '20 sacs CPJ45'}], details=True))
    assert result['lines'][0]['price'] == expected
    assert result['delivery'] == datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()
    assert bool(calls) == (explicit is None)
    if calls:
        assert calls[0] == ('last_price', 'CPJ45', 'C01401')
    assert 'prix TTC CPJ45' not in result['missing_fields']
    assert result['lines'][0]['price_defaulted_zero'] == (explicit is None and historical is None)


def test_unknown_article_with_quantity_requests_information(monkeypatch):
    async def complete(*args,**kwargs):
        return {'message':{'content':json.dumps({'client':None,'intent':'order','lines':[{'article':None,'quantity':60,'price':None,'unit':None}]})}}
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lambda *args,**kwargs:[])
    result=asyncio.run(module.prepare([{'role':'user','content':'60 // ?'}],details=True))
    assert result['lines']==[]
    assert 'article article non précisé' in result['missing_fields']


@pytest.mark.parametrize('explicit_code', [False, True])
def test_verified_client_resolution_is_not_discarded_by_second_name_ranking(monkeypatch, explicit_code):
    draft={'client':'Houssine swalam','intent':'order','lines':[]}
    async def complete(*args, **kwargs):
        return {'message':{'content':json.dumps(draft)}}
    searched=[]
    def lookup(kind, code, *args, **kwargs):
        searched.append((kind,code))
        return [{'BPCNUM_0':'C02287','BPCNAM_0':'HOUSSINE SOUALEM','CUR_0':'MAD','REP_0':'REP003','VACBPR_0':'MAR'}] if kind=='client' else []
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup)
    text='Houssine swalam'+(' C02287' if explicit_code else '')
    result=asyncio.run(module.prepare([{'role':'user','content':text}],details=True))
    assert result['client']['BPCNUM_0']=='C02287'
    assert ('client','C02287' if explicit_code else 'Houssine swalam') in searched
