"""User-selected units, reference labels, and conversion safety. No Sage writes."""
import sys,copy
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import article_sql as sql,sage_crud as crud,unit_references as units,conversation_tools as engine
from app.services.modification_resolvers import UnitResolver
from app.core.config import settings
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create
from test_article_direct_sql import article,schema

ROWS=[{'UOM_0':'M2','label':'Mètre carré'},{'UOM_0':'M3','label':'Mètre cube'},{'UOM_0':'RLX','label':'Rolleauux'},{'UOM_0':'UN','label':'Unité'}]

def test_no_category_default_can_supply_missing_stock_unit(monkeypatch):
    draft=article();draft.pop('unite')
    monkeypatch.setattr(sql,'catalog',lambda *a,**k:pytest.fail('Unit must be requested before preview'))
    with pytest.raises(crud.CrudError,match='unité de stock'):sql.article_plan(draft)

@pytest.mark.parametrize('query,code',[('metr carr','M2'),('mètre carré','M2'),('m2','M2'),('rouleau','RLX')])
def test_units_search_real_labels_and_typos(query,code):
    choices=UnitResolver().search(query,ROWS)
    assert choices[0]['code']==code
    state={'unit_choices':{'ok':True,'folder':'TEST','query':query,'choices':choices}}
    assert units.proof(code,'mon uniter est '+query,state,'TEST')['value']==code
    assert units.proof(code,query,state,'OB') is None

def test_ambiguous_units_need_selection():
    choices=UnitResolver().search('metre',[{'UOM_0':'M2','label':'Mètre carré'},{'UOM_0':'M3','label':'Mètre cube'}])
    state={'unit_choices':{'ok':True,'folder':'TEST','query':'metre','choices':choices}}
    assert units.proof('M2','mon unité metre',state,'TEST') is None

def test_exact_litre_wins_over_centilitre_and_millilitre_fragments():
    rows=[{'UOM_0':'L','label':'Litre'},{'UOM_0':'CL','label':'Centilitre'},{'UOM_0':'DL','label':'Décilitre'},{'UOM_0':'ML','label':'Millilitre'}]
    choices=UnitResolver().search('litre',rows)
    state={'unit_choices':{'ok':True,'folder':'TEST','query':'litre','choices':choices}}
    assert units.proof('L','OUI MAIS POUR LE VENT litre',state,'TEST')['value']=='L'
    assert units.proof('CL','OUI MAIS POUR LE VENT litre',state,'TEST') is None
    state['unit_choices']['choices'].append({'code':'LTR','label':'Litre','score':1})
    assert units.proof('L','vente litre',state,'TEST') is None

def test_literal_stock_sale_and_coefficient_survive_a_wrong_model_sale_unit():
    from app.services.article_sql_dialogue import enrich
    a=article(unite='UN',unite_vente='UN')
    enrich({'articles':[a]},'le unter UN dans le vent L LA COFSSION EST 1000')
    assert a['unite']=='UN' and a['unite_vente']=='L' and a['coefficient_vente_declare']=='1000'
    data=schema();data['units'].append({'UOM_0':'L'})
    with pytest.raises(crud.CrudError) as exc:sql.article_plan(a,data)
    assert '1 L = 1000 UN' in exc.value.code and '1 UN = 1000 L' in exc.value.code

def test_sale_unit_label_does_not_replace_stock_with_de():
    from app.services.article_sql_dialogue import enrich
    a=article(unite='UN',unite_vente='L')
    enrich({'articles':[a]},'Unité de vente est L')
    assert a['unite']=='UN' and a['unite_vente']=='L'

def test_reference_alias_completes_same_creation_and_survives_enrichment(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,_,_,attempts,_=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','CAF UNIT TEST'),fact('categorie','AVNS')])),say('Quelle unité de stock souhaitez-vous ?')])
    s=send(c,create(c),'créer article CAF UNIT TEST, catégorie AVNS')
    a=s['state']['articles'][0];identifier=a['id']
    assert not a.get('unite') and a['operation']['status']=='blocked'
    from app.services import chat_tools
    old=chat_tools.run
    monkeypatch.setattr(chat_tools,'run',lambda calls:{calls[0]['id']:{'ok':True,'folder':'TEST','rows':copy.deepcopy(ROWS)}} if calls[0]['tool']=='search_units' else old(calls))
    q.extend([native(call('search_units',query='metr carr')),native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('unite','M2','mon uniter est metr carr')])),say('M2 conservé pour vérification.')])
    s=send(c,s,'mon uniter est metr carr')
    a=s['state']['articles'][0]
    assert a['id']==identifier and a['unite']=='M2'
    assert a['field_provenance']['unite']['source']=='verified_unit_label'
    assert all(not attempt['execute'] for attempt in attempts)

def test_stock_unit_failure_explains_conversion_not_category():
    from test_modifications import data,draft
    from app.services import erp_modification as mod
    fixture=data();view=fixture['article']
    view['units'].append({'UOM_0':'M2'})
    with pytest.raises(crud.CrudError) as exc:mod.build(draft(stock_unit='M2',sale_unit={'code':'RLX'}),fixture['schema'],view)
    assert 'conversion' in exc.value.code and 'incompatible avec la catégorie' not in exc.value.code

def test_sale_unit_string_becomes_typed_change_and_keeps_stock(native_chat):
    c,q,_,_,attempts,_=native_chat
    q.extend([native(call('prepare_modification',resource='article',code='TESTART201',changes=[{'field':'stock_unit','value':'M2','evidence':'stock M2'},{'field':'sale_unit','value':'RLX','evidence':'vente RLX'}])),say('Changements conservés pour vérification.')])
    s=send(c,create(c),'modifie article existant TESTART201 : stock M2 et vente RLX')
    d=s['state']['modification_drafts'][-1]
    assert d['changes']=={'stock_unit':'M2','sale_unit':{'code':'RLX'}}
    assert all(not attempt['execute'] for attempt in attempts)
