"""No Sage writes: policies, TEST plans, private chat, durable audit and confirmations."""
import sys,json,copy,importlib
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timedelta,timezone
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from test_conversation_chat import fixture,create
from app.core.config import settings
from app.services import erp_modification as mod,modification_actions as actions,modification_dialogue as dialogue,conversation_chat as chat,business_store as db,sage_crud as crud
from app.services.modification_resolvers import CategoryResolver,UnitResolver
from app.services.modification_policy import ArticleDependencyAnalyzer,ArticleModificationPolicy
REAL_SEMANTIC_CHANGES=dialogue.semantic_changes

def data():return json.loads((ROOT/'TEST/fixtures/modification-schema.json').read_text())
def draft(resource='article',**changes):return {'id':str(uuid4()),'folder':'TEST','resource':resource,'code':'TESTART201' if resource=='article' else 'F994' if resource=='supplier' else 'SC3','changes':changes}
def proof(plan,execute=False):return {'ok':True,'folder':'TEST','resource':plan['resource'],'code':plan['code'],'executed':execute,'verified':execute,'affected':len(plan['nodes']) if execute else 0,'transaction_state':'COMMIT' if execute else 'VALIDATED_NO_WRITE','records':[{'tab':n['table'],'kind':n['kind'],'affected':int(execute)} for n in plan['nodes']]}

@pytest.fixture
def simulated(monkeypatch):
    # These tests mock the Ollama wire response; never contact configured cloud.
    monkeypatch.setattr(settings,'ai_provider','ollama')
    fixture=data();schema=fixture['schema'];article=fixture['article'];calls=[]
    article['menus'].extend({'CODFIC_0':'ITMMASTER','CODZONE_0':field,'LANNUM_0':value,'LANMES_0':label} for field in ('NEGSTO','XFLGBPS') for value,label in ((1,'Non'),(2,'Oui')))
    supplier={**copy.deepcopy(article),**fixture['supplier'],'resource':'supplier','code':'F994'}
    supplier['dependencies']={'complete':True,'coverage':'TEST_schema_and_Sage_dictionary','sources':[{'tab':t,'readable':True,'has_matches':t in ('BPARTNER','BPSUPPLIER','BPADDRESS'),'columns_checked':'BPSNUM_0'} for t in ('BPARTNER','BPSUPPLIER','BPADDRESS','PORDER','PINVOICE','PAYMENTH')]}
    monkeypatch.setattr(settings,'sage_modification_enabled',True);monkeypatch.setattr(settings,'sage_mcp_enabled',False)
    monkeypatch.setattr(mod,'catalog',lambda:copy.deepcopy(schema))
    def snapshot(resource,code):
        view=copy.deepcopy(supplier if resource=='supplier' else article);view['resource']=resource;view['code']=code;return view
    monkeypatch.setattr(mod,'snapshot',snapshot)
    monkeypatch.setattr(dialogue,'read_current_record',lambda resource,code:actions.current_values(snapshot(resource,code)))
    def transport(action,resource='',code='',plan=None,execute=False):
        assert action=='plan';calls.append((copy.deepcopy(plan),execute));return proof(plan,execute)
    monkeypatch.setattr(mod,'transport',transport)
    model=json.loads((ROOT/'TEST/fixtures/article-sql-schema.json').read_text());monkeypatch.setattr(mod.article_sql,'catalog',lambda *a,**k:copy.deepcopy(model))
    monkeypatch.setattr(dialogue,'semantic_changes',lambda *args:{})
    actions.PERMITS.clear()
    return schema,article,supplier,calls

def build(simulated,d):return mod.build(d,simulated[0],simulated[2] if d['resource']=='supplier' else simulated[1])
def mark(view,table,active=None):
    r=next(r for r in view['dependencies']['sources'] if r['tab']==table);r['has_matches']=True
    if active is not None:r['active']=active

