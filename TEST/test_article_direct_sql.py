"""Article/category plans and real chat authorization; Sage writes ALWAYS mocked."""
import sys,json,copy
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timedelta,timezone
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from test_conversation_chat import fixture,create
from app.services import article_sql as sql,article_sql_dialogue as dialogue,chat_article_sql_actions as actions,conversation_chat as chat,business_store as db,sage_crud as crud
from app.core.config import settings

def schema():return json.loads((ROOT/'TEST/fixtures/article-sql-schema.json').read_text())
def article(**changes):
    return {'id':str(uuid4()),'code_article':'QATEST201','designation':'Article de verification','categorie':'AVNS','unite':'UN','requested_sites':['201'],'fournisseurs':[{'code':'F994','reference':''}],**changes}


def test_account_prefix_search_proposes_real_codes_without_selecting():
    data=schema()
    data['accounting']=[{'ACCCOD_0':'CODE_TEST','ACC_0':'44150000'},{'ACCCOD_0':'OTHER','ACC_0':'61200000'}]
    draft=article(compte_general='4415')
    with pytest.raises(crud.CrudError) as error:sql.article_plan(draft,data)
    assert 'CODE_TEST' in error.value.code and 'OTHER' not in error.value.code
    assert not draft.get('code_comptable')


def test_unmatched_account_prefix_has_precise_message():
    data=schema();data['accounting']=[{'ACCCOD_0':'OTHER','ACC_0':'61200000'}]
    with pytest.raises(crud.CrudError) as error:sql.article_plan(article(compte_general='4415'),data)
    assert 'Aucun code comptable article relié à 4415' in error.value.code
def proof(plan,execute=False):
    return {'ok':True,'folder':'TEST','resource':plan['resource'],'code':plan['code'],'executed':execute,'transaction_state':'COMMIT' if execute else 'VALIDATED_NO_INSERT','sql_verified':execute,'records':[{'tab':n['table'],'site':n['overrides'].get('STOFCY_0'),'supplier':n['overrides'].get('BPSNUM_0'),'inserted':int(execute)} for n in plan['nodes']]}

@pytest.fixture
def simulated(monkeypatch):
    s=schema();calls=[]
    monkeypatch.setattr(settings,'sage_article_sql_enabled',True);monkeypatch.setattr(settings,'sage_mcp_enabled',False)
    monkeypatch.setattr(sql,'catalog',lambda *args,**kwargs:copy.deepcopy(s))
    def transport(action,plan=None,execute=False,**kwargs):
        assert action=='plan';calls.append((copy.deepcopy(plan),execute))
        if execute and plan['resource']=='category':s['categories'].append({**plan['nodes'][0]['overrides'],'source_hash':'C'*64})
        return proof(plan,execute)
    monkeypatch.setattr(sql,'transport',transport)
    from app.services.sage_gateway import Gateway
    monkeypatch.setattr(Gateway,'read',lambda *args,**kwargs:{'exists':False})
    monkeypatch.setattr(Gateway,'write_once',lambda *args,**kwargs:pytest.fail('SOAP write forbidden'))
    actions.PERMITS.clear()
    return s,calls

@pytest.mark.parametrize('changes,count,sales,providers,sites',[
    ({},5,1,1,['201']),
    ({'requested_sites':['202'],'fournisseurs':[{'code':p,'reference':''} for p in ('F994','F468','F354','F007')]},8,1,4,['202']),
    ({'categorie':'AVT','gestion_stock':'2','vendu':'1','requested_sites':['201','202'],'fournisseurs':[],'supplier_intent':'none'},4,0,0,['201','202'])])
def test_three_validated_scenarios(simulated,changes,count,sales,providers,sites):
    plan=sql.prepare(article(**changes))['plan'];nodes=plan['nodes']
    assert len(nodes)==count and sum(n['table']=='ITMSALES' for n in nodes)==sales
    assert sum(n['table']=='ITMBPS' for n in nodes)==providers
    assert [n['overrides']['STOFCY_0'] for n in nodes if n['table']=='ITMFACILIT']==sites
    assert nodes[-1]['overrides']=={'CODFIC_0':'ITMMASTER','ZONE_0':'DES1AXX','IDENT1_0':'QATEST201','IDENT2_0':'','LANGUE_0':'FRA','TEXTE_0':'Article de verification'}
    assert all(not execute for _,execute in simulated[1])

