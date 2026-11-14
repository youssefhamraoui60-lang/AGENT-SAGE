import asyncio
import json
from contextlib import closing

import telegram_order
import creation


def test_missing_historical_price_is_saved_blank_without_prompt_or_write(tmp_path, monkeypatch):
    monkeypatch.setattr(creation, 'LEDGER', tmp_path / 'draft.sqlite3')
    details = {'intent': 'order', 'client': {'BPCNUM_0': 'C10370'},
               'lines': [{'article': 'PF-TP16X20', 'quantity': 5, 'price': None}],
               'delivery': '2026-11-08', 'missing': ['No historical price'],
               'missing_fields': ['prix TTC PF-TP16X20']}

    async def prepare(*args, **kwargs):
        return details

    def forbidden(*args, **kwargs):
        raise AssertionError('No Sage write or review expected')

    monkeypatch.setattr(telegram_order, 'prepare', prepare)
    monkeypatch.setattr(creation, 'review', forbidden)
    monkeypatch.setattr(creation, 'confirm', forbidden)
    reply = asyncio.run(telegram_order.handle([], 'telegram:test:message'))
    assert 'Manque' not in reply
    assert 'laissés vides' in reply
    assert len(telegram_order.short(reply)) <= 200
    with closing(creation.connection()) as db:
        saved = json.loads(db.execute('SELECT details FROM telegram_drafts').fetchone()[0])
    assert saved['lines'][0]['price'] is None