@pytest.mark.parametrize('table',['PORDERQ','PRECEIPTD','PINVOICED','SORDERQ','SDELIVERYD','SINVOICED','STOJOU','STOALL','STOCK','CUNLISDET','MFGITM','OTHER_DOCUMENT'])
@pytest.mark.parametrize('changes',[{'designation':'NOUVEL INTITULE'},{'category':'AVNS'},{'stock_unit':'UN'},{'stock_mode':1}])
def test_history_locks_identity_related_changes_even_closed(simulated,table,changes):
    mark(simulated[1],table,False)
    with pytest.raises(crud.CrudError,match='déjà utilisé'):build(simulated,draft(**changes))
    assert not simulated[3]

@pytest.mark.parametrize('key',['code','code_article','ITMREF_0','BPSNUM_0','BPRNUM_0'])
def test_unique_codes_are_immutable(simulated,key):
    with pytest.raises(crud.CrudError,match='code unique'):build(simulated,draft(**{key:'NEWCODE'}))

def test_unused_designation_updates_master_sales_and_fra_together(simulated):
    plan=build(simulated,draft(designation='NOUVEL INTITULE'))
    assert {n['table'] for n in plan['nodes']}=={'ITMMASTER','ATEXTRA','ITMSALES'}
    assert all('ITMREF_0' not in n['values'] for n in plan['nodes'])

@pytest.mark.parametrize('changes',[{'accounting':'61253000'},{'tax_level':{'index':0,'code':'T10'}}])
def test_financial_changes_possible_on_used_article_with_specific_confirmation(simulated,changes):
    mark(simulated[1],'PINVOICED',False);plan=build(simulated,draft(**changes))
    assert plan['policy']['sensitive'] and plan['policy']['future_only'] and not plan['policy']['history_writes']
    assert all(n['table']=='ITMMASTER' for n in plan['nodes'])
    assert any(g['table'] in ('TABVACITM','GACCCODE') for g in plan['guards'])

@pytest.mark.parametrize('changes',[{'tax_rate':'10'},{'tax_level':{'index':3,'code':'T10'}},{'tax_level':{'index':0,'code':'T99'}},{'accounting':'INVENTED'}])
def test_no_inferred_tax_or_accounting(simulated,changes):
    with pytest.raises(crud.CrudError):build(simulated,draft(**changes))

@pytest.mark.parametrize('changes',[{'deactivate':True},{'purchase_unit':{'code':'SC2','coefficient':'25'}},{'sale_unit':{'code':'SC2'}},{'supplier_reference':{'code':'F994','reference':'X'}},{'remove_sites':['201']},{'remove_suppliers':['F994']},{'replace_supplier':{'old':'F994','new':'F007'}}])
@pytest.mark.parametrize('active',[True,None])
def test_active_or_unproven_closure_blocks_operations(simulated,changes,active):
    mark(simulated[1],'PORDERQ',active)
    with pytest.raises(crud.CrudError):build(simulated,draft(**changes))

def test_closed_document_still_counts_as_used_but_not_as_open(simulated):
    mark(simulated[1],'SDELIVERYD',False);plan=build(simulated,draft(deactivate=True))
    assert plan['analysis']['used'] and not plan['analysis']['active'] and not plan['analysis']['unknown_activity']
    assert plan['nodes'][0]['values']['ITMSTA_0']==6

@pytest.mark.parametrize('key',['remove_sites','remove_suppliers'])
def test_no_physical_deletion_even_without_dependencies(simulated,key):
    with pytest.raises(crud.CrudError,match='retrait physique'):build(simulated,draft(**{key:['201']}))

def test_supplier_replacement_keeps_old_association_and_sets_new_principal(simulated):
    simulated[1]['article_suppliers']=[{'ITMREF_0':'TESTART201','BPSNUM_0':'F994','ITMREFBPS_0':'OLDREF','PUU_0':'UN','source_hash':'A'*64}]
    plan=build(simulated,draft(replace_supplier={'old':'F994','new':'F007'}))
    assert all(n['kind'] in ('insert','update') for n in plan['nodes'])
    assert any(n['table']=='ITMBPS' and n['keys']['BPSNUM_0']=='F007' for n in plan['nodes'])
    assert any(n['table']=='ITMMASTER' and n['values']['XBPS_0']=='F007' for n in plan['nodes'])
    assert 'ancienne association est conservée' in plan['impact']

