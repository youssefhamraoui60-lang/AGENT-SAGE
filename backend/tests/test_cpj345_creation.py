"""CPJ345 regression and general article/site lifecycle. No real Sage writes."""
from copy import deepcopy
from pathlib import Path
from datetime import date,timedelta
import json
import pytest
from app.services import conversation_chat as chat,chat_fast_extract as fast,chat_tools,chat_general_articles as actions,chat_general_sites as sites,sage_crud as crud,sage_article_rules as rules_module
from app.services.article_execution import legacy_scope
from app.services.sage_gateway import RESOURCES,projection,digest
from app.services.sage_soap import parse_xml
from test_conversation_chat import fixture,create

TEXT="Je veux créer l'article CPJ345 Y45 dans le système, catégorie NEG, TVA 10."
TYPO="je veux créer l'articles CPJ345 Y45 dasn le systéme avce la catigorier NEG et le TVA 10"


@pytest.mark.parametrize('text',[TEXT,TYPO])
def test_initial_request_has_no_invented_unit_or_stock(text):
    delta,trace=fast.extract(text,{'articles':[]});state=chat.merge({'articles':[]},delta,text);a=state['articles'][0]
    assert (a['designation'],a['code_article'],a['categorie'],a['taux_tva'])==('CPJ345 Y45','CPJ345-Y45','NEG','10')
    assert a['unite'] is None and a['gestion_stock'] is None and not trace['real_model_called']
    assert not chat.grounded('unite','L',text)


def test_hallucinated_model_unit_L_is_rejected_even_when_json_is_valid():
    delta=chat.model.Delta(intent='new',articles=[{'designation':'CPJ345 Y45','unite':'L','gestion_stock':'1'}])
    a=chat.merge({'articles':[]},delta,TEXT)['articles'][0]
    assert a['unite'] is None and a['gestion_stock'] is None
    assert not chat.grounded('unite','UN','Créer un article CPJ345 Y45')


@pytest.mark.parametrize('text',['CRÉER LE ARTICLES','CR2ER LE ARTICLES',"Créer l'article",'Valider et créer','Lance la création','Enregistre cet article'])
def test_creation_verbs_request_approval_without_authorizing_write(text):
    initial,_=fast.extract(TEXT,{'articles':[]});s=chat.merge({'articles':[]},initial,TEXT)
    delta,trace=fast.extract(text,s);after=chat.merge(s,delta,text)
    assert len(after['articles'])==1 and after['last_turn']['creation_requested']
    assert after['creation_request']['write_approved'] is False
    assert after['articles'][0]['unite'] is None and not trace['real_model_called']


def rulebook():
    combos=[{'ITM3_1.STU':u,'ITM3_1.PUU':u,'ITM3_1.SAU':u,'ITM3_1.PUUSTUCOE':'1','ITM3_1.SAUSTUCOE':'1'} for u in ['UN','M2','L']]
    taxes=[{'ITM5_1.VACITM':['T20','','']},{'ITM5_1.VACITM':['T10','','']}]
    allowed=['ITM0_1.DES1AXX','ITM0_1.TCLCOD','ITM0_1.ITMSTA',*combos[0],'ITM5_1.VACITM','ITM2_1.STOMGTCOD']
    category={'active':True,'manual_keys':True,'statuses':['1'],'units':{k:['UN','M2','L'] for k in ['STU','PUU','SAU']},'unit_combinations':combos,
        'allowed_fields':allowed,'required_fields':[],'tax_fields':['ITM5_1.VACITM'],'tax_combinations':taxes,'tax_default_verified':True,'tax_default_fields':taxes[0],
        'requires_article_site':False,'supplier_required':False,'supplier_fields':[],'stock_management':['1','2'],
        'tax_contexts':[{'reviewed':True,'rate':'10','site':'201','company':'20','regime':'MAR','vat_code':'T10','level':'T10','valid_from':'2026-01-01','valid_to':'2030-12-31','fields':taxes[1]}]}
    return {'required_fields':[],'active_units':['UN','M2','L'],'categories':{'NEG':category,'RAW':deepcopy(category)}}


