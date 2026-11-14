import copy
import asyncio
from app.services import article_sql_dialogue as dialogue,conversation_tools as e
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create

def test_unrelated_negative_clause_does_not_cancel_positive_site_addition(monkeypatch):
    from app.services import modification_actions
    captured=[]
    def prepare(d):captured.append(copy.deepcopy(d));d['operation']={'status':'prepared'}
    monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
    text='Pour cet article de test CXTEST001, prépare uniquement l’ajout du site 202. Ne change pas la fiche principale et attends la confirmation.'
    state={'articles':[{'id':'owned','code_article':'CXTEST001','operation':{'status':'succeeded'}}]}
    result=asyncio.run(e.turn(None,None,text,state,[]))
    assert result['phase']=='literal_article_site_addition'
    assert captured[0]['changes']=={'add_sites':['202']}
    assert result['state']['tool_orchestration']['sage_writes']==0

def test_designation_est_does_not_override_valid_model_with_verb():
    s={'articles':[{'id':'a','designation':'PAPIER A4 80G TES 002','site':'202'}]}
    dialogue.enrich(s,'attend, jai fait une faute : la désignation est PAPIER A4 80G TEST 002, corrige juste ça',copy.deepcopy(s))
    assert s['articles'][0]['designation']=='PAPIER A4 80G TEST 002'
    assert s['articles'][0]['site']=='202'

def test_unknown_code_alias_and_repeated_historical_facts_do_not_drop_draft(native_chat):
    c,q,*_=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','EXTINCTEUR TEST'),fact('site','131')],unknowns=['code','categorie'])),say('Quelle catégorie souhaitez-vous ?')])
    s=send(c,create(c),'Créer article EXTINCTEUR TEST site 131, code inconnu')
    assert s['state']['articles'][0]['designation']=='EXTINCTEUR TEST'
    assert s['state']['articles'][0]['site']=='131'
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=s['state']['articles'][0]['id'],fields=[fact('designation','EXTINCTEUR TEST','EXTINCTEUR TEST'),fact('site','131')])),say('Site conservé.')])
    s=send(c,s,'cest pour 131, pas la peine de redemander le site')
    errors=[x['result'] for x in s['state']['tool_orchestration']['calls'] if not x['result'].get('ok')]
    assert not errors
    assert len(s['state']['articles'])==1

def test_complete_creation_does_not_require_generated_query_or_provider(native_chat,monkeypatch):
    c,q,*_=native_chat
    async def forbidden(*args,**kwargs):raise AssertionError('Complete literal input needs no model call')
    monkeypatch.setattr(e.ai_provider,'tool_chat',forbidden)
    text='Prépare un article de test. Code article : CXDEMO001, désignation : Article demo, catégorie AVNS, unité UN, site 201, non géré en stock, acheté et vendu, sans fournisseur.'
    s=send(c,create(c),text)
    assert s['state']['articles'][0]['code_article']=='CXDEMO001'
    assert s['state']['articles'][0]['designation']=='Article demo'
    assert s['state']['tool_orchestration']['provider']=='literal_complete_creation'

def test_additional_reference_and_same_site_are_retained(native_chat):
    c,q,*_=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','SCIE TEST'),fact('site','201')])),say('Quelle catégorie ?')])
    s=send(c,create(c),'créer article SCIE TEST site 201')
    q.append(say('Deux références conservées.'))
    s=send(c,s,'ah au fait il faut aussi LUNETTES PROTECTION TEST 001, avec CIMAT, ce sont 2 références différentes')
    assert len(s['state']['articles'])==2
    s=send(c,s,'le deuxième cest pour le même site, pas un troisième')
    assert len(s['state']['articles'])==2 and s['state']['articles'][1]['site']=='201'

def test_category_declaration_survives_search_without_model_patch(native_chat):
    c,q,*_=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','PAPIER TEST')])),say('Quelle catégorie ?')])
    s=send(c,create(c),'Créer article PAPIER TEST')
    q.append(say('Je conserve votre catégorie pour vérification.'))
    s=send(c,s,'la catégorie cest consommables')
    assert s['state']['articles'][0]['categorie_libelle']=='consommables'
