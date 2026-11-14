"""Sales require a supplier link, not a principal. Plans only, no ERP writes."""
import sys,copy,asyncio
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from test_article_direct_sql import article,schema
from test_modifications import data,draft
from app.services import article_sql as sql,erp_modification as mod,sage_crud as crud,conversation_tools as engine

def fixture():
 v=data();a=v['article']['articles'][0]
 a.update(XBPS_0='',XFLGBPS_0=1,NEGSTO_0=2)
 v['article']['menus'].extend({'CODFIC_0':'ITMMASTER','CODZONE_0':field,'LANNUM_0':num,'LANMES_0':label} for field in ('XFLGBPS','NEGSTO') for num,label in ((1,'Non'),(2,'Oui')))
 return v

def test_sold_creation_requires_link_not_principal_and_checks_flag():
 with pytest.raises(crud.CrudError,match='au moins un fournisseur'):sql.article_plan(article(fournisseurs=[]),schema())
 p=sql.article_plan(article(flag_fournisseur='1'),schema())
 assert p['summary']['flag_fournisseur']==2 and p['summary']['principal']==''
 assert p['summary']['suppliers'][0]['code']=='F994'
 with pytest.raises(crud.CrudError,match='invalide'):sql.article_plan(article(flag_fournisseur='3'),schema())

def test_three_supplier_links_do_not_require_a_principal():
 v=fixture();v['article']['article_suppliers']=[{'BPSNUM_0':c} for c in ('F007','F552','F889')]
 p=mod.build(draft(supplier_flag=True),v['schema'],v['article'])
 n=next(n for n in p['nodes'] if n['table']=='ITMMASTER')
 assert n['values']['XFLGBPS_0']==2 and not n['values'].get('XBPS_0')

def test_sale_flag_is_automatic_and_requires_actual_link():
 v=fixture()
 with pytest.raises(crud.CrudError,match='au moins un fournisseur'):mod.build(draft(sale_enabled=True),v['schema'],v['article'])
 v['article']['article_suppliers']=[{'BPSNUM_0':'F007'}]
 p=mod.build(draft(sale_enabled=True),v['schema'],v['article'])
 n=next(n for n in p['nodes'] if n['table']=='ITMMASTER')
 assert n['values']['XFLGBPS_0']==2
 with pytest.raises(crud.CrudError,match='doit garder'):mod.build(draft(supplier_flag=False),v['schema'],v['article'])

def test_no_stock_article_can_disable_negative_stock_but_cannot_enable_it():
 v=fixture()
 p=mod.build(draft(allow_negative_stock=False),v['schema'],v['article'])
 assert next(n for n in p['nodes'] if n['table']=='ITMMASTER')['values']['NEGSTO_0']==1
 with pytest.raises(crud.CrudError,match='non géré'):mod.build(draft(allow_negative_stock=True),v['schema'],v['article'])

@pytest.mark.parametrize('change',[{'deactivate':True},{'accounting':'61253000'},{'tax_level':{'index':0,'code':'T10'}},{'sale_enabled':False}])
def test_requested_changes_make_readonly_plans(change):
 v=fixture();p=mod.build(draft(**change),v['schema'],v['article'])
 assert p['nodes'] and not p['policy']['history_writes']
 assert all(n['kind']=='update' for n in p['nodes'])

def test_stock_mode_conflict_is_business_validation_not_unknown_field():
 v=fixture()
 with pytest.raises(crud.CrudError,match='incompatible avec la catégorie'):mod.build(draft(stock_mode=2),v['schema'],v['article'])

def test_french_sale_and_stock_aliases_preserve_both_even_if_blocked(monkeypatch):
 captured=[]
 from app.services import modification_actions
 def prepare(d):
  captured.append(copy.deepcopy(d['changes']));d['operation']={'status':'blocked','message':'Catégorie incompatible'}
 monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
 monkeypatch.setattr(engine.settings,'sage_modification_enabled',True)
 s={'supplier_target':'TEST'}
 args=engine.Modify(resource='article',code='TESTART201',changes=[engine.Change(field='vendu',value=2,evidence='utisable dans la vente'),engine.Change(field='gestion_stock',value=2,evidence='gérer on sstock')])
 r=engine.dispatch('prepare_modification',args,s,'TESTART201 utisable dans la vente et gérer on sstock')
 assert r['ok'] and captured==[{'sale_enabled':True,'stock_mode':2}]

def test_accounting_uses_matching_chart_instead_of_confusing_generic_duplicate():
 v=fixture();a=v['article']['articles'][0]
 old=next(r for r in v['article']['accounting'] if r['ACCCOD_0'].strip()==a['ACCCOD_0'].strip())
 old['COA_0']='MAR'
 next(r for r in v['article']['accounting'] if r['ACCCOD_0'].strip()=='61253000')['COA_0']='MAR'
 v['article']['accounting'].append({**copy.deepcopy(old),'COA_0':'','source_hash':'B'*64})
 p=mod.build(draft(accounting='61253000'),v['schema'],v['article'])
 assert any(g['table']=='GACCCODE' and g['keys']['ACCCOD_0']==old['ACCCOD_0'] and g['keys']['COA_0']==old['COA_0'] for g in p['guards'])

def test_unchanged_stock_mode_does_not_compare_unrelated_category_defaults():
 v=fixture()
 with pytest.raises(crud.CrudError,match='déjà enregistrées'):mod.build(draft(stock_mode=1),v['schema'],v['article'])

def test_without_principal_does_not_mean_without_suppliers():
 from app.services.article_sql_dialogue import enrich
 a=article(fournisseurs=[{'code':'F007','reference':''},{'code':'F552','reference':''},{'code':'F889','reference':''}])
 enrich({'articles':[a]},'sans fournisseur principal')
 assert {p['code'] for p in a['fournisseurs']}=={'F007','F552','F889'}

def test_optional_principal_can_be_cleared_without_removing_link():
 v=fixture();v['article']['articles'][0]['XBPS_0']='F007'
 v['article']['article_suppliers']=[{'BPSNUM_0':'F007'}]
 p=mod.build(draft(principal_supplier=''),v['schema'],v['article'])
 n=next(n for n in p['nodes'] if n['table']=='ITMMASTER')
 assert n['values']['XBPS_0']=='' and n['values']['XFLGBPS_0']==2
 assert all(n['table']!='ITMBPS' for n in p['nodes'])

def test_single_202_modification_exemption_is_revoked_when_201_added():
 v=fixture();v['article']['sites']=[{**r,'STOFCY_0':'202'} for r in v['article']['sites']]
 with pytest.raises(crud.CrudError,match='déjà enregistrées'):mod.build(draft(sale_enabled=True),v['schema'],v['article'])
 with pytest.raises(crud.CrudError,match='au moins un fournisseur'):mod.build(draft(sale_enabled=True,add_sites=['201']),v['schema'],v['article'])
