"""Structured DeepSeek -> FastAPI -> private PG; HTTP and Sage are simulated."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
import pytest,httpx
from test_deepseek_provider import cloud,send
from test_conversation_chat import fixture,create
from app.core.config import settings
from app.services import supplier_chat_flow,conversation_analysis as semantic,supplier_dialogue

PLAIN="bonjour je veux crrer un nevelle fourniseur il s'appelle ATLAS BUREAU TEST c'est une SARL AU à Rabat mais j'ai pas encore son ICE ni téléphone"
COMMAS="Bonjour, je veux crrer un nevelle fourniseur, il s'appelle ATLAS BUREAU TEST, c'est une SARL AU à Rabat, mais j'ai pas encore son ICE ni son téléphone."
def analysis(fields=None,**extra):
    return {'intent':'CREATE_SUPPLIER','reformulation':'Préparer ATLAS BUREAU TEST à Rabat, forme SARL AU, ICE et téléphone inconnus.','extracted':[{'field':k,'value':v,'evidence':v} for k,v in (fields or {'nom':'ATLAS BUREAU TEST','ville':'Rabat','forme_juridique':'SARL AU'}).items()],
        'unknowns':['ice','telephone'],'corrections':[],'proposed_action':'PREPARE_DRAFT','reply_candidate':'La fiche est prête à relire. L’ICE et le téléphone restent non renseignés.',**extra}

@pytest.fixture
def stage(cloud,monkeypatch):
    c,calls,response=cloud;monkeypatch.setattr(settings,'conversation_analysis_enabled',True)
    response['text']=json.dumps(analysis(),ensure_ascii=False)
    original=httpx.AsyncClient.post
    async def post(self,url,**kw):
        if '/api/chat' in str(url) and 'local_json' in response:
            calls.append({'url':str(url),'payload':kw.get('json')})
            return httpx.Response(200,request=httpx.Request('POST',url),json={'done':True,'message':{'content':json.dumps(response['local_json'])}})
        return await original(self,url,**kw)
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    def prepare(state):
        p=state['partners'][0];assert not p['approved'];p['operation']={'status':'prepared'}
        return 'Fiche prête. Vérifiez les informations avant de confirmer.'
    monkeypatch.setattr(supplier_chat_flow,'prepare_state',prepare)
    return c,calls,response

@pytest.mark.parametrize('text',[PLAIN,COMMAS,PLAIN.replace("c'est",'c’est'),PLAIN.replace('crrer','créer'),PLAIN.replace('ATLAS BUREAU TEST','**ATLAS BUREAU TEST**')])
def test_structured_analysis_matches_pg_and_displayed_reply(stage,text):
    c,calls,response=stage;s=send(c,create(c),text)
    a=s['state']['conversation_analysis'];p=s['state']['partners'][0]
    assert a['status']=='validated' and a['provider']=='deepseek'
    assert a['analysis']['intent']=='CREATE_SUPPLIER'
    assert {f['field']:f['value'] for f in a['analysis']['extracted']}=={k:p[k] for k in ('nom','ville','forme_juridique')}
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'
    assert not p.get('ice') and not p.get('telephone')
    assert p['field_states']['ice']['status']=='unknown' and p['field_states']['telephone']['status']=='unknown'
    assert len(calls)==1 and not s['state'].get('_pending')
    assert s['messages'][-1]['content'].startswith('La fiche est prête à relire')
    saved=c.get('/api/v1/chat/conversations/'+s['id']).json();assert saved['state']['conversation_analysis']==a

@pytest.mark.parametrize('failure',[401,429,503,'timeout','json'])
def test_failed_api_or_json_preserves_and_uses_deterministic_fallback(stage,failure):
    c,calls,r=stage
    if isinstance(failure,int):r['status']=failure
    elif failure=='timeout':r['timeout']=True
    else:r['text']='not JSON'
    s=send(c,create(c),PLAIN);p=s['state']['partners'][0]
    assert s['state']['conversation_analysis']['status']=='fallback'
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'
    assert not s['state'].get('_pending') and 'extraction' not in s['messages'][-1]['content'].lower()
    assert len(calls)==2

def test_qwen_fallback_also_produces_validated_analysis(stage):
    c,calls,r=stage;r['status']=503;r['local_json']=analysis()
    s=send(c,create(c),PLAIN)
    assert s['state']['conversation_analysis']['provider']=='ollama'
    assert s['state']['conversation_analysis']['status']=='validated' and len(calls)==2

@pytest.mark.parametrize('candidate',['Quel est le nom du fournisseur ?','Souhaitez-vous créer ou modifier ?',"J’ai créé le fournisseur avec succès dans TEST."])
def test_unsafe_or_repeated_question_candidate_is_rejected(stage,candidate):
    c,_,r=stage;r['text']=json.dumps(analysis(reply_candidate=candidate))
    s=send(c,create(c),PLAIN)
    assert not s['state']['conversation_analysis']['candidate_accepted']
    assert candidate not in s['messages'][-1]['content']

def test_hallucinated_city_is_not_saved(stage):
    c,_,r=stage;r['text']=json.dumps(analysis({'nom':'ATLAS BUREAU TEST','ville':'Paris'}))
    s=send(c,create(c),PLAIN)
    assert s['state']['partners'][0]['ville']=='Rabat'
    assert s['state']['conversation_analysis']['status']=='fallback'

def test_correction_updates_one_field_and_keeps_context(stage):
    c,_,r=stage;s=send(c,create(c),PLAIN)
    r['text']=json.dumps(analysis({'nom':'ATLAS CORRIGÉ'},intent='UPDATE_SUPPLIER',unknowns=[],corrections=['nom']))
    s=send(c,s,'Non, le nom est ATLAS CORRIGÉ')
    p=s['state']['partners'][0];assert p['nom']=='ATLAS CORRIGÉ' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'

@pytest.mark.parametrize('text,fields',[
    ('salam zid lina fournisseur jdid smitou RIF ELECTRIC kayn f Fes',{'nom':'RIF ELECTRIC','ville':'Fes'}),
    ('بغيت نزيد مورد جديد سميتو النور تيست فالرباط',{'nom':'النور تيست','ville':'الرباط'})])
def test_darija_grounded_values(stage,text,fields):
    c,_,r=stage;r['text']=json.dumps(analysis(fields,unknowns=[]))
    s=send(c,create(c),text);p=s['state']['partners'][0]
    assert all(p[k]==v for k,v in fields.items())

def test_greeting_uses_single_structured_call(stage):
    c,calls,r=stage;r['text']=json.dumps(analysis(extracted=[],intent='CHAT',unknowns=[],proposed_action='CHAT',reply_candidate='Bonjour ! Comment puis-je vous aider ?'))
    s=send(c,create(c),'Bonjour');assert s['messages'][-1]['content']=='Bonjour ! Comment puis-je vous aider ?' and len(calls)==1

def test_article_schema_does_not_route_article_fields_to_supplier():
    value=semantic.Analysis.model_validate(analysis({'code_article':'TESTIA001','designation':'BUREAU','categorie':'AVNS','unite':'UN','site':'202'},intent='CREATE_ARTICLE',unknowns=[]))
    state={'articles':[],'partners':[],'conversation_analysis':{'status':'validated','analysis':value.model_dump()}}
    assert semantic.supplier_turn('Créer un article TESTIA001',state) is None

def test_existing_ice_is_not_erased_by_unknown_analysis():
    value=semantic.Analysis.model_validate(analysis(extracted=[],intent='UPDATE_SUPPLIER',unknowns=['ice']))
    state={'partners':[{'id':'draft','kind':'supplier','nom':'ATLAS','ice':'001234567890123','sources':{}}],
        'conversation_analysis':{'status':'validated','analysis':value.model_dump()}}
    out=semantic.supplier_turn('Je ne connais pas mon ICE',state)['state']
    assert out['partners'][0]['ice']=='001234567890123'

def test_response_candidate_must_match_final_draft():
    value=analysis({'ville':'Rabat'},reply_candidate='La ville est Rabat.')
    state={'partners':[{'ville':'Casablanca','operation':{'status':'prepared'}}],
        'conversation_analysis':{'status':'validated','analysis':value,'candidate_accepted':True}}
    assert semantic.checked_supplier_reply(state,'Ville corrigée : Casablanca.')=='Ville corrigée : Casablanca.'
    assert state['conversation_analysis']['coherence_errors']==['ville']

@pytest.mark.parametrize('text',[PLAIN,COMMAS])
def test_model_free_fallback_separates_clauses(text):
    p=supplier_dialogue.handle(text,{'partners':[],'articles':[]})['state']['partners'][0]
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat'
    assert {'ice','telephone'}<=set(p['unknown_fields'])
