import pytest,asyncio
from app.services.article_intake import parse
from app.services import ai_provider
from app.services import conversation_tools as engine
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create


@pytest.mark.parametrize('answer',['AVT','avt','PDRV','Habillements et vêtements de travail','Négoce'])
def test_category_reply_uses_actual_presented_choices(answer):
    choices=[{'code':'AVT','label':'Habillements et vêtements de travail'},{'code':'PDRV','label':'Pièce de rechange Vendable'},{'code':'NEG','label':'Négoce'}]
    state={'articles':[{'id':'stable','designation':'CAF 77H','dossier_cible':'TEST','category_options':{'folder':'TEST','choices':choices}}]}
    result=parse(answer,state)
    assert result['target_id']=='stable' and result['category_label']==answer


def test_category_choices_from_another_folder_are_not_used():
    assert parse('AVT',{'supplier_target':'OB','articles':[{'id':'stable','designation':'CAF','category_options':{'folder':'TEST','choices':[{'code':'AVT','label':'Clothing'}]}}]}) is None


@pytest.mark.parametrize('legacy',[False,True])
def test_exact_caf77h_avt_without_provider(native_chat,monkeypatch,legacy):
    from app.services import article_sql,conversation_chat
    import json,copy
    from pathlib import Path
    schema=json.loads((Path(__file__).parent/'fixtures/article-sql-schema.json').read_text())
    category=copy.deepcopy(schema['categories'][0]);category.update(TCLCOD_0='AVT',TCLDES_0='Habillements et vêtements de travail',STOFCY_0='',ACCCOD_0='')
    schema['categories']=[row for row in schema['categories'] if row['TCLCOD_0'].strip()!='AVT']
    schema['categories'].append(category)
    monkeypatch.setattr(article_sql,'catalog',lambda *a,**kw:copy.deepcopy(schema))
    async def forbidden(*a,**kw):raise AssertionError('Selecting a presented category needs no model')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    monkeypatch.setattr(conversation_chat.model,'extract',forbidden)
    c,q,requests,reads,attempts,fault=native_chat
    s=send(c,create(c),"bonjour créer l'articles CAF 77H")
    identifier=s['state']['articles'][0]['id']
    if legacy:
        from app.services import business_store
        from psycopg.types.json import Jsonb
        s['state']['articles'][0].pop('category_options',None)
        with business_store.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(s['state']),s['id']))
    s=send(c,s,'AVT')
    a=s['state']['articles'][0]
    assert len(s['state']['articles'])==1 and a['id']==identifier
    assert a['designation']=='CAF 77H' and a['categorie']=='AVT'
    assert 'services IA' not in s['messages'][-1]['content']
    assert not requests and all(not x['execute'] for x in attempts)


def test_exact_ht78_conversation_keeps_final_digit_and_account_answer(native_chat,monkeypatch):
    from app.services import conversation_chat
    from app.services import article_sql
    import json,copy
    from pathlib import Path
    schema=json.loads((Path(__file__).parent/'fixtures/article-sql-schema.json').read_text())
    category=copy.deepcopy(schema['categories'][0]);category.update(TCLCOD_0='NEG',TCLDES_0='Négoce',STOFCY_0='',ACCCOD_0='')
    schema['categories'].append(category)
    monkeypatch.setattr(article_sql,'catalog',lambda *a,**kw:copy.deepcopy(schema))
    c,q,requests,reads,attempts,fault=native_chat
    async def forbidden(*a,**kw):raise AssertionError('Literal article dialogue needs no provider')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    monkeypatch.setattr(conversation_chat.model,'extract',forbidden)
    s=create(c);ids=[]
    for message in ['JE VEUX CR2ER UN ARTICLMES CAF HT78 3','le nom compléte est CAF HT78 3','la catigorer est NEGOSE','crer les artice','crée le articles','CAF HT78','negose','4415']:
        s=send(c,s,message)
        assert len(s['state']['articles'])==1,message
        a=s['state']['articles'][0];ids.append(a['id'])
        assert a['designation']=='CAF HT78 3',message
        assert not a.get('code_article') or a['code_article']!='3'
        assert 'services IA' not in s['messages'][-1]['content'],message
    assert a['compte_general']=='4415'
    assert len(set(ids))==1 and not requests
    assert all(not x['execute'] for x in attempts)