def test_missing_dependency_permission_is_not_an_unused_article(simulated):
    simulated[1]['dependencies']['sources'][-1]['readable']=False
    with pytest.raises(crud.CrudError,match='incomplète'):build(simulated,draft(accounting='61253000'))

def test_trigger_without_review_blocks_update_but_does_not_escalate_permissions(simulated):
    simulated[0]['triggers']=[{'table':'ITMMASTER','name':'ITMMASTER_UPDTICK','is_disabled':False}]
    with pytest.raises(crud.CrudError,match='Déclencheur'):build(simulated,draft(accounting='61253000'))
    assert not simulated[3]

def test_missing_update_right_is_precise(simulated):
    next(r for r in simulated[0]['permissions'] if r['table']=='BPADDRESS')['can_update']=0
    with pytest.raises(crud.CrudError,match='UPDATE.*TEST.BPADDRESS'):build(simulated,draft('supplier',phone='0600000099'))

def test_supplier_used_allows_current_coordinates_but_not_legal_or_bank_rewrite(simulated):
    mark(simulated[2],'PINVOICE',False)
    plan=build(simulated,draft('supplier',phone='0600000099',email='new@example.test',address='Nouvelle adresse'))
    assert all(n['table']=='BPADDRESS' for n in plan['nodes'])
    for change in ({'ice':'001234567890124'},{'name':'AUTRE NOM'},{'bank_account':'123456'}):
        with pytest.raises(crud.CrudError):build(simulated,draft('supplier',**change))

def test_supplier_tax_ids_preserve_zeros_and_require_specific_confirmation(simulated):
    plan=build(simulated,draft('supplier',ice='000000000000001',**{'if':'00001234'}))
    assert plan['nodes'][0]['values']['XICE_0']=='000000000000001' and plan['policy']['sensitive']

def test_address_uses_three_real_lines_without_truncation(simulated):
    text='Boulevard de verification numero 25 quartier industriel zone commerciale avenue de controle'
    node=build(simulated,draft('supplier',address=text))['nodes'][0]
    lines=[node['values']['BPAADDLIG_'+str(i)] for i in range(3)]
    assert max(map(len,lines))<=50 and ' '.join(x for x in lines if x)==text
    with pytest.raises(crud.CrudError):build(simulated,draft('supplier',address='x'*151))

def test_category_search_uses_real_codes_compatible_parameters_and_pagination():
    rows=[{'TCLCOD_0':'N'+str(i),'TCLDES_0':'Negoce '+str(i),'STOFCY_0':'','STOMGTCOD_0':1,'ENAFLG_0':2} for i in range(10)]
    rows.append({'TCLCOD_0':'BAD','TCLDES_0':'Negoce','STOFCY_0':'','STOMGTCOD_0':2,'ENAFLG_0':2})
    resolver=CategoryResolver();first=resolver.search('negouse',rows,{'STOMGTCOD_0':1});rest=resolver.search('negouse',rows,{'STOMGTCOD_0':1},[r['code'] for r in first],5)
    assert len(first)==3 and len(rest)==5 and not {r['code'] for r in first}&{r['code'] for r in rest}
    assert all(r['code']!='BAD' and r['requires_selection'] for r in first+rest)
    assert resolver.search('COMPLETEMENT INCONNU',[] )==[]

def test_existing_unit_conversion_has_exact_direction_and_inverse(simulated):
    resolver=UnitResolver();assert resolver.coefficient('SC2','KG',simulated[1],'25')=='25.0'
    assert resolver.coefficient('KG','SC2',simulated[1],'.04')=='0.04'
    with pytest.raises(crud.CrudError):resolver.coefficient('SC2','KG',simulated[1],'24')
    with pytest.raises(crud.CrudError):resolver.coefficient('SAC','KG',simulated[1])
    simulated[1]['conversions'].pop()
    with pytest.raises(crud.CrudError):resolver.coefficient('SC2','KG',simulated[1])