@pytest.mark.parametrize('changes',[
    {'dossier_cible':'OB'},{'code_article':''},{'designation':'X'*71},{'categorie':'NOPE'},
    {'gestion_stock':'2'},{'site':'999','requested_sites':['999']},{'vendu':'1'},
    {'unite':'BAD'},{'unite_achat':'M2'},{'code_comptable':'BAD'},{'code_tva':'BAD'},
    {'taux_tva':'20'},{'fournisseurs':[{'code':'F999999','reference':''}]},
    {'fournisseurs':[{'code':'F994','reference':'X'*21}]},
    {'fournisseurs':[{'code':'F994'},{'code':'F994'}]},
    {'supplier_intent':'none'},{'fournisseur_principal':'F468'},{'type_article':'invented'},
    {'fournisseurs':[],'flag_fournisseur':'2'},
    {'compte_general':'61253000'},{'accounting_category':'Frais generaux'},
    {'flag_fournisseur':'3'},
    {'modele_article':'UNKNOWN'},{'modele_site':'UNKNOWN'},
    {'modele_fournisseur':'UNKNOWN'},{'modele_traduction':'UNKNOWN'},
    {'unite':'M99'},
])
def test_invalid_or_unverified_input_never_reaches_sql(simulated,changes):
    with pytest.raises(crud.CrudError):sql.prepare(article(**changes))
    assert not simulated[1]

def test_new_unit_can_instantiate_neutral_approved_template(simulated):
    plan=sql.prepare(article(unite='M2'))['plan']
    master=next(n for n in plan['nodes'] if n['table']=='ITMMASTER')
    assert master['model']=='TESTART201'
    assert all(master['overrides'][key]=='M2' for key in ('STU_0','PUU_0','SAU_0','SSU_0','EEU_0'))
    assert all(master['overrides'][key]==1 for key in ('PUUSTUCOE_0','SAUSTUCOE_0','SSUSTUCOE_0','EEUSTUCOE_0'))
    assert all(not execute for _,execute in simulated[1])

@pytest.mark.parametrize('change',[{'PCU_0':'RLX'},{'PCUSTUCOE_0':1000},{'PUUSTUCOE_0':25},{'PUU_0':'RLX'},{'ITMWEI_0':1},{'VOU_0':'M3'}])
def test_new_unit_never_reuses_non_neutral_template(simulated,change):
    data=simulated[0]
    for row in data['articles']:row['fields'].update(change)
    with pytest.raises(crud.CrudError):sql.prepare(article(unite='M2'),schema=data)
    assert not simulated[1]

def test_long_generated_reference_is_explicit_unique_proposal(simulated):
    op=sql.prepare(article(code_article='TWENTYCHARACTERSLONG',fournisseurs=[{'code':p} for p in ('F994','F007')]))
    refs=op['summary']['suppliers'];assert all(len(p['reference'])==20 and p['generated'] and p['strategy']=='reference_technique_hachee_a_confirmer' for p in refs)
    assert refs[0]['reference']!=refs[1]['reference']

@pytest.mark.parametrize('key',['translations','supplier_models','sales'])
def test_missing_source_retains_original_input(simulated,key):
    simulated[0][key]=[];a=article();before=copy.deepcopy(a)
    with pytest.raises(crud.CrudError):sql.prepare(a)
    assert a==before and not simulated[1]

def test_missing_site_model_not_cloned_from_other_site(simulated):
    simulated[0]['facilities']=[r for r in simulated[0]['facilities'] if r['STOFCY_0']!='202']
    with pytest.raises(crud.CrudError):sql.prepare(article(requested_sites=['202']))

def test_category_existing_or_long_label_blocks_without_truncation(simulated):
    state={};a=article(categorie='QAT01');dialogue.prepare_missing_category(state,a,simulated[0]);d=state['category_drafts'][0]
    assert d['operation']['status']=='prepared'
    for changes in ({'code':'AVNS'},{'designation':'X'*71},{'nom_court':'X'*11}):
        raw={k:v for k,v in {**d,**changes}.items() if k not in ('operation','approved')}
        with pytest.raises(crud.CrudError):sql.prepare(raw,'category')

def test_followups_preserve_fields_and_add_only_requested_provider(simulated):
    a=article();state={'articles':[a]};old=copy.deepcopy(state)
    dialogue.prepare_state(state,'Ajoute fournisseur F007',old)
    assert [p['code'] for p in a['fournisseurs']]==['F994','F007']
    assert a['code_article']==old['articles'][0]['code_article']
    old=copy.deepcopy(state);dialogue.prepare_state(state,'sans fournisseur, sites 201 et 202',old)
    assert not a['fournisseurs'] and a['supplier_intent']=='none' and a['requested_sites']==['201','202']

