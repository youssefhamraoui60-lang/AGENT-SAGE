"""User-supplied cleaner request: no ERP write or policy relaxation."""
from app.services import chat_fast_extract as fast,conversation_chat as chat,chat_semantics as semantics
from app.services.chat_model import Delta
import os
import pytest

TEXT='CRRER UN ARTICLES DE Nettoyant FAP-NET 1L ECO1105 LE UNITER L LE TVA 12% et le non gréer on stoque et dois dans le site 202 ET 201 ne pas de fornssieur ligé a cette articles'


def test_exact_cleaner_literal_request():
    result=fast.extract(TEXT,{'articles':[]})
    assert result is not None
    delta,proof=result;state=chat.merge({'articles':[]},delta,TEXT)
    assert len(state['articles'])==1 and not proof['real_model_called']
    a=state['articles'][0]
    assert a['designation']=='Nettoyant FAP-NET 1L ECO1105'
    assert a['unite']=='L' and a['taux_tva']=='12' and a['gestion_stock']=='1'
    assert a['requested_sites']==['202','201'] and a['supplier_intent']=='none'
    assert not a['categorie'] and not a['code_tva'] and not a['code_fournisseur']


def test_supplier_typo_is_an_explicit_omission():
    assert semantics.supplier_decision('ne pas de fornssieur ligé a cette articles')=='none'


def existing():
    return {'articles':[{'id':'a','designation':'Nettoyant FAP-NET 1L ECO1105','code_article':'NETTOYANT-FAP-NET-1L','unite':'L','categorie':'NEG','site':'202','sources':{},'proposals':{}}]}


def test_repeated_create_request_is_not_another_new_object():
    for text in ['CRER LE','pour tu reste comme ca crréer le articles derctomnet aprer mon forfirmation ok']:
        result=fast.extract(text,existing());assert result is not None
        delta,_=result;state=chat.merge(existing(),delta,text)
        assert len(state['articles'])==1 and not delta.articles and not delta.fournisseurs
        assert state['last_turn']['creation_requested'] and not state['articles'][0].get('approved')


def test_table_request_is_presentation_only():
    text='créer le articles affiche un tabe pas contaien les info de articles pas comme cette carde'
    result=fast.extract(text,existing());assert result is not None
    delta,_=result;state=chat.merge(existing(),delta,text)
    assert state['presentation']['article_view']=='table'
    assert state['articles']==existing()['articles']


from test_conversation_chat import fixture,create,FakeSQL
integration=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Isolated PostgreSQL required')


@integration
def test_cleaner_complete_conversation_and_distinct_site_checks(fixture,monkeypatch):
    c,_=fixture;s=create(c);calls=[]
    async def extract(text,state,*args):
        result=fast.extract(text,state);assert result is not None;return result
    monkeypatch.setattr(chat.model,'extract',extract)
    def sql(batch):calls.extend(batch);return FakeSQL()(batch)
    monkeypatch.setattr(chat.tools,'run',sql)
    for text in [TEXT,'NEG','pour tu reste comme ca crréer le articles derctomnet aprer mon forfirmation ok','créer le articles affiche un tabe pas contaien les info de articles pas comme cette carde']:
        r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text
        s=r.json();a=s['state']['articles'][0]
        assert len(s['state']['articles'])==1 and not s['state'].get('partners')
        assert a['requested_sites']==['202','201'] and a['supplier_intent']=='none'
        assert a['unite']=='L' and a['taux_tva']=='12' and a['gestion_stock']=='1'
        assert not a.get('approved') and not a.get('operation')
        checks=a['checks']['requested_site_checks']
        assert {p['site'] for p in checks if p['exists']}=={'202','201'}
        assert not any(q['field'] in ('site','code_fournisseur') for q in s['state']['pending'])
    assert s['state']['presentation']['article_view']=='table'
    assert {x['args']['Site'] for x in calls if x['tool']=='get_article_site'}=={'202','201'}
    assert a['categorie']=='NEG' and a['code_tva'] is None


@integration
def test_unknown_secondary_site_blocks_validation_without_losing_it(fixture,monkeypatch):
    c,_=fixture;s=create(c)
    async def extract(text,state,*args):return fast.extract(text,state)
    monkeypatch.setattr(chat.model,'extract',extract)
    def sql(batch):
        results=FakeSQL()(batch)
        for call in batch:
            if call['tool']=='get_sites' and call['args'].get('Site')=='999':results[call['id']]['rows']=[]
        return results
    monkeypatch.setattr(chat.tools,'run',sql)
    text=TEXT.replace('202 ET 201','202 ET 999')
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text
    a=r.json()['state']['articles'][0]
    assert a['requested_sites']==['202','999']
    assert 'unknown:requested_site:999' in a['checks']['errors'] and not a['checks']['valid_basic']
