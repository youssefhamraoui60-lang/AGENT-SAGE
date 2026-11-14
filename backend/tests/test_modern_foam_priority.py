"""Modern Foam incident regressions, ERP writes excluded."""
from copy import deepcopy
import pytest
from app.services import conversation_chat as chat, chat_fast_extract as fast, chat_turns
from app.services.chat_model import Delta


def draft():
    return {'articles':[dict(id=str(i),designation=f'Modern foam boards {letter} XPS 4 CM',code_article=f'MFB-{letter}-XPS-40',categorie='AR',unite='M2',site=None,fournisseur_nom='Modern for Foam and Plastic',sources={},proposals={}) for i,letter in enumerate('AB',1)],'pending':[{'field':'site','text':'Site ?'},{'field':'categorie','text':'Cat?gorie ?'}]}


def test_site_and_supplier_same_turn():
    text='sur le site 201 ET POUR LE FORNISEUR JE VEUX PAS DE FORNISEUR'
    delta,_=fast.extract(text,draft())
    assert delta is not None
    after=chat.merge(draft(),delta,text)
    assert len(after['articles'])==2
    assert all(a['site']=='201' and a['unite']=='M2' and a.get('supplier_intent')=='none' for a in after['articles'])


@pytest.mark.parametrize('text',['DONNER LES NOM DES CHQGE CATIGORIER','lisert les nom des de chque cztigorier pour mois je peux dire q uille code catigorier','Liste les noms des catégories','Donne les catégories'])
def test_typo_category_catalogue_is_readonly(text):
    before=draft()
    turn=chat_turns.analyse(text,before)
    assert turn.readonly and turn.lookups.get('catalogue_categories')
    delta,_=fast.extract(text,before)
    assert delta is not None
    assert chat.merge(before,delta,text)['articles']==before['articles']


def test_bare_category_answer_preserves_context():
    before=draft()
    for a in before['articles']: a.update(site='201',supplier_intent='none',fournisseur_nom=None)
    delta,_=fast.extract('AGEN',before)
    assert delta is not None
    after=chat.merge(before,delta,'AGEN')
    assert all(a['categorie']=='AGEN' and a['site']=='201' and a['unite']=='M2' and a['supplier_intent']=='none' for a in after['articles'])


def test_catalogue_response_has_no_silent_21_limit():
    value=draft();value['catalogue_results']={'ok':True,'rows':[{'TCLCOD_0':f'C{i:03}','TCLDES_0':f'Libellé {i}'} for i in range(35)]}
    answer=chat.compose(value)
    assert 'C034 : Libellé 34' in answer
    assert 'limitée à 21' not in answer


@pytest.mark.parametrize('field,value,text',[('site','202','site 202'),('site','209','site 209'),('unite','UN','unité UN'),('categorie','NEG','catégorie NEG'),('code_fournisseur','F1025','code fournisseur F1025')])
def test_successive_corrections_change_only_requested_field(field,value,text):
    before=draft()
    for a in before['articles']: a.update(site='201',supplier_intent='none',fournisseur_nom=None)
    delta,_=fast.extract(text,before)
    after=chat.merge(before,delta,text)
    assert all(a[field]==value for a in after['articles'])
    for old,new in zip(before['articles'],after['articles']):
        for unchanged in {'site','categorie','unite'}-{field}: assert old[unchanged]==new[unchanged]


def test_supplier_answer_does_not_replace_pending_category():
    before=draft()
    turn=chat_turns.analyse('F1025',before)
    assert turn.values=={'code_fournisseur':'F1025'}


def test_explicit_catalogue_request_bypasses_reference_cache(monkeypatch):
    from app.services import chat_tools as tools
    calls=[]
    def worker(batch):
        calls.extend(batch)
        return {'results':[{'id':c['id'],'ok':True,'rows':[{'TCLCOD_0':'AGEN','TCLDES_0':'AGENCEMENTS ET AMENAGEMENTS'}]} for c in batch]}
    monkeypatch.setattr(tools,'_worker',worker)
    monkeypatch.setattr(tools,'_CACHE',{})
    plan=tools.Plan();plan.add('get_article_categories',Category='',Label='',Site='')
    tools.pooled(plan.calls);tools.pooled(plan.calls)
    assert len(calls)==2


# Reuse a fixture that creates and drops only its own local PostgreSQL schema.
from test_conversation_chat import fixture, create, send, initial, FakeSQL
import os


@pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Isolated local PG required')
def test_complete_modern_foam_conversation_persists_and_checks_categories(fixture,monkeypatch):
    c,q=fixture
    calls=[]
    def sql(calls_in):
        calls.extend(deepcopy(calls_in));out=FakeSQL()(calls_in)
        for call in calls_in:
            if call['tool']=='get_article_categories':
                code=call['args'].get('Category')
                rows=[{'TCLCOD_0':x,'TCLDES_0':label,'STOFCY_0':'','STU_0':'M2'} for x,label in [('AGEN','Agencement'),('NEG','Négoce')] if not code or code==x]
                out[call['id']]['rows']=rows
        return out
    monkeypatch.setattr(chat.tools,'run',sql)
    text='Bonjour, j’ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR.'
    s=send(c,q,create(c),text,initial())
    transcript=[]
    for text in ['sur le site 201 ET POUR LE FORNISEUR JE VEUX PAS DE FORNISEUR','DONNER LES NOM DES CHQGE CATIGORIER','lisert les nom des de chque cztigorier pour mois je peux dire q uille code catigorier','AGEN','AGEN']:
        delta,_=fast.extract(text,s['state'])
        s=send(c,q,s,text,delta.model_dump(exclude_none=True))
        answer=s['messages'][-1]['content']
        assert 'Sur quel site souhaitez-vous' not in answer
        assert '| Site déclaré |' in answer
        for a in s['state']['articles']:
            assert a['site']=='201' and a['unite']=='M2' and a['supplier_intent']=='none'
        assert not any(x['field']=='site' for x in s['state']['pending'])
        if 'CATIGORIER' in text or 'cztigorier' in text:
            assert s['state']['catalogue_results']['ok']
            assert s['state']['catalogue_results']['rows'][0]['TCLDES_0']=='Agencement'
            assert 'AGEN : Agencement' in answer and 'NEG : Négoce' in answer
        transcript.append({'user':text,'assistant':answer,'state':deepcopy(s['state'])})
    assert all(a['categorie']=='AGEN' and a['checks']['verified']['categorie'] for a in s['state']['articles'])
    for a in s['state']['articles']:
        workflow=a['checks']['article_site_workflow']
        assert workflow['site']=='201' and workflow['separate_approval_required']
        assert not workflow['fields_verified'] and not workflow['creation_executed']
        assert not workflow['connector_scope_supported']
    assert any(call['tool']=='get_article_categories' and call['args'].get('Category')=='AGEN' for call in calls)
    r=c.get('/api/v1/chat/conversations/'+s['id']);assert r.status_code==200
    assert r.json()['state']['articles']==s['state']['articles']
    from pathlib import Path
    import json
    target=Path(__file__).resolve().parents[2]/'tests/ai-evaluation/reports/modern-foam-replay.json'
    target.write_text(json.dumps({'source':'isolated PostgreSQL + simulated Sage SQL, no writes','turns':transcript},ensure_ascii=False,indent=2),encoding='utf-8')
