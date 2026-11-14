from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create
from app.services.modification_resolvers import CategoryResolver
from app.services.chat_article_requests import declared_sites
from app.services.article_sql_dialogue import recover_declared_batch


def test_category_read_does_not_require_insert_but_creation_catalog_does(monkeypatch):
    import pytest
    from app.services import article_sql,sage_crud
    result={'ok':True,'folder':'OB','permissions':[{'can_select':1,'can_insert':0}],'categories':[]}
    monkeypatch.setattr(article_sql,'transport',lambda *a,**kw:result)
    assert article_sql.catalog(folder='OB',require_insert=False) is result
    with pytest.raises(sage_crud.CrudError):article_sql.catalog(folder='OB')
    result['permissions'][0]['can_select']=0
    with pytest.raises(sage_crud.CrudError):article_sql.catalog(folder='OB',require_insert=False)


def test_dimensioned_email_is_idempotent_without_model(native_chat,monkeypatch):
    from app.services import ai_provider
    c,q,requests,reads,attempts,fault=native_chat
    async def forbidden(*args,**kwargs):
        raise AssertionError('A literal batch must finish before model orchestration')
    monkeypatch.setattr(ai_provider,'tool_chat',forbidden)
    text='Bonjour, Merci de créer les 2 références d article. Fournisseur RZ timber qui est déjà existant MADRIER 37*177*4  MADRIER 37*177*3 Cdlt'
    s=send(c,create(c),text)
    assert [a['designation'] for a in s['state']['articles']]==['MADRIER 37*177*4','MADRIER 37*177*3']
    assert all(a['fournisseur_nom']=='RZ timber' for a in s['state']['articles'])
    assert not s['state'].get('partners')
    assert s['messages'][-1]['content'].count('Quelle catégorie')==1
    assert 'Catégories existantes dans TEST' in s['messages'][-1]['content']
    ids=[a['id'] for a in s['state']['articles']]
    s=send(c,s,text)
    assert [a['id'] for a in s['state']['articles']]==ids
    assert all(not a.get('approved') for a in s['state']['articles'])
    assert all(not a['execute'] for a in attempts)

def test_supplier_relation_survives_http_turns_and_is_saved_as_article_change(native_chat,monkeypatch):
    from app.services import business_store as db,modification_actions
    from psycopg.types.json import Jsonb
    c,q,_,_,attempts,_=native_chat
    s=create(c)
    with db.connection() as conn:
        row=conn.execute('SELECT state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()
        row['state']['articles']=[{'id':'existing-article','code_article':'GEN_AINATLASE','designation':'AINATLASE','operation':{'status':'succeeded'}}]
        conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(row['state']),s['id']))
    q.append(say('Quels codes fournisseurs souhaitez-vous rattacher à cet article ?'))
    s=send(c,s,'dire fihe le fournisseur rachide ou cimat')
    q.append(say('Les codes sont conservés pour le rattachement.'))
    s=send(c,s,'codes retenus F10043 et F007')
    captured=[]
    def prepare(d):
        captured.append(d.copy());d['operation']={'status':'prepared','folder':'TEST'}
    monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
    s=send(c,s,'direhame fi articles GEN_AINATLASE')
    assert captured[0]['resource']=='article'
    saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
    assert saved['state']['modification_drafts'][0]['changes']['add_suppliers']==[{'code':'F10043','reference':''},{'code':'F007','reference':''}]
    assert all(not a['execute'] for a in attempts)

def test_dimensioned_email_survives_model_omission_in_real_chat_route(native_chat):
    c,q,_,_,attempts,_=native_chat
    text='Bonjour, Merci de créer les 2 références d article. Fournisseur RZ timber qui est déjà existant MADRIER 37*177*4  MADRIER 37*177*3 Cdlt'
    q.append(say('Les deux références sont conservées. Quelle catégorie retenir ?'))
    s=send(c,create(c),text)
    assert [a['designation'] for a in s['state']['articles']]==['MADRIER 37*177*4','MADRIER 37*177*3']
    assert all(a['fournisseur_nom']=='RZ timber' for a in s['state']['articles'])
    ids=[a['id'] for a in s['state']['articles']]
    q.append(say('Quelle catégorie souhaitez-vous retenir ?'))
    s=send(c,s,'le catigourer dois negose')
    assert [a['id'] for a in s['state']['articles']]==ids
    assert all(a['categorie_libelle']=='negose' for a in s['state']['articles'])
    assert all(not a['execute'] for a in attempts)