@pytest.mark.parametrize('damage',[{'code':'OTHER'},{'folder':'OB'},{'sql_verified':False},{'executed':False},{'records':[]},{'transaction_state':'ROLLBACK'}])
def test_success_requires_exact_transaction_proof(simulated,damage):
    plan=sql.article_plan(article());assert not sql.verify(plan,{**proof(plan,True),**damage})

def seed(c):
    s=create(c)
    with db.connection() as conn:
        row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone();row['state']['articles']=[article()];row['state']['supplier_target']='TEST';chat.save_conversation_context(conn,row['owner_id'],s['id'],row['state'])
    return chat.read(row['owner_id'],UUID(str(s['id']))),row['owner_id']
def step(c,s,name,confirm=False,category=False):
    item=s['state']['category_drafts' if category else 'articles'][0]
    return c.post('/api/v1/chat/conversations/'+str(s['id'])+('/categories/' if category else '/articles/')+item['id']+'/'+name,json={'revision':s['revision'],'confirm':confirm})

def test_legacy_markdown_category_label_is_recovered(simulated):
    a=article(categorie=None,categorie_libelle='**AVNS**')
    state={'articles':[a]}
    dialogue.prepare_state(state,'Supprime les etoiles dans les valeurs',copy.deepcopy(state))
    assert a['categorie']=='AVNS' and a['operation']['status']=='prepared'

def test_markdown_creation_and_corrections_persist_in_chat(fixture,simulated):
    c,q=fixture;s=create(c)
    texts=('Bonjour, je veux créer un article **TESTIA001**, désignation **FOURNITURE BUREAU TEST**, catégorie **AVNS**, non géré en stock, acheté et vendu, unité **UN**, site **202**, sans fournisseur. Prépare sa fiche pour validation.',"J'ai déjà donné le code AVNS",'Supprime les étoiles dans les valeurs')
    for text in texts:
        r=c.post('/api/v1/chat/conversations/'+str(s['id'])+'/messages',json={'content':text,'revision':s['revision']})
        assert r.status_code==200,r.text
        s=r.json();a=s['state']['articles'][0]
        assert a['code_article']=='TESTIA001' and a['designation']=='FOURNITURE BUREAU TEST'
        assert a['categorie']=='AVNS' and a['unite']=='UN' and a['requested_sites']==['202']
        assert a['gestion_stock']=='1' and a['achete']=='2' and a['vendu']=='2'
        assert a['flag_fournisseur']=='1' and a['fournisseurs']==[]
        assert a['operation']['status']=='prepared'
    assert not q and not any(execute for _,execute in simulated[1])

def test_confirmed_execution_and_replay_guard(fixture,simulated):
    c,_=fixture;s,owner=seed(c)
    assert step(c,s,'execute',True).status_code==409
    s=step(c,s,'prepare').json();assert step(c,s,'approve').status_code==403
    assert step(c,s,'execute',True).status_code==403
    s=step(c,s,'approve',True).json();assert not any(x for _,x in simulated[1])
    r=step(c,s,'execute',True);assert r.status_code==200,r.text
    s=r.json();op=s['state']['articles'][0]['operation'];assert op['status']=='succeeded' and op['verification']['sql_verified'] and not op['verification']['business_operations_verified']
    assert step(c,s,'execute',True).status_code==409
    assert sum(execute for _,execute in simulated[1])==1
    with pytest.raises(crud.CrudError):chat.invalidate(s['state']['articles'][0])

@pytest.mark.parametrize('damage',['input','plan','query','expiry','revision','mcp','target','owner','restart'])
def test_stale_foreign_or_changed_approval_cannot_execute(fixture,simulated,damage):
    c,_=fixture;s,owner=seed(c);s=step(c,s,'prepare').json();s=step(c,s,'approve',True).json();a=s['state']['articles'][0]
    if damage in ('input','plan','query','target'):
        with db.connection() as conn:
            row=chat.get_row(conn,owner,UUID(str(s['id'])),True);item=row['state']['articles'][0]
            if damage=='input':item['designation']='Different'
            elif damage=='plan':item['operation']['plan']['code']='OTHER'
            elif damage=='query':item['operation']['query_digest']='old'
            else:row['state']['supplier_target']='OB'
            chat.save_conversation_context(conn,owner,UUID(str(s['id'])),row['state'])
    elif damage=='expiry':actions.PERMITS[a['id']]['expires']=datetime.now(timezone.utc)-timedelta(seconds=1)
    elif damage=='revision':s['revision']-=1
    elif damage=='mcp':settings.sage_mcp_enabled=True
    elif damage=='owner':actions.PERMITS[a['id']]['owner']=str(uuid4())
    elif damage=='restart':actions.PERMITS.clear()
    r=step(c,s,'execute',True);assert r.status_code in (403,409,423),r.text
    assert not any(x for _,x in simulated[1])