def test_exact_caf798k_four_turns_without_any_model(native_chat,monkeypatch):
    from app.services import conversation_chat
    c,q,requests,reads,attempts,fault=native_chat
    async def forbidden(*a,**kw):raise AssertionError('These four literal messages require no model')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    monkeypatch.setattr(conversation_chat.model,'extract',forbidden)
    s=create(c)
    messages=['je veux créer un articele','le nom de l"articles est CAF 798K dans la catigorier negose','le nom de article est CAF 798K','et la catigorier negose']
    ids=[]
    for i,message in enumerate(messages):
        s=send(c,s,message)
        if i==0:
            assert 'Quel est le nom' in s['messages'][-1]['content']
            continue
        assert len(s['state']['articles'])==1
        a=s['state']['articles'][0];ids.append(a['id'])
        assert a['designation']=='CAF 798K'
        assert a.get('categorie')=='NEG' or a.get('categorie_libelle')=='negose'
        assert 'services IA' not in s['messages'][-1]['content']
    assert len(set(ids))==1 and not requests
    assert all(not x['execute'] for x in attempts)


@pytest.mark.parametrize('messages,name,site',[
 (['le nom de articles est CAF G56 L dans la catiégorier negos','Négoce',"c'est le negose",'NEG','la catigorier est NEG','un','le uniter est UN'],'CAF G56 L',None),
 (['le articne est CAF56 HY dasn le site 202 ET son catigorier est NEGOSE'],'CAF56 HY','202'),
])
def test_last_two_real_article_dialogues_without_provider(native_chat,monkeypatch,messages,name,site):
    c,q,requests,reads,attempts,fault=native_chat
    async def forbidden(*a,**kw):raise AssertionError('Literal clarification requires no provider')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    s=send(c,create(c),'je veux créer un articles')
    ids=[]
    for message in messages:
        s=send(c,s,message)
        assert len(s['state']['articles'])==1
        a=s['state']['articles'][0];ids.append(a['id'])
        assert a['designation']==name
        assert a.get('categorie')=='NEG' or (a.get('categorie_libelle') or '').lower() in ('negos','negose','neg','négoce')
        assert 'services IA' not in s['messages'][-1]['content']
    assert len(set(ids))==1
    if site:assert a['site']==site
    else:assert a['unite']=='UN'
    assert not requests and all(not x['execute'] for x in attempts)

def test_exact_tempo_conversation_uses_sage_draft_without_model(native_chat,monkeypatch):
    c,q,requests,_,attempts,_=native_chat
    async def forbidden(*args,**kwargs):raise AssertionError('No paid or local model is needed for these literal turns')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    s=create(c)
    for text in ['Bonjour je veux crée un article','la articles est TEMPO','je veux créer cette articles','créer l &articles TEMPO  la catigonier negose']:
        s=send(c,s,text)
        reply=s['messages'][-1]['content'].lower()
        assert not any(w in reply for w in ('public cible','offres','stratégies','prix','blog','détente'))
    assert len(s['state']['articles'])==1
    a=s['state']['articles'][0]
    assert a['designation']=='TEMPO'
    assert a.get('categorie_libelle')=='negose' or a.get('categorie')=='NEG'
    assert not a.get('approved') and a['operation']['status']!='succeeded'
    assert all(not x['execute'] for x in attempts)
    assert not requests

@pytest.mark.parametrize('text',['Bonjour je veux créer un article','je veux cree un article','créer un article'])
def test_missing_name_only_asks_name(text):assert parse(text,{})=={'ask_name':True}

def test_bare_name_uses_pending_article_context():
    assert parse('TEMPO',{'article_intake_pending':True})['name']=='TEMPO'
    assert parse('TEMPO',{}) is None

@pytest.mark.parametrize('text',['annule cette création','modifier article TEMPO','rédige un article de blog','Créer article TEST001, catégorie AVNS, unité UN, site 201'])
def test_complex_other_intents_keep_existing_route(text):assert parse(text,{}) is None

def test_supplier_only_scope_is_preserved():assert parse('créer article TEMPO',{'discussion_mode':'supplier'}) is None

def test_unverified_local_editorial_reply_cannot_override_business_recovery(monkeypatch):
    async def local(*args,**kwargs):return {'provider':'ollama','text_only_fallback':True,'message':{'role':'assistant','content':'Choisissez votre public cible et vos offres.'}}
    monkeypatch.setattr(ai_provider,'tool_chat',local)
    state={'articles':[{'id':'draft','designation':'TEMPO','operation':{'status':'blocked'}}]}
    result=asyncio.run(engine.turn(None,None,'Tu peux préparer cette fiche ?',state,[]))
    assert result['fallback'] is True
    assert not result['state'].get('native_fallback_reply')
    assert result['state']['articles'][0]['designation']=='TEMPO'

def test_old_failed_conversation_can_resume_from_its_last_creation_request(monkeypatch):
    async def forbidden(*args,**kwargs):raise AssertionError('No provider call allowed')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    result=asyncio.run(engine.turn(None,None,'la articles est TEMPO',{},[{'role':'user','content':'Bonjour je veux crée un article'},{'role':'assistant','content':'Définissez votre public cible.'}]))
    assert result['state']['articles'][0]['designation']=='TEMPO'
    assert result['phase']=='article_intake_draft'