class FakeSage:
    records={};writes=[];mode='ok'
    def __init__(self,resource):self.resource=resource;self.spec=RESOURCES[resource]
    def describe(self):return parse_xml((Path(__file__).resolve().parents[2]/('runtime/crud-'+self.spec['publication']+'-description.xml')).read_bytes())
    def read(self,keys,describe=True):
        row=self.records.get((self.resource,tuple(sorted(keys.items()))))
        return {'exists':row is not None,'fields':deepcopy(row or {}),'fingerprint':digest(row or {})}
    def write_once(self,action,keys,xml,identifier):
        assert action=='create';key=(self.resource,tuple(sorted(keys.items())));assert key not in self.records
        self.writes.append((self.resource,keys))
        if self.mode=='refused' or self.mode=='child_refused' and self.resource=='article-sites':return {'status':0,'messages':['CONTROLLED FIXTURE REFUSAL']}
        self.records[key]=projection(parse_xml(xml.encode()))
        if self.mode=='ambiguous':raise RuntimeError('CONTROLLED UNKNOWN OUTCOME')
        return {'status':1,'messages':['CONTROLLED FIXTURE; NO SAGE REQUEST']}


@pytest.fixture
def workflow(fixture,monkeypatch):
    client,queue=fixture;FakeSage.records={};FakeSage.writes=[];FakeSage.mode='ok';actions.PERMITS.clear();sites.PERMITS.clear()
    ready={'value':False};rules=rulebook()
    monkeypatch.setattr(crud,'security',lambda *a,**k:{'ready':ready['value'],'blockers':[] if ready['value'] else ['CONTROLLED_CLOSED_GATE'],'folder':'TEST'})
    for module in [crud,actions,sites]:monkeypatch.setattr(module,'Gateway',FakeSage)
    site_rules={'sites':{'201':{'company':'20','fields':{'ITF1_2.ABCCLS':'1'},'required_fields':['ITF1_2.ABCCLS'],'sql_mapping':{'ITF1_2.ABCCLS':'ABCCLS_0'}}}}
    def load(hash_,resource='articles'):return deepcopy(site_rules if resource=='article-sites' else rules)
    monkeypatch.setattr(actions,'load_rules',load);monkeypatch.setattr(sites,'load_rules',load);monkeypatch.setattr(rules_module,'load_rules',load)
    def sql(calls):
        out={}
        for call in calls:
            tool=call['tool'];args=call['args'];rows=[];code=args.get('Code','')
            master=FakeSage.records.get(('articles',(('ITMREF',code),)))
            if tool in ('check_article_duplicate','get_article_record') and master:
                from app.services.article_readback import MAPPING
                r={'ITMREF_0':code}
                for path,columns in MAPPING.items():
                    if path in master:
                        values=master[path] if isinstance(master[path],list) else [master[path]]
                        r.update(zip(columns,values))
                rows=[r]
            elif tool=='get_article_categories' and args.get('Category') in rules['categories']:rows=[{'TCLCOD_0':args['Category'],'STU_0':'UN','STOFCY_0':' ','VACITM_0':'T20','STOMGTCOD_0':2}]
            elif tool=='get_units':rows=[{'UOM_0':x} for x in {args.get('Unit'),args.get('Unit2')} if x]
            elif tool=='get_sites' and args.get('Site','') in ('','201'):rows=[{'FCY_0':'201','LEGCPY_0':'20','CRY_0':'MA','WRHFLG_0':2}]
            elif tool=='get_tax_rules':rows=[{'VAT_0':'T10','VATRAT_0':10,'CPY_0':' ','LEG_0':' '}]
            elif tool=='get_tax_determination_by_vat':rows=[{'VAT_0':'T10','VACITM_0':'T10','VACBPR_0':'MAR','ENAFLG_0':2}]
            elif tool=='get_tax_determination':rows=[{'VAT_0':'T20','VACITM_0':'T20','VACBPR_0':'MAR','ENAFLG_0':2}]
            elif tool in ('get_article_site','get_article_site_record'):
                child=FakeSage.records.get(('article-sites',tuple(sorted({'ITMREF':code,'STOFCY':args['Site']}.items()))))
                if child:rows=[{'ITMREF_0':code,'STOFCY_0':args['Site'],'ABCCLS_0':child.get('ITF1_2.ABCCLS')}]
            out[call['id']]={'ok':True,'rows':rows,'source':'SQL TEST','controlled_fixture':True}
        return out
    monkeypatch.setattr(chat_tools,'run',sql)
    async def extract(text,state,*a):
        value=fast.extract(text,state)
        assert value is not None,text
        return value
    monkeypatch.setattr(chat.model,'extract',extract)
    s=create(client)
    return client,s,ready,rules