def test_new_unit_blocks_missing_permission_and_never_copies_international_code(simulated):
    d=draft('unit',model='SAC',stock_unit='KG',coefficient='25',inverse='.04')
    with pytest.raises(crud.CrudError,match='INSERT manquant'):build(simulated,d)
    for r in simulated[0]['permissions']:
        if r['table'] in ('TABUNIT','TABCOEFF'):r['can_insert']=1
    plan=build(simulated,d);assert len(plan['nodes'])==3 and plan['policy']['sensitive']
    assert plan['nodes'][0]['values']['INTSAU_0']==''
    d['changes']['inverse']='.05'
    with pytest.raises(crud.CrudError):build(simulated,d)

def test_new_unit_does_not_duplicate_existing_unit(simulated):
    d=draft('unit',model='SAC',stock_unit='KG',coefficient='25',inverse='.04');d['code']='SC2'
    with pytest.raises(crud.CrudError,match='existe déjà'):build(simulated,d)

def test_added_site_and_provider_are_scoped_to_the_existing_article(simulated):
    simulated[1]['articles'][0]['XBPS_0']=''
    plan=build(simulated,draft(add_sites=['202'],add_suppliers=[{'code':'F007','reference':''}]))
    site=[n for n in plan['nodes'] if n['table']=='ITMFACILIT'];providers=[n for n in plan['nodes'] if n['table']=='ITMBPS']
    assert len(site)==1 and site[0]['keys']=={'ITMREF_0':'TESTART201','STOFCY_0':'202'}
    assert len(providers)==1 and providers[0]['values']['ITMREFBPS_0']=='TESTART201_F007'
    assert not any(n['table'] in ('ATEXTRA','ITMSALES') for n in plan['nodes'])
    with pytest.raises(crud.CrudError):build(simulated,draft(add_sites=['201']))

@pytest.mark.parametrize('text,resource,expected',[
 ('Change le code ART001 en ART002.','article',{'code':'ART002'}),
 ('Change le code comptable de l’article ART001 en STD.','article',{'accounting':'STD'}),
 ('Change la TVA de l’article ART001 à 10 %.','article',{'tax_rate':'10'}),
 ('Modifie la taxe de l’article ART001 : T10 indice 0','article',{'tax_level':{'index':0,'code':'T10'}}),
 ('Ajoute F007 comme fournisseur de ART001.','article',{'add_suppliers':[{'code':'F007','reference':''}]}),
 ('Cet article existe seulement sur 201, ajoute 202.','article',{'add_sites':['202']}),
 ('Remplace le fournisseur F994 par F468.','article',{'replace_supplier':{'old':'F994','new':'F468'}}),
 ('Change la catégorie de cet article en négoce.','article',{'category':'négoce'}),
 ('Change son unité d’achat en SC2, avec 25 KG par sac.','article',{'purchase_unit':{'code':'SC2','coefficient':'25'}}),
 ('Modifie l’adresse du fournisseur F994 en Nouvelle adresse.','supplier',{'address':'Nouvelle adresse'}),
 ('nbdel telephone du fournisseur F994 en 0600000099','supplier',{'phone':'0600000099'}),
 ('zid site 202','article',{'add_sites':['202']})])
def test_french_and_darija_requests_have_typed_changes(text,resource,expected):
    assert dialogue.parse_changes(text,resource)==expected

def create_draft(c,s,changes=None,resource='supplier'):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/modifications/drafts',json={'revision':s['revision'],'resource':resource,'code':'F994' if resource=='supplier' else 'TESTART201','changes':changes or {'phone':'0600000099'}})
    assert r.status_code==200,r.text;return r.json()
def step(c,s,name,confirm=False,sensitive=False):
    d=s['state']['modification_drafts'][-1]
    return c.post('/api/v1/chat/conversations/'+s['id']+'/modifications/'+d['id']+'/'+name,json={'revision':s['revision'],'confirm':confirm,'sensitive_confirm':sensitive})