def test_pending_article_name_is_not_a_supplier_search_or_completed_recreation():
    assert parse('cherche fournisseur F007',{'article_intake_pending':True}) is None
    assert parse('je veux créer cette articles',{'articles':[{'id':'done','designation':'TEMPO','operation':{'status':'succeeded'}}]}) is None

@pytest.mark.parametrize('provider',['deepseek','ollama'])
@pytest.mark.parametrize('native_enabled',[True,False])
def test_new_exact_conversation_in_all_provider_modes(native_chat,monkeypatch,provider,native_enabled):
    from app.core.config import settings
    c,q,requests,_,attempts,_=native_chat
    monkeypatch.setattr(settings,'ai_provider',provider)
    monkeypatch.setattr(settings,'conversation_tool_calling_enabled',native_enabled)
    async def forbidden(*args,**kwargs):raise AssertionError('No model call is needed')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    s=create(c)
    ids=[]
    for text in ['je veux créer un articles','mon articles est Tempo','créer cette artilces','dans la ctigorier NEgouse']:
        s=send(c,s,text)
        reply=s['messages'][-1]['content'].lower()
        assert not any(w in reply for w in ('public cible','offres','rythme','temporelle','immobilier','patrimoine','prix','type d’article','code et la désignation'))
        if s['state'].get('articles'):ids.append(s['state']['articles'][0]['id'])
    assert len(set(ids))==1 and len(s['state']['articles'])==1
    a=s['state']['articles'][0]
    assert a['designation']=='Tempo'
    assert a.get('categorie_libelle','').lower()=='negouse' or a.get('categorie')=='NEG'
    assert not a['approved'] and all(not x['execute'] for x in attempts)
    assert not requests

@pytest.mark.parametrize('provider',['deepseek','ollama'])
@pytest.mark.parametrize('native_enabled',[True,False])
def test_name_and_category_combined_survive_outage(native_chat,monkeypatch,provider,native_enabled):
    from app.core.config import settings
    c,q,requests,_,attempts,_=native_chat
    monkeypatch.setattr(settings,'ai_provider',provider)
    monkeypatch.setattr(settings,'conversation_tool_calling_enabled',native_enabled)
    async def forbidden(*args,**kwargs):raise AssertionError('No inference needed')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    s=send(c,create(c),'bonjour je veux créer un articles')
    s=send(c,s,'TEmpo et dans la ctigorier NEgose')
    assert len(s['state']['articles'])==1
    a=s['state']['articles'][0];identifier=a['id']
    assert a['designation']=='TEmpo' and a.get('categorie_libelle','').lower()=='negose'
    s=send(c,s,"le nom de l'articles est Tempo et pour la catigourier est negouse")
    a=s['state']['articles'][0]
    assert len(s['state']['articles'])==1 and a['id']==identifier
    assert a['designation']=='Tempo' and a.get('categorie_libelle','').lower()=='negouse'
    assert not a.get('approved') and not requests
    assert all(not x['execute'] for x in attempts)

def test_combined_rich_fields_are_not_silently_dropped():
    assert parse('Tempo et catégorie NEG et site 201',{'article_intake_pending':True}) is None

def test_negoce_alias_uses_only_existing_compatible_reference(monkeypatch):
    from app.services import article_sql_dialogue as dialogue,article_sql as sql
    schema={'categories':[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':'','STOMGTCOD_0':2}]}
    monkeypatch.setattr(sql,'catalog',lambda *args,**kwargs:schema)
    monkeypatch.setattr(sql,'prepare',lambda *args,**kwargs:{'status':'prepared'})
    a={'id':'a','designation':'Tempo','categorie_libelle':'NEgose'}
    dialogue.prepare_state({'articles':[a]})
    assert a['categorie']=='NEG' and a['code_article']=='NEG_TEMPO'

def test_alias_cannot_override_explicit_stock_constraint(monkeypatch):
    from app.services import article_sql_dialogue as dialogue,article_sql as sql
    from app.core.config import settings
    monkeypatch.setattr(settings,'sage_modification_enabled',True)
    schema={'categories':[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':'','STOMGTCOD_0':2}]}
    monkeypatch.setattr(sql,'catalog',lambda *args,**kwargs:schema)
    monkeypatch.setattr(sql,'prepare',lambda *args,**kwargs:pytest.fail('Incompatible category must not be prepared'))
    a={'id':'a','designation':'Tempo','categorie_libelle':'negouse','gestion_stock':'1'}
    dialogue.prepare_state({'articles':[a]})
    assert not a.get('categorie') and a['gestion_stock']=='1' and a['operation']['status']=='blocked'