def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});assert r.status_code==200,r.text
    return r.json()


def act(c,s,step,confirm=False,site=None):
    return c.post('/api/v1/chat/conversations/'+s['id']+'/articles/'+s['state']['articles'][0]['id']+'/'+step,json={'revision':s['revision'],'confirm':confirm,'site':site})


def prepared(workflow):
    c,s,ready,rules=workflow;s=send(c,s,TEXT)
    for message in ['Site 101','Site 201','NEG','unité UN']:s=send(c,s,message)
    ready['value']=True;s=send(c,s,'CR2ER LE ARTICLES')
    assert s['state']['articles'][0]['operation']['status']=='prepared'
    return c,s,ready,rules


def test_exact_conversation_blocks_missing_unit_and_preserves_site_correction(workflow):
    c,s,ready,rules=workflow;s=send(c,s,TYPO)
    for message in ['Site 101','Site 201','NEG','CRÉER LE ARTICLES']:s=send(c,s,message)
    a=s['state']['articles'][0]
    assert a['unite'] is None and a['site']=='201' and a['categorie']=='NEG' and a['taux_tva']=='10'
    assert a['execution']['route']=='general_test' and not a.get('operation') and not FakeSage.writes
    assert 'BLOQUÉ' in s['messages'][-1]['content']
    assert 'web_test_requires_NEG_UN' not in a['checks']['creation_blockers']
    assert a['execution']['tax']['default_differs_from_rate_code']


def test_generic_save_confirms_exact_tax_sql_and_does_not_create_site(workflow):
    c,s,ready,rules=prepared(workflow)
    assert not FakeSage.writes and act(c,s,'execute',True).status_code==403
    s=send(c,s,'oui');assert not FakeSage.writes and not s['state']['articles'][0].get('approved')
    r=act(c,s,'approve',True);assert r.status_code==200,r.text;s=r.json()
    token=actions.PERMITS[s['state']['articles'][0]['id']]['token'];assert token not in json.dumps(s)
    r=act(c,s,'execute',True);assert r.status_code==200,r.text;s=r.json();a=s['state']['articles'][0]
    assert a['outcome']['confirmed'] and a['outcome']['comparisons']['VACITM_0']
    assert a['outcome']['site_creation_executed'] is False and [x[0] for x in FakeSage.writes]==['articles']
    assert 'CRÉÉ' in s['messages'][-1]['content'] and act(c,s,'execute',True).status_code==409


@pytest.mark.parametrize('mode',['refused','ambiguous'])
def test_save_refusal_or_ambiguity_never_claims_created(workflow,mode):
    c,s,ready,rules=prepared(workflow);FakeSage.mode=mode;s=act(c,s,'approve',True).json();r=act(c,s,'execute',True);assert r.status_code==200,r.text
    s=r.json();assert not s['state']['articles'][0]['outcome']['confirmed']
    assert 'RÉSULTAT INCERTAIN' in s['messages'][-1]['content'] and len(FakeSage.writes)==1
    assert act(c,s,'execute',True).status_code==409


def test_tax_rate_existence_does_not_replace_context_review(workflow):
    c,s,ready,rules=workflow;s=send(c,s,TEXT);s=send(c,s,'Site 201');s=send(c,s,'unité UN')
    rules['categories']['NEG']['tax_contexts']=[];ready['value']=True;s=send(c,s,'Lance la création')
    assert not s['state']['articles'][0].get('operation') and not FakeSage.writes
    assert 'TVA demandée non validée' in s['messages'][-1]['content']


