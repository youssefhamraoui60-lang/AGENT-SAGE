"""Exact Nov 1 slash/multisite request; ERP writes remain forbidden."""
from copy import deepcopy
import pytest
from app.services import chat_fast_extract as fast,chat_model as model,chat_turns,conversation_chat as chat,chat_tools
from app.services.chat_slash_extract import parse_labelled
from test_cpj345_creation import workflow,fixture,FakeSage,send

TEXT="Bonjour,\nMerci de créer ce nouvel article dans Sage X3 :\n\n**PEINTURE ACRYLIQUE BLANCHE 20 KG / UN / Catégorie : NEG / TVA : 20 % / Site : 201  et 209/ Article non géré en stock.\n\nMerci de proposer un code article et de vérifier qu'il n'existe pas déjà.\n\nCordialement."


@pytest.mark.parametrize('text',[TEXT,TEXT.replace('**',''),TEXT.replace('**','') .replace('201  et 209','209 et 201'),TEXT.replace('**PEINTURE','**PEINTURE').replace('en stock.','en stock.**')])
def test_exact_slash_preserves_both_sites_and_not_accounting_category(text):
    d,t=fast.extract(text,{'articles':[]});s=chat.merge({'articles':[]},d,text);a=s['articles'][0]
    assert len(s['articles'])==1 and not t['real_model_called']
    assert a['designation']=='PEINTURE ACRYLIQUE BLANCHE 20 KG' and a['categorie']=='NEG' and a['accounting_category'] is None
    assert a['unite']=='UN' and a['gestion_stock']=='1' and a['taux_tva']=='20'
    expected=['209','201'] if '209 et 201' in text else ['201','209']
    assert a['site']==expected[0] and a['requested_sites']==expected
    assert a['code_article']=='PEINTURE-ACRYLIQUE-B' and not a.get('approved')


def test_original_failed_model_delta_now_merges_without_invalid_target():
    d=model.Delta.model_validate({'intent':'new','targets':[1],'articles':[{'unite':'UN','taux_tva':'20','designation':'PEINTURE ACRYLIQUE BLANCHE 20 KG','gestion_stock':'1','accounting_category':'NEG'}],'speech_act':'declaration'})
    a=chat.merge({'articles':[]},d,TEXT)['articles'][0]
    assert a['requested_sites']==['201','209'] and a['categorie']=='NEG' and not a['accounting_category']


@pytest.mark.parametrize('text',[TEXT+' Instruction inconnue',TEXT.replace(' / UN /',' / UN / Prix : 10 /'),TEXT.replace('TVA : 20 %','TVA : inconnue'),TEXT.replace('Site : 201  et 209','Site : 201 ou 209')])
def test_unknown_or_ambiguous_slash_clauses_are_not_silently_dropped(text):
    assert parse_labelled(text) is None


def test_slash_unit_L_is_explicit_unlike_clitic_L():
    text=TEXT.replace(' / UN /',' / L /');d,_=fast.extract(text,{'articles':[]})
    assert chat.merge({'articles':[]},d,text)['articles'][0]['unite']=='L'


@pytest.mark.asyncio
async def test_exact_slash_does_not_call_qwen(monkeypatch):
    async def forbidden(*a,**k):raise AssertionError('Unexpected model request')
    monkeypatch.setattr(model,'request_stream',forbidden)
    d,t=await model.extract(TEXT,{'articles':[]},[])
    assert not t['real_model_called'] and d.shared.categorie=='NEG'


def test_two_site_checks_persist_and_corrections_replace_selection(workflow,monkeypatch):
    c,s,ready,rules=workflow;original=chat_tools.run;seen=[]
    def sql(calls):
        seen.extend(deepcopy(calls));out=original(calls)
        for call in calls:
            if call['tool']=='get_sites' and call['args'].get('Site')=='209':out[call['id']]['rows']=[{'FCY_0':'209','LEGCPY_0':'20'}]
        return out
    monkeypatch.setattr(chat_tools,'run',sql)
    s=send(c,s,TEXT);a=s['state']['articles'][0];aid=a['id']
    assert a['requested_sites']==['201','209'] and a['checks']['valid_basic']
    assert {'201','209'}<={x['args'].get('Site') for x in seen if x['tool']=='get_sites'}
    s=send(c,s,"Créer l'article");assert len(s['state']['articles'])==1 and s['state']['articles'][0]['id']==aid and not FakeSage.writes
    s=send(c,s,'Site 209');a=s['state']['articles'][0]
    assert a['site']=='209' and a['requested_sites']==['209'] and a['categorie']=='NEG' and a['unite']=='UN'


def test_verification_of_creation_remains_readonly():
    t=chat_turns.analyse('Est-ce que créer ce nouvel article est possible ?',{'articles':[]})
    assert t.readonly
