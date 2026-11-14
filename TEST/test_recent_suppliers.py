import asyncio
import pytest
from app.services import conversation_tools as e,chat_tools
from app.services.sage_crud import CrudError

@pytest.mark.parametrize('folder',['TEST','OB'])
def test_recent_supplier_is_ordered_by_date_and_folder(monkeypatch,folder):
    calls=[]
    def run(batch):
        calls.extend(batch)
        return {'recent_suppliers':{'ok':True,'folder':folder,'rows':[{'BPSNUM_0':'F008','BPRNAM_0':'Récent','created_at':'2026-11-06 12:00:00.000','date_precision':'datetime','same_creation_time':1,'unknown_creation_dates':0}]}}
    monkeypatch.setattr(chat_tools,'run',run)
    r=asyncio.run(e.turn(None,None,'donner la dernire fourniseur a été créer',{'supplier_target':folder},[]))
    assert calls[0]['tool']=='get_recent_suppliers' and calls[0]['args']=={'Folder':folder,'PageSize':'1','Status':'all'}
    assert r['phase']=='supplier_recent_readonly' and 'F008' in r['reply'] and '2026-11-06' in r['reply']
    assert not r['state'].get('modification_drafts')

def test_ties_and_missing_dates_are_explicit(monkeypatch):
    monkeypatch.setattr(chat_tools,'run',lambda batch:{'recent_suppliers':{'ok':True,'folder':'TEST','rows':[{'BPSNUM_0':'F008','BPRNAM_0':'Test','created_at':'2026-11-06','date_precision':'date','same_creation_time':4,'unknown_creation_dates':2}]}})
    r=e.dispatch('get_recent_suppliers',e.RecentSuppliers(limit=1),{},'dernier fournisseur')
    assert 'impossible' in r['message'] and 'dates connues' in r['message'] and 'date seule' in r['message']

def test_wrong_folder_result_is_rejected(monkeypatch):
    monkeypatch.setattr(chat_tools,'run',lambda batch:{'recent_suppliers':{'ok':True,'folder':'TEST','rows':[]}})
    with pytest.raises(CrudError):e.dispatch('get_recent_suppliers',e.RecentSuppliers(),{'supplier_target':'OB'},'dernier fournisseur')

@pytest.mark.parametrize('limit',[0,21,1000])
def test_bounded_recent_query(limit):
    with pytest.raises(ValueError):e.RecentSuppliers(limit=limit)