def test_three_nameless_code_drafts_survive_and_receive_both_sites(native_chat):
    c,q,_,_,attempts,_=native_chat
    names=['Distributeur de savon mural','Détecteur de fumée','Kit de premiers secours']
    text='Merci de créer les articles suivants : '+names[0]+', unité, article non géré en stock, fournisseur CHAOUIA PROTECT. '+names[1]+', unité, article acheté et vendu, fournisseur CHAOUIA PROTECT. '+names[2]+', unité, fournisseur F007.'
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation',names[0]),fact('gestion_stock','1','non géré en stock'),fact('fournisseur_principal','CHAOUIA PROTECT')]),call('prepare_draft',resource='article',mode='new',fields=[fact('designation',names[1]),fact('achete','2','acheté et vendu'),fact('vendu','2','acheté et vendu'),fact('fournisseur_principal','CHAOUIA PROTECT')]),call('prepare_draft',resource='article',mode='new',fields=[fact('designation',names[2]),fact('fournisseur_principal','F007')])),say('Trois brouillons conservés.')])
    s=send(c,create(c),text)
    assert [a['designation'] for a in s['state']['articles']]==names
    ids=[a['id'] for a in s['state']['articles']];assert len(set(ids))==3
    assert s['state']['articles'][0]['gestion_stock']=='1'
    assert not s['state']['articles'][1].get('gestion_stock')
    assert s['state']['articles'][0]['fournisseur_nom']=='CHAOUIA PROTECT'
    s=send(c,s,'pour les site dois dans 202 ET 201')
    assert [a['id'] for a in s['state']['articles']]==ids
    assert all(a['requested_sites']==['202','201'] for a in s['state']['articles'])
    assert all(not a['execute'] for a in attempts)

def test_matching_category_is_visible_even_when_stock_conflicts():
    rows=[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':'','STOMGTCOD_0':2},{'TCLCOD_0':'FOURN','TCLDES_0':'FOURNITURE DE NETTOYAGE','STOFCY_0':'','STOMGTCOD_0':1}]
    choices=CategoryResolver().search('negouse',rows,{'STOMGTCOD_0':1},include_incompatible=True)
    assert choices[0]['code']=='NEG' and not choices[0]['compatible']
    assert choices[0]['conflicts']==['STOMGTCOD_0'] and choices[0]['requires_selection']

def test_noisy_common_site_phrase_keeps_both_codes():
    assert declared_sites('pour les site dois dans 202 ET 201')==['202','201']

def test_lost_email_drafts_are_recovered_without_replacing_existing_or_cancelled():
    text='Merci de créer les articles suivants : Distributeur de savon mural, unité, non géré en stock, fournisseur CHAOUIA PROTECT. Détecteur de fumée, unité, acheté et vendu, fournisseur CHAOUIA PROTECT. Kit de premiers secours, unité, fournisseur F007.'
    kit={'id':'stable','designation':'Kit de premiers secours','gestion_stock':'1','operation':{'status':'blocked'}}
    state={'articles':[kit]};history=[{'role':'user','content':text}]
    assert recover_declared_batch(state,history)==2
    assert len(state['articles'])==3 and state['articles'][2] is kit
    assert state['articles'][0]['designation']=='Distributeur de savon mural'
    assert 'gestion_stock' not in kit
    assert recover_declared_batch(state,history)==0
    state={'articles':[kit]}
    assert recover_declared_batch(state,history+[{'role':'user','content':'annule le premier article'}])==0
