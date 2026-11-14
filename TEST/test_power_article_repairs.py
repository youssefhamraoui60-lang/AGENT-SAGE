import asyncio,copy
import pytest
from test_modifications import simulated,build,draft
from app.services import conversation_tools as e,erp_modification as mod,supplier_tasks
from app.services.sage_crud import CrudError
from app.services.modification_resolvers import CategoryResolver

def test_article_tax_question_returns_rates_instead_of_site_only(monkeypatch):
    view={'articles':[{'ITMREF_0':'A123','ITMDES1_0':'Article','VACITM_0':'T20','ACCCOD_0':'STD'}],'sites':[],
          'tax_determinations':[{'VACITM_0':'T20','VACBPR_0':'MAR','VAT_0':'T20'}],'taxes':[{'VAT_0':'T20','VATRAT_0':'20.000'}]}
    monkeypatch.setattr(mod,'snapshot',lambda *args,**kwargs:copy.deepcopy(view))
    s={'articles':[{'code_article':'A123'}]}
    r=asyncio.run(e.turn(None,None,'donne moi le tva actiale de cette article A123',s,[]))
    assert r['phase']=='article_attribute_read' and 'T20' in r['reply'] and '20.000' in r['reply']
    assert r['state']['tool_orchestration']['sage_writes']==0

def test_supplier_accounting_code_is_exposed_as_a_code(monkeypatch):
    monkeypatch.setattr(supplier_tasks,'read_record',lambda code:{'BPRNAM_0':'Fournisseur','ACCCOD_0':'STD','BPSNUM_0':code})
    r=e.read(e.Read(resource='supplier',code='F007'),{},'quel code comptable du fournisseur F007')
    assert r['fields']['code_comptable']=='STD' and 'Code comptable : STD' in r['message']
    assert 'distinct' in r['message']

@pytest.mark.parametrize('field,column',[('allow_negative_stock','NEGSTO_0'),('supplier_flag','XFLGBPS_0')])
@pytest.mark.parametrize('enabled',[True,False])
def test_validated_article_flags_create_reviewable_plan(simulated,field,column,enabled):
    view=simulated[1];a=view['articles'][0];a['STOMGTCOD_0']=2;a[column]=1 if enabled else 2
    view['menus'].extend({'CODFIC_0':'ITMMASTER','CODZONE_0':column[:-2],'LANNUM_0':v,'LANMES_0':label} for v,label in ((1,'Non'),(2,'Oui')))
    if field=='supplier_flag':view['article_suppliers']=[{'BPSNUM_0':'F007'}];a['XBPS_0']='F007'
    plan=build(simulated,draft(**{field:enabled}))
    assert any(n['values'].get(column)==(2 if enabled else 1) for n in plan['nodes'])

def test_flag_without_verified_menu_is_blocked(simulated):
    with pytest.raises(CrudError):build(simulated,draft(allow_negative_stock=False))

def test_selected_supplier_names_can_be_linked_without_literal_repeated_code(monkeypatch):
    from app.services import modification_actions
    monkeypatch.setattr(modification_actions,'prepare_draft',lambda d:d.update(operation={'status':'prepared'}))
    state={'tool_read_results':[{'ok':True,'folder':'TEST','rows':[{'BPSNUM_0':'F007','BPRNAM_0':'CIMAT'},{'BPSNUM_0':'F889','BPRNAM_0':'NOVACIM'}]}]}
    text='lier les fournisseurs CIMAT et F889 à A123'
    result=e.dispatch('prepare_modification',e.Modify(resource='article',code='A123',changes=[e.Change(field='fournisseurs',value=['F007','F889'],evidence=text)]),state,text)
    assert result['changes']['add_suppliers']==[{'code':'F007','reference':''},{'code':'F889','reference':''}]
    assert result['sage_writes']==0

@pytest.mark.parametrize('query',['marchndise','marchondise','marchandise'])
def test_merchandise_typos_propose_negoce(query):
    choices=CategoryResolver().search(query,[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':''},{'TCLCOD_0':'MATB','TCLDES_0':'MATERIEL DE BUREAU','STOFCY_0':''}])
    assert choices[0]['code']=='NEG'