@pytest.mark.parametrize('result,status',[({'ok':False,'transaction_state':'ROLLBACK'},'blocked'),({'ok':False,'code':'result_requires_readback'},'ambiguous')])
def test_failed_or_unknown_execution_does_not_claim_success(fixture,simulated,monkeypatch,result,status):
    c,_=fixture;s,owner=seed(c);s=step(c,s,'prepare').json();s=step(c,s,'approve',True).json()
    monkeypatch.setattr(sql,'transport',lambda *args,**kwargs:result)
    r=step(c,s,'execute',True);assert r.status_code==200,r.text
    s=r.json();assert s['state']['articles'][0]['operation']['status']==status
    assert step(c,s,'execute',True).status_code in (403,409)

def test_category_and_article_require_separate_confirmations(fixture,simulated):
    c,_=fixture;s,owner=seed(c)
    with db.connection() as conn:
        row=chat.get_row(conn,owner,UUID(str(s['id'])),True);row['state']['articles'][0]['categorie']='QAT01'
        # Creating a missing category is a separate explicit request, never
        # an automatic consequence of receiving an unrecognised category code.
        dialogue.prepare_missing_category(row['state'],row['state']['articles'][0],simulated[0])
        dialogue.prepare_state(row['state']);chat.save_conversation_context(conn,owner,UUID(str(s['id'])),row['state'])
    s=chat.read(owner,UUID(str(s['id'])));assert s['state']['category_drafts'][0]['operation']['status']=='prepared'
    s=step(c,s,'approve',True,True).json();r=step(c,s,'execute',True,True);assert r.status_code==200,r.text
    s=r.json();assert s['state']['category_drafts'][0]['operation']['status']=='succeeded'
    assert s['state']['articles'][0]['operation']['status']=='prepared'
    assert sum(execute for _,execute in simulated[1])==1
    assert step(c,s,'execute',True).status_code==403