def test_chat_confirmation_execution_audit_and_replay(fixture,simulated):
    c,q=fixture;s=create_draft(c,create(c));assert s['state']['modification_drafts'][0]['operation']['status']=='prepared'
    assert step(c,s,'approve').status_code==403 and step(c,s,'execute',True).status_code==403
    s=step(c,s,'approve',True).json();assert not any(execute for _,execute in simulated[3])
    r=step(c,s,'execute',True);assert r.status_code==200,r.text;s=r.json()
    assert s['state']['modification_drafts'][0]['operation']['status']=='succeeded'
    assert step(c,s,'execute',True).status_code==409
    records=c.get('/api/v1/chat/conversations/'+s['id']+'/modifications/audit').json()['events']
    assert {r['event'] for r in records}=={'prepared','approved','executing','succeeded'}
    assert records[0]['payload']['diff'][0]['before']=='0600000000'
    assert records[0]['payload']['diff'][0]['after']=='0600000099'
    assert sum(execute for _,execute in simulated[3])==1

def test_sensitive_confirmation_is_separate(fixture,simulated):
    c,_=fixture;s=create_draft(c,create(c),{'ice':'000000000000001'})
    assert step(c,s,'approve',True).status_code==403
    s=step(c,s,'approve',True,True).json();assert step(c,s,'execute',True).status_code==403
    assert not any(execute for _,execute in simulated[3])

@pytest.mark.parametrize('damage',['input','plan','query','expiry','owner','conversation','restart','revision','mcp','production'])
def test_changed_stale_or_foreign_confirmation_cannot_write(fixture,simulated,damage):
    c,_=fixture;s=create_draft(c,create(c));s=step(c,s,'approve',True).json();d=s['state']['modification_drafts'][0]
    if damage in ('input','plan','query','production'):
        with db.connection() as conn:
            row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s FOR UPDATE',(s['id'],)).fetchone();item=row['state']['modification_drafts'][0]
            if damage=='input':item['changes']['phone']='0600000088'
            elif damage=='plan':item['operation']['plan']['code']='F007'
            elif damage=='query':item['operation']['query_digest']='old'
            else:row['state']['supplier_target']='OB'
            chat.save_conversation_context(conn,row['owner_id'],UUID(s['id']),row['state'])
    elif damage=='expiry':actions.PERMITS[d['id']]['expires']=datetime.now(timezone.utc)-timedelta(seconds=1)
    elif damage in ('owner','conversation'):actions.PERMITS[d['id']][damage]=str(uuid4())
    elif damage=='restart':actions.PERMITS.clear()
    elif damage=='revision':s['revision']-=1
    else:settings.sage_mcp_enabled=True
    assert step(c,s,'execute',True).status_code in (403,409,423)
    assert not any(execute for _,execute in simulated[3])

@pytest.mark.parametrize('result,status',[({'ok':False,'transaction_state':'ROLLBACK'},'blocked'),({'ok':False,'outcome':'unknown'},'ambiguous')])
def test_rollback_or_unknown_does_not_claim_success(fixture,simulated,monkeypatch,result,status):
    c,_=fixture;s=create_draft(c,create(c));s=step(c,s,'approve',True).json();monkeypatch.setattr(mod,'transport',lambda *a,**k:result)
    r=step(c,s,'execute',True);assert r.status_code==200,r.text;s=r.json()
    assert s['state']['modification_drafts'][0]['operation']['status']==status
    assert step(c,s,'execute',True).status_code in (403,409)

def test_private_access_csrf_and_audit(fixture,simulated):
    from fastapi.testclient import TestClient
    from app.main import app
    c,_=fixture;s=create_draft(c,create(c));url='/api/v1/chat/conversations/'+s['id']+'/modifications/audit'
    other=TestClient(app);other.headers['Origin']='http://testserver'
    r=other.post('/api/v1/chat/auth/register',json={'email':'other-'+uuid4().hex+'@example.test','display_name':'Autre utilisateur','password':'Integration-test-password-2026!'});other.headers['X-Chat-CSRF']=r.json()['csrf']
    assert other.get(url).status_code==404 and step(other,s,'approve',True).status_code==404
    c.headers['X-Chat-CSRF']='invalid';assert step(c,s,'approve',True).status_code==403

