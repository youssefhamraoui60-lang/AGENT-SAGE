import asyncio
import pytest
from app.services import conversation_tools as e,chat_tools
from app.services.sage_crud import CrudError

@pytest.mark.parametrize('folder',['TEST','OB'])
def test_supplier_list_is_scoped_paginated_and_readonly(monkeypatch,folder):
    calls=[]
    def run(batch):
        calls.extend(batch)
        return {'supplier_list':{'ok':True,'folder':folder,'rows':[{'BPSNUM_0':f'F{i}','BPRNAM_0':'Nom | test','supplier_active':1,'partner_active':1,'total_count':3} for i in range(3)]}}
    monkeypatch.setattr(chat_tools,'run',run)
    state={'supplier_target':folder}
    result=e.dispatch('list_suppliers',e.SupplierList(status='inactive',page_size=2),state,'liste les fournisseurs désactivés')
    assert result['folder']==folder and len(result['rows'])==2 and result['has_more'] and result['sage_writes']==0
    assert calls[0]['args']=={'Folder':folder,'Status':'inactive','Offset':'0','PageSize':'2'}
    assert state['active_supplier_task']=='control' and not state.get('modification_drafts')
    assert 'Nom / test' in result['message']

def test_supplier_list_rejects_cross_folder_result(monkeypatch):
    monkeypatch.setattr(chat_tools,'run',lambda calls:{'supplier_list':{'ok':True,'folder':'TEST','rows':[]}})
    with pytest.raises(CrudError):e.dispatch('list_suppliers',e.SupplierList(),{'supplier_target':'OB'},'liste fournisseurs')

def test_exact_user_phrase_and_next_page_do_not_need_ai(monkeypatch):
    calls=[]
    def run(batch):
        calls.extend(batch)
        return {'supplier_list':{'ok':True,'folder':'TEST','rows':[{'BPSNUM_0':f'F{i}','BPRNAM_0':'Test','supplier_active':1,'partner_active':1,'total_count':20} for i in range(11)]}}
    monkeypatch.setattr(chat_tools,'run',run)
    r=asyncio.run(e.turn(None,None,'lister les founisseur qui désactive',{},[]))
    assert r['phase']=='supplier_list_readonly' and calls[0]['args']['Status']=='inactive'
    r=asyncio.run(e.turn(None,None,'page suivante',r['state'],[]))
    assert calls[1]['args']['Offset']=='10' and r['state']['supplier_list']['page']==2

@pytest.mark.parametrize('values',[{'page':0},{'page_size':51},{'status':'SQL'}])
def test_model_cannot_request_unbounded_or_arbitrary_list(values):
    with pytest.raises(ValueError):e.SupplierList(**values)
