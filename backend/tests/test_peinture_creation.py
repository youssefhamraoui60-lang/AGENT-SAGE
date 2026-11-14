"""PEINTURE regression: controlled ERP fixtures, never a real Sage write."""
from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import chat_model as model,chat_fast_extract as fast,conversation_chat as chat,chat_tools
from app.services.chat_article_requests import simple_initial
from test_cpj345_creation import workflow,fixture,FakeSage,send,act

SHORT='Merci de créer un nouvel article PEINTURE ACRYLIQUE BLANCHE 20 KG, catégorie NEG, unité UN, site 201, TVA 20 %, non géré en stock.'
EXACT='Merci de créer un nouvel article dans Sage X3, avec les informations suivantes : - Désignation : PEINTURE ACRYLIQUE BLANCHE 20 KG - Catégorie article : NEG - Unité : UN - Site : 201 - TVA : 20 % - Gestion de stock : Non géré en stock'


@pytest.mark.parametrize('text',[SHORT,EXACT,EXACT.replace(' - ','\n- ')])
def test_literal_paint_preserves_every_declared_fact(text):
    d,t=fast.extract(text,{'articles':[]});a=chat.merge({'articles':[]},d,text)['articles'][0]
    assert a['designation']=='PEINTURE ACRYLIQUE BLANCHE 20 KG'
    assert [a[k] for k in ['categorie','unite','site','taux_tva','gestion_stock']]==['NEG','UN','201','20','1']
    assert a['code_article']=='PEINTURE-ACRYLIQUE-B' and len(a['code_article'])==20
    assert not a.get('code_fournisseur') and not t['real_model_called']


def test_unknown_label_does_not_silently_drop_information():
    assert simple_initial(EXACT+' - Prix : 99') is None
    assert simple_initial(EXACT+' - Site : 202') is None


def test_narrow_qwen_schema_uses_sage_stock_enum_not_boolean_zero():
    props=model.single_article_schema(EXACT)['properties']['articles']['items']['properties']
    assert props['gestion_stock']['enum']==['1','2','3']


@pytest.mark.asyncio
async def test_complete_bullets_do_not_wait_for_qwen_queue(monkeypatch):
    async def forbidden(*a):raise AssertionError('Qwen should not be called for literal complete bullets')
    monkeypatch.setattr(model,'request_stream',forbidden)
    d,t=await model.extract(EXACT,{'articles':[]},[])
    assert not t['real_model_called'] and d.shared.gestion_stock=='1'


@pytest.fixture
def paint(workflow,monkeypatch):
    c,s,ready,rules=workflow
    original=chat_tools.run
    def sql(calls):
        values=original(calls)
        for call in calls:
            if call['tool']=='get_tax_rules':values[call['id']]['rows']=[{'VAT_0':'T20','VATRAT_0':20,'CPY_0':' ','LEG_0':' '}]
            if call['tool']=='get_tax_determination_by_vat':values[call['id']]['rows']=[{'VAT_0':'T20','VACITM_0':'T20','VACBPR_0':'MAR','ENAFLG_0':2}]
        return values
    monkeypatch.setattr(chat_tools,'run',sql)
    rules['categories']['NEG']['tax_contexts']=[{'reviewed':True,'rate':'20','site':'201','company':'20','regime':'MAR','vat_code':'T20','level':'T20','valid_from':'2026-01-01','valid_to':'2030-12-31','fields':{'ITM5_1.VACITM':['T20','','']}}]
    return c,s,ready,rules


def prepared(paint):
    c,s,ready,rules=paint;ready['value']=True;s=send(c,s,EXACT)
    assert s['state']['articles'][0]['operation']['status']=='prepared'
    return c,s,ready,rules


def test_blocked_security_is_explicit_and_does_not_send_save(paint):
    c,s,ready,rules=paint;s=send(c,s,EXACT);a=s['state']['articles'][0]
    assert a['execution']['route']=='general_test' and a['execution']['security_controls']
    assert act(c,s,'prepare').status_code==423 and not FakeSage.writes
    assert a['gestion_stock']=='1' and not a.get('operation')


def test_paint_approved_save_readback_and_optional_supplier(paint):
    c,s,ready,rules=prepared(paint);s=act(c,s,'approve',True).json();r=act(c,s,'execute',True);assert r.status_code==200,r.text
    a=r.json()['state']['articles'][0]
    assert a['outcome']['confirmed'] and a['outcome']['comparisons']['STOMGTCOD_0'] and a['outcome']['comparisons']['VACITM_0']
    assert a['outcome']['site_creation_executed'] is False and len(FakeSage.writes)==1


def test_expired_approval_does_not_save(paint):
    from app.services.chat_general_articles import PERMITS
    c,s,ready,rules=prepared(paint);s=act(c,s,'approve',True).json()
    PERMITS[s['state']['articles'][0]['id']]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert act(c,s,'execute',True).status_code==403 and not FakeSage.writes


@pytest.mark.parametrize('restriction',['stock','supplier'])
def test_conditional_business_restrictions_fail_closed(paint,restriction):
    c,s,ready,rules=paint
    if restriction=='stock':rules['categories']['NEG']['stock_management']=['2']
    else:rules['categories']['NEG']['supplier_required']=True
    ready['value']=True;s=send(c,s,EXACT);a=s['state']['articles'][0]
    assert a['operation']['status']=='blocked' and not FakeSage.writes
    assert act(c,s,'approve',True).status_code==409
    assert not a.get('code_fournisseur') and a['gestion_stock']=='1'


def test_article_site_is_not_prepared_without_parent(paint):
    c,s,ready,rules=prepared(paint)
    assert act(c,s,'site-prepare',site='201').status_code==409 and not FakeSage.writes


def test_refused_paint_save_never_claims_created(paint):
    c,s,ready,rules=prepared(paint);FakeSage.mode='refused';s=act(c,s,'approve',True).json();s=act(c,s,'execute',True).json()
    assert not s['state']['articles'][0]['outcome']['confirmed'] and len(FakeSage.writes)==1


def test_chat_html_is_not_cached_as_an_old_release():
    r=TestClient(app).get('/sage/');assert r.status_code==200
    assert 'no-store' in r.headers['cache-control']