def test_conversation_corrections_and_restart_keep_data_not_authority(fixture,simulated):
    c,q=fixture;s=create(c)
    for text in ('Modifie le telephone du fournisseur F994 en 0600000099','corrige le telephone en 0600000088','oui'):
        r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'revision':s['revision'],'content':text});assert r.status_code==200,r.text;s=r.json()
    d=s['state']['modification_drafts'][0];assert d['changes']['phone']=='0600000088' and d['operation']['status']=='prepared'
    assert not any(execute for _,execute in simulated[3]) and not q
    actions.PERMITS.clear();saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
    assert saved['state']['modification_drafts'][0]['changes']==d['changes']
    assert step(c,saved,'execute',True).status_code==403

def test_cancellation_revokes_consent_and_does_not_undo_existing_write(fixture,simulated):
    c,_=fixture;s=create_draft(c,create(c));s=step(c,s,'approve',True).json()
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'revision':s['revision'],'content':'annule la modification'});assert r.status_code==200,r.text
    s=r.json();assert s['state']['modification_drafts'][0]['operation']['status']=='cancelled'
    assert step(c,s,'execute',True).status_code==409 and not any(execute for _,execute in simulated[3])

def test_existing_creation_requests_are_not_intercepted(simulated):
    for text in ('Cree un article Carton, categorie AVNS, site 202','Ajoute un article Ciment','Cree un fournisseur Nouveau'):
        assert dialogue.turn(uuid4(),uuid4(),text,{}) is None

def test_audit_is_metered_and_deletion_frees_space(fixture,simulated):
    c,_=fixture;s=create_draft(c,create(c));events=c.get('/api/v1/chat/conversations/'+s['id']+'/modifications/audit').json()['events'];assert len(events)==1
    used=c.get('/api/v1/chat/storage').json()['used_bytes']
    with db.connection() as conn:
        owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()['owner_id']
        conn.execute('DELETE FROM chat_conversations WHERE id=%s AND owner_id=%s',(s['id'],owner))
        assert conn.execute('SELECT count(*) AS n FROM chat_modification_audit WHERE owner_id=%s',(owner,)).fetchone()['n']==0
    assert c.get('/api/v1/chat/storage').json()['used_bytes']<used

def test_chat_immutable_code_response_never_queries_or_prepares_new_fiche(simulated):
    result=dialogue.turn(uuid4(),uuid4(),'Change le code ART001 en ART002.',{})
    assert 'ART001 ne peut pas' in result['reply'] and 'ART002' in result['reply']
    assert not result['state'].get('modification_drafts') and not simulated[3]

def test_pending_modification_does_not_capture_memory_questions(simulated):
    state={'modification_drafts':[draft('supplier',phone='0600000099')]}
    assert dialogue.turn(uuid4(),uuid4(),'Que sais-tu de moi ?',state) is None
    assert dialogue.turn(uuid4(),uuid4(),'Retiens que je préfère des réponses courtes',state) is None

def test_incomplete_request_retains_target_and_accepts_next_value(fixture,simulated):
    c,_=fixture;s=create(c)
    for text in ('Change l’intitulé de l’article TESTART201','NOUVEL INTITULE'):
        r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'revision':s['revision'],'content':text});assert r.status_code==200,r.text;s=r.json()
    d=s['state']['modification_drafts'][0];assert d['code']=='TESTART201' and d['changes']=={'designation':'NOUVEL INTITULE'} and d['operation']['status']=='prepared'
    assert not any(e for _,e in simulated[3])

def test_current_article_pronoun_keeps_target_for_site_addition(simulated):
    current=draft(accounting='61253000');current['operation']={'status':'prepared'}
    result=dialogue.turn(uuid4(),uuid4(),'Cet article existe seulement sur 201, ajoute 202.',{'modification_drafts':[current]})
    assert result['state']['modification_drafts'][0]['code']=='TESTART201'
    assert result['state']['modification_drafts'][0]['changes']['add_sites']==['202']

def test_severe_spelling_and_darija_keep_literal_values(simulated):
    result=dialogue.turn(uuid4(),uuid4(),'modfie le tele du frs F994 en 0600000099',{})
    d=result['state']['modification_drafts'][0]
    assert d['resource']=='supplier' and d['code']=='F994' and d['changes']=={'phone':'0600000099'}