def test_chat_simple_creation_and_provider_followup_do_not_need_model(fixture,simulated):
    c,q=fixture;s=create(c)
    for text in ('Cree un article Verification, code article: QATEST201, categorie: AVNS, site 201, fournisseur F994.','unite UN','Ajoute fournisseur F007'):
        r=c.post('/api/v1/chat/conversations/'+str(s['id'])+'/messages',json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text;s=r.json()
    a=s['state']['articles'][0];assert a['code_article']=='QATEST201' and a['categorie']=='AVNS'
    assert [p['code'] for p in a['fournisseurs']]==['F994','F007']
    assert a['operation']['status']=='prepared' and not q and not any(x for _,x in simulated[1])

@pytest.mark.parametrize('matching',[False,True])
def test_sage_consultation_is_distinct_from_sql_and_business_validation(fixture,simulated,monkeypatch,matching):
    from app.services.sage_gateway import Gateway
    c,_=fixture;s,owner=seed(c);s=step(c,s,'prepare').json();s=step(c,s,'approve',True).json()
    monkeypatch.setattr(Gateway,'read',lambda *args,**kwargs:{'exists':True,'fields':{'ITM0_1.ITMREF':'QATEST201','ITM0_1.DES1AXX':'Article de verification' if matching else 'Autre designation'}})
    s=step(c,s,'execute',True).json();v=s['state']['articles'][0]['operation']['verification']
    assert v['sql_verified'] is True and v['sage_consultation_verified'] is matching and not v['business_operations_verified']

def test_category_endpoints_require_owner_and_csrf(fixture,simulated):
    from fastapi.testclient import TestClient
    from app.main import app
    c,_=fixture;s,owner=seed(c)
    raw={'revision':s['revision'],'code':'QAT01','designation':'Controle','nom_court':'CONTROLE','modele':'GEN','gestion_stock':1,'achete':2,'vendu':2,'fabrique':1,'livrable':2,'sous_traite':1,'receptionne':2,'unite':'UN','code_comptable':'STD','taxe':'T20'}
    url='/api/v1/chat/conversations/'+str(s['id'])+'/categories/drafts'
    other=TestClient(app);other.headers['Origin']='http://testserver'
    r=other.post('/api/v1/chat/auth/register',json={'email':'other-'+uuid4().hex+'@example.test','display_name':'Autre utilisateur','password':'Integration-test-password-2026!'})
    other.headers['X-Chat-CSRF']=r.json()['csrf'];assert other.post(url,json=raw).status_code==404
    r=c.post(url,json=raw);assert r.status_code==200,r.text
    assert r.json()['state']['category_drafts'][0]['operation']['status']=='prepared'
    c.headers['X-Chat-CSRF']='wrong';assert c.post(url,json={**raw,'revision':r.json()['revision']}).status_code==403
    assert not any(x for _,x in simulated[1])

def test_legacy_site_creation_cannot_append_to_atomic_sql_article(fixture,simulated):
    c,_=fixture;s,owner=seed(c);s=step(c,s,'prepare').json()
    assert step(c,s,'site-prepare').status_code==423
    assert not any(x for _,x in simulated[1])

def test_batch_deadline_preserves_drafts_without_starting_more_sql(simulated,monkeypatch):
    times=iter((0,91,92));monkeypatch.setattr(dialogue,'monotonic',lambda:next(times))
    state={'articles':[article(),article(code_article='QATEST202')]}
    reply=dialogue.prepare_state(state)
    assert len(state['articles'])==2 and all(a['operation']['status']=='blocked' for a in state['articles'])
    assert 'délai' in reply and not simulated[1]

@pytest.mark.parametrize('text,category,stock,sold',[
    ('3afak, article bla stock, kanchriwh w kanbi3ouh','AVNS','1','2'),
    ('had article mstocki, kanchriwh, ma kaytba3ch','AVT','2','1'),
    ('article non gere en stock, achete et vendu','AVNS','1','2')])
def test_literal_business_parameters_french_and_darija(simulated,text,category,stock,sold):
    a=article(categorie=category);state={'articles':[a]};dialogue.prepare_state(state,text,copy.deepcopy(state))
    assert a['gestion_stock']==stock and a['vendu']==sold and a['achete']=='2'
    assert a['operation']['status']=='prepared'

def test_unrequested_model_and_statistical_settings_are_not_invented(simulated):
    assert not chat.grounded('modele_article','CARTON','article CARTON, categorie AVNS')
    assert chat.grounded('modele_article','TESTART201','modele article: TESTART201')
    a=article(familles_statistiques=['INVENTED']);state={'articles':[a]};dialogue.prepare_state(state,'article de verification',{'articles':[]})
    assert a['familles_statistiques'] is None

def test_qwen_single_article_schema_does_not_invite_technical_defaults(simulated):
    from app.services.chat_model import sql_article_schema
    schema=sql_article_schema('Article CARTON, code article: QA201, categorie AVNS, unite UN, sites 201 et 202, fournisseurs F994 et F007',{})
    keys=set(schema['properties']['articles']['items']['properties'])
    assert keys=={'designation','code_article','categorie','unite','site'}

def test_disabling_sql_preserves_its_route_without_soap_fallback(fixture,simulated):
    c,_=fixture;s,owner=seed(c);s=step(c,s,'prepare').json();settings.sage_article_sql_enabled=False
    assert chat.read(owner,UUID(str(s['id'])))['state']['articles'][0]['execution']['route']=='sql_test'
    assert step(c,s,'approve',True).status_code==423
    assert not any(x for _,x in simulated[1])

def test_initial_multiple_articles_do_not_share_codes_sites_or_providers(simulated):
    a=article(designation='Carton A',code_article='QAONE');b=article(designation='Carton B',code_article='QATWO',categorie='AVT',requested_sites=['202'],fournisseurs=[])
    state={'articles':[a,b]}
    dialogue.prepare_state(state,'article Carton A, code article: QAONE, categorie: AVNS, site 201, fournisseur F994; article Carton B, code article: QATWO, categorie: AVT, site 202, sans fournisseur.',{'articles':[]})
    assert [x['operation']['status'] for x in state['articles']]==['prepared','prepared']
    assert [x['operation']['plan']['code'] for x in state['articles']]==['QAONE','QATWO']
    assert a['requested_sites']==['201'] and b['requested_sites']==['202']
    assert a['fournisseurs'][0]['code']=='F994' and b['fournisseurs']==[]
