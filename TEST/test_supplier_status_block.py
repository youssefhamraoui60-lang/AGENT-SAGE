"""Status support replaces the former unsupported-operation regression."""
import copy,pytest
from test_modifications import simulated,build,draft,mark
from app.services.modification_policy import ArticleModificationPolicy
from app.services.sage_crud import CrudError

@pytest.fixture
def status_data(simulated):
    view=simulated[2]
    for key in ('partners','suppliers'):view[key][0]['ENAFLG_0']=2
    view['menus']=[{'CODFIC_0':t,'CODZONE_0':'ENAFLG','LANNUM_0':v,'LANMES_0':label} for t in ('BPARTNER','BPSUPPLIER') for v,label in ((1,'Non'),(2,'Oui'))]
    return simulated

@pytest.mark.parametrize('enabled',[True,False])
def test_supplier_status_plan_updates_both_master_records(status_data,enabled):
    for key in ('partners','suppliers'):status_data[2][key][0]['ENAFLG_0']=1 if enabled else 2
    plan=build(status_data,draft('supplier',enabled=enabled))
    assert plan['policy']['sensitive'] is True
    assert {n['table']:n['values']['ENAFLG_0'] for n in plan['nodes']}=={'BPARTNER':2 if enabled else 1,'BPSUPPLIER':2 if enabled else 1}

@pytest.mark.parametrize('active',[True,None])
@pytest.mark.parametrize('enabled',[True,False])
def test_supplier_status_blocks_open_or_unclassified_history(status_data,active,enabled):
    mark(status_data[2],'PORDER',active)
    with pytest.raises(CrudError):build(status_data,draft('supplier',enabled=enabled))

@pytest.mark.parametrize('enabled',[1,0,'oui',None])
def test_status_never_accepts_coerced_boolean(status_data,enabled):
    with pytest.raises(CrudError):build(status_data,draft('supplier',enabled=enabled))

def test_missing_menu_blocks_status(status_data):
    status_data[2]['menus']=[]
    with pytest.raises(CrudError):build(status_data,draft('supplier',enabled=False))