def test_non_demo_category_unit_and_code_use_reviewed_rules(workflow):
    c,s,ready,rules=workflow;s=send(c,s,'Créer un article Autre Matière, catégorie RAW, unité M2, site 201')
    ready['value']=True;s=send(c,s,'Enregistre cet article');a=s['state']['articles'][0]
    assert a['operation']['status']=='prepared' and not a['code_article'].startswith('TEST')
    assert a['categorie']=='RAW' and a['unite']=='M2' and a['execution']['route']=='general_test'


def test_optional_supplier_and_reviewed_non_stock(workflow):
    c,s,ready,rules=prepared(workflow)
    s=send(c,s,'Gestion stock 1')
    assert s['state']['articles'][0]['operation']['status']=='prepared'
    payload=s['state']['articles'][0]['operation']['payload']['fields']
    assert any(f['name']=='STOMGTCOD' and f['value']=='1' for f in payload)
    assert not any(f['name']=='BPSNUM' for f in payload)


def test_article_site_is_separately_approved_saved_and_verified(workflow):
    c,s,ready,rules=prepared(workflow);s=act(c,s,'approve',True).json();s=act(c,s,'execute',True).json()
    r=act(c,s,'site-prepare',site='201');assert r.status_code==200,r.text;s=r.json()
    assert len(FakeSage.writes)==1 and act(c,s,'site-execute',True,site='201').status_code==403
    s=act(c,s,'site-approve',True,site='201').json();r=act(c,s,'site-execute',True,site='201');assert r.status_code==200,r.text;s=r.json()
    child=s['state']['articles'][0]['strict_site_operations']['201']
    assert child['confirmed'] and [x[0] for x in FakeSage.writes]==['articles','article-sites']
    assert act(c,s,'site-execute',True,site='201').status_code==409


def test_article_created_but_site_save_refused_is_not_full_success(workflow):
    c,s,ready,rules=prepared(workflow);s=act(c,s,'approve',True).json();s=act(c,s,'execute',True).json();FakeSage.mode='child_refused'
    s=act(c,s,'site-prepare',site='201').json();s=act(c,s,'site-approve',True,site='201').json();r=act(c,s,'site-execute',True,site='201');assert r.status_code==200,r.text
    a=r.json()['state']['articles'][0];assert a['outcome']['confirmed'] and not a['strict_site_operations']['201']['confirmed']


def test_changed_draft_consumes_pending_approval_without_save(workflow):
    c,s,ready,rules=prepared(workflow);s=act(c,s,'approve',True).json()
    s=send(c,s,'unité M2')
    assert not s['state']['articles'][0].get('approved') and not FakeSage.writes
    assert act(c,s,'execute',True).status_code in (403,409)


def test_duplicate_appearing_after_preparation_blocks_approval(workflow):
    c,s,ready,rules=prepared(workflow)
    FakeSage.records[('articles',(('ITMREF','CPJ345-Y45'),))]={'ITM0_1.DES1AXX':'EXISTING'}
    assert act(c,s,'approve',True).status_code==409
    assert not FakeSage.writes


def test_connection_failure_in_prepare_preserves_extraction(workflow,monkeypatch):
    import requests
    c,s,ready,rules=workflow;s=send(c,s,TEXT);s=send(c,s,'Site 201');s=send(c,s,'unité UN')
    def unavailable(self):raise requests.Timeout('CONTROLLED FIXTURE')
    monkeypatch.setattr(FakeSage,'describe',unavailable);ready['value']=True
    s=send(c,s,'Lance la création');a=s['state']['articles'][0]
    assert a['designation']=='CPJ345 Y45' and a['unite']=='UN'
    assert a['write_status']['status']=='blocked' and not a['write_status']['save_sent']
    assert 'connexion Sage indisponible' in s['messages'][-1]['content'] and not FakeSage.writes