def test_correction_moves_the_same_value_without_inventing_supplier_data(simulated):
    current=draft('supplier',address='Berrechid');current['operation']={'status':'prepared'}
    result=dialogue.turn(uuid4(),uuid4(),'non, c’est la ville',{'modification_drafts':[current]})
    d=result['state']['modification_drafts'][0];assert d['changes']=={'city':'Berrechid'}

def test_existing_creation_draft_code_remains_editable_before_sage_creation(simulated):
    state={'articles':[{'id':str(uuid4()),'code_article':'DRAFT001','operation':{'status':'prepared'}}]}
    assert dialogue.turn(uuid4(),uuid4(),'Change le code article DRAFT001 en DRAFT002',state) is None

def test_unit_followup_preserves_first_message_values(simulated):
    first=dialogue.turn(uuid4(),uuid4(),'Cree une unite SC3 modele SAC unite stock KG',{})
    second=dialogue.turn(uuid4(),uuid4(),'coefficient 25 inverse 0,04',first['state'])
    d=second['state']['modification_drafts'][0];assert d['changes']=={'model':'SAC','stock_unit':'KG','coefficient':'25','inverse':'0.04'}
    assert d['operation']['status']=='blocked' and 'INSERT' in d['operation']['message']

def test_fallback_model_value_must_be_literal_and_never_provides_sql(simulated,monkeypatch):
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'done':True,'message':{'content':json.dumps({'changes':[{'field':'phone','value':'INVENTED'},{'field':'city','value':'Berrechid'},{'field':'sql','value':'DROP TABLE'}]})}}
    monkeypatch.setattr(dialogue.httpx.Client,'post',lambda *a,**k:Response())
    assert REAL_SEMANTIC_CHANGES('La ville correcte est Berrechid','supplier',{})=={'city':'Berrechid'}

def test_unsafe_or_incomplete_sql_proof_is_not_success(simulated):
    plan=build(simulated,draft('supplier',phone='0600000099'))
    for patch in ({'folder':'OB'},{'executed':False},{'affected':0},{'records':[]},{'transaction_state':'ROLLBACK'},{'verified':False}):assert not mod.verify(plan,{**proof(plan,True),**patch})

def test_live_transport_preserves_decimal_lexemes(monkeypatch):
    class Process:stdout='{"ok":true,"coefficient":1234567890123456.1234567}'
    monkeypatch.setattr(mod.subprocess,'run',lambda *a,**k:Process())
    assert mod.transport('catalog')['coefficient']=='1234567890123456.1234567'

def test_payment_label_uses_existing_shared_resolver_without_inventing_code(simulated,monkeypatch):
    monkeypatch.setattr(mod.supplier_sql,'load_reference_labels',lambda folder:[{'kind':'Paiement','code':'VIR30','label':'Virement 30 jours'}])
    plan=build(simulated,draft('supplier',payment='Virement 30 jours'))
    assert plan['nodes'][0]['values']['PTE_0']=='VIR30' and plan['policy']['sensitive']
    assert any(g['table']=='TABPAYTERM' for g in plan['guards'])

def test_contact_references_are_not_overwritten_with_unverified_free_text(simulated):
    with pytest.raises(crud.CrudError,match='CONTACT'):build(simulated,draft('supplier',contact_name='Nom invente'))

def test_missing_target_retains_phone_until_user_provides_code(simulated):
    first=dialogue.turn(uuid4(),uuid4(),'Modifie le telephone du fournisseur en 0600000099',{})
    assert first['state']['modification_pending_target']['resource']=='supplier'
    second=dialogue.turn(uuid4(),uuid4(),'F994',first['state']);d=second['state']['modification_drafts'][0]
    assert d['changes']=={'phone':'0600000099'} and d['code']=='F994' and d['operation']['status']=='prepared'

def test_quantities_preserve_precision_and_do_not_offset_positive_and_negative(simulated):
    view=simulated[1];r=next(r for r in view['dependencies']['sources'] if r['tab']=='STOCK')
    r.update(has_matches=True,active=True,evidence='[{"field":"QTYSTU_0","quantity":0.0000000,"absolute":1234567890123456.1234567}]')
    analysis=ArticleDependencyAnalyzer().analyze(view)
    assert analysis['active'] and analysis['quantities'][0]['absolute']=='1234567890123456.1234567'
    with pytest.raises(crud.CrudError):build(simulated,draft(deactivate=True))

