from test_chat_supplier_sql import workflow
from app.services import supplier_sql as sql

def test_duplicates_block_even_with_old_override(workflow,monkeypatch):
    state,calls,call=workflow
    def preview(values,execute=False):
        assert not execute
        return {'ok':False,'code':'sql_validation_rejected','sql_error_number':50109,
            'diagnostics':[{'duplicate_code':'F10017','duplicate_name':'Izs.Tex'}]}
    monkeypatch.setattr(sql,'run',preview)
    response=call('prepare');assert response.status_code==200
    op=response.json()['state']['partners'][0]['operation']
    assert op['status']=='blocked' and '| F10017 | Izs.Tex |' in op['validation']['message']
    assert call('approve',True).status_code==423
    assert call('execute',True).status_code==423
    assert calls==[]
