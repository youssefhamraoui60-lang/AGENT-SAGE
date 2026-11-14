import pytest
from app.services import conversation_tools as engine

@pytest.mark.parametrize('folder',['TEST','OB'])
def test_model_code_is_replaced_by_user_name_search_not_a_write(monkeypatch,folder):
    requests=[]
    def read(args,state,text):
        requests.append(args)
        return {'ok':True,'folder':folder,'rows':[{'BPSNUM_0':'F10030','BPRNAM_0':'AHMDE rachid'},{'BPSNUM_0':'F10043','BPRNAM_0':'Ahmde rachide'}]}
    monkeypatch.setattr(engine,'read',read)
    state={'supplier_target':folder}
    result=engine.dispatch('prepare_modification',engine.Modify(resource='supplier',code='F10043',changes=[engine.Change(field='enabled',value=False,evidence='je veux désactiver le founisseur rachide')]),state,'je veux désactiver le founisseur rachide')
    assert requests[0].name=='rachide' and requests[0].code is None
    assert result['needs_selection'] is True and result['sage_writes']==0
    assert 'F10030' in result['message'] and 'F10043' in result['message']
    assert not state.get('modification_drafts')

def test_unknown_code_without_searchable_name_returns_useful_question():
    state={}
    result=engine.dispatch('prepare_modification',engine.Modify(resource='supplier',code='F999999',changes=[]),state,'désactive cette fiche')
    assert result['needs_selection'] and result['sage_writes']==0
    assert not state.get('modification_drafts')