def test_cancel_all_revokes_all_pending_modification_consents(fixture,simulated):
    c,q=fixture;s=create_draft(c,create(c));s=step(c,s,'approve',True).json()
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'revision':s['revision'],'content':'annule tout'});assert r.status_code==200,r.text
    s=r.json();assert s['state']['modification_drafts'][0]['operation']['status']=='cancelled'
    assert not actions.PERMITS and not q
    assert step(c,s,'execute',True).status_code==409

@pytest.mark.parametrize('verb',['Change','Modifie','modfie','bdel','nbdel','corrige'])
@pytest.mark.parametrize('field',['le nom','la designation','le code comptable','la TVA','l intitule'])
def test_thirty_bare_existing_article_update_routes(simulated,verb,field):
    text=verb+' '+field+' de TESTART203'+(' a 10 %' if field=='la TVA' else '')
    result=dialogue.turn(uuid4(),uuid4(),text,{})
    assert result is not None
    assert not result['state'].get('articles')
    rows=result['state'].get('modification_drafts') or []
    assert rows and rows[0]['resource']=='article' and rows[0]['code']=='TESTART203'
    assert not any(execute for _,execute in simulated[3])

def test_rate_uses_determination_not_tax_code_spelling():
    old={'COD_0':'MAR_OLD','VACBPR_0':'MAR','VACITM_0':'LEVEL20','VAT_0':'VAT20','ENAFLG_0':2,'source_hash':'A'*64}
    target={**old,'COD_0':'MAR_NEW','VACITM_0':'LEVEL10','VAT_0':'UNRELATED_NAME','source_hash':'B'*64}
    view={'articles':[{'VACITM_0':'LEVEL20','VACITM_1':'','VACITM_2':''}],'taxes':[{'VAT_0':'UNRELATED_NAME','VATRAT_0':'10.000','source_hash':'C'*64}],'tax_determinations':[old,target]}
    tax,guards=mod.resolve_tax_rate('10',view)
    assert tax=={'index':0,'code':'LEVEL10'} and len(guards)==3
    view['tax_determinations'].append({**target,'COD_0':'OTHER','VACITM_0':'ALTERNATIVE'})
    with pytest.raises(crud.CrudError):mod.resolve_tax_rate('10',view)

def test_account_number_never_becomes_an_accounting_code(simulated):
    assert dialogue.parse_changes('Change le compte general de TESTART203 en 61253000','article')=={'general_account':'61253000'}
    simulated[1]['general_accounts']=[{'ACC_0':'61253000','COA_0':'MAR'}]
    with pytest.raises(crud.CrudError,match='imputation'):build(simulated,draft(general_account='61253000'))

def test_unicode_expansion_does_not_drop_a_leading_zero():
    assert dialogue.parse_changes('modiﬁe le telephone du fournisseur F994 en 0600000099','supplier')=={'phone':'0600000099'}
    assert dialogue.parse_changes('bdel smiya dyal frs F10014 l FOURNISSEUR QA DARIJA','supplier')=={'name':'FOURNISSEUR QA DARIJA'}

def test_model_cannot_trim_tax_id_zeros_or_use_entire_command(simulated,monkeypatch):
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'done':True,'message':{'content':json.dumps({'changes':[{'field':'if','value':'12345678'},{'field':'name','value':'Modifie le nom du fournisseur F994 en NOM TEST'}]})}}
    monkeypatch.setattr(dialogue.httpx.Client,'post',lambda *a,**k:Response())
    assert REAL_SEMANTIC_CHANGES('IF 0012345678','supplier',{})=={}
    assert REAL_SEMANTIC_CHANGES('Modifie le nom du fournisseur F994 en NOM TEST','supplier',{})=={}

@pytest.mark.parametrize('coefficient',['NaN','sNaN','Infinity','1e1000000'])
def test_nonfinite_or_oversized_unit_coefficient_is_a_clear_block(simulated,coefficient):
    with pytest.raises(crud.CrudError):build(simulated,draft('unit',model='SAC',stock_unit='KG',coefficient=coefficient,inverse='.04'))
