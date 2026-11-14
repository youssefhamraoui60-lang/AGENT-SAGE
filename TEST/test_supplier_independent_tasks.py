"""Replay the user's 28 turns, separately per scenario; all Sage access mocked."""
import sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
import pytest
import httpx
from test_conversation_chat import fixture,create
from test_chat_supplier_sql import workflow
from app.core.config import settings
from app.services import chat_tools,erp_modification,supplier_chat_flow,supplier_tasks

GROUP=[
"bonjour je veux crrer 3 nevelle fourniseur en méme temp, tu peux m'aider ?",
"le premier c'est ATLAS NEGOCE TEST à casa, le 2eme MAGHREB OUTILLAGE TEST f rabat et le troisiéme c'est SUD SERVICES TEST à agadir",
"pour le premier c'est SARL AU, le 2eme SARL et le 3eme je connais pas encore la forme juridique",
"le fournisseur de rabat finalement smito MAGHREB INDUSTRIE TEST, corrige juste son nom, les autres touche pas",
"pour atlas je connais pas ICE ni téléphone daba, mais SUD SERVICES son téléphone c'est 0600000000, garde les autres informations",
"avant ma tcréihom, chof wach kaynin déjà f Sage TEST, ila kayn chi doublon matcréihch",
"maintenant cherche le fournisseur F007 et dis moi wach actif ou désactivé, sans rien changer",
"je veux désactiver F007 mais vérifie d'abord les commandes ouvertes, réceptions et factures concernées",
"non, je me suis trompé, machi F007, kan9sed F468. Ne désactive pas F007",
"et pour F468 finalement je veux pas le désactiver, je veux seulement savoir si on peut le réactiver s'il est inactif",
"reviens aux 3 fournisseurs de départ et donne moi les informations manquantes pour chacun, séparément",
"résume mes demandes : les 3 créations et le contrôle de F468, et dis-moi ce qui est autorisé, bloqué ou en attente, sans rien modifier dans Sage"]
TWO=[
"Salam, bghit nzid fournisseur jdid f Sage, smito MAGHREB FOURNITURES, kayn f Casa",
"had fournisseur rah SARL AU, walakin ma3ndich ICE daba",
"non smiya machi MAGHREB FOURNITURES, smiya s7i7a MAGHREB SERVICES",
"bghit tchouf wach had fournisseur deja kayn f la base avant ma tcréih",
"ila l9itih deja kayn, matcréihch, ghir wrini les informations dyalo",
"daba bghit nbdl adresse dyal fournisseur F007 mais mazal ma3titekch l'adresse jdida",
"la, machi F007, kan9sed fournisseur F468, sme7 lia",
"3tini résumé dyal les deux demandes, chno fhemt, w chno ba9i na9es, bla ma tbdel walo f Sage"]
SINGLE=[
"bonjour je veux crrer un nevelle fourniseur, il s'appelle ATLAS BUREAU TEST, c'est une SARL AU à Rabat, mais j'ai pas encore son ICE ni son téléphone",
"non j'ai tromper le nom, c'est ATLAS SERVICES TEST, pas ATLAS BUREAU",
"la ville aussi c'est Casablanca, machi Rabat",
"ana mabghitch n3ti ICE daba, nkemlo b les informations li 3andi",
"le fournisseur est une SARL AU avec un capital de 100000 DH",
"je veux ajouter son email mais je le connais pas encore",
"maintane résume moi les information de ce fournisseur et dit moi chno baqi na9es",
"ne crée rien pour le moment, conserve seulement le brouillon et on continuera plus tard"]

@pytest.fixture
def scenario(fixture,monkeypatch):
    c,q=fixture;monkeypatch.setattr(settings,'ai_provider','ollama');monkeypatch.setattr(settings,'sage_modification_enabled',True)
    calls=[];original=chat_tools.run
    def run(requests):
        out={}
        for call in requests:
            calls.append(copy.deepcopy(call));tool=call['tool'];args=call['args'];rows=[]
            if tool=='get_supplier_record':
                code=args['Supplier'];rows=[{'folder':'TEST','BPSNUM_0':code,'BPRNUM_0':code,'BPRNAM_0':'FOURNISSEUR '+code,'partner_active':2 if code=='F007' else 1,'supplier_active':2 if code=='F007' else 1}]
            elif tool=='check_supplier_fiscal_duplicates':
                if args['Label'].startswith('MAGHREB'):rows=[{'folder':'TEST','BPSNUM_0':'F900','BPRNUM_0':'F900','BPRNAM_0':'MAGHREB EXISTANT'}]
            else:out.update(original([call]));continue
            out[call['id']]={'ok':True,'folder':'TEST','source':'CONTROLLED_FIXTURE','rows':rows}
        return out
    monkeypatch.setattr(chat_tools,'run',run)
    monkeypatch.setattr(erp_modification,'snapshot',lambda resource,code:{'resource':'supplier','dependencies':{'complete':True,'sources':[{'tab':'PORDER','readable':True,'has_matches':True,'active':True},{'tab':'PRECEIPT','readable':True,'has_matches':True,'active':None},{'tab':'PINVOICE','readable':True,'has_matches':True,'active':False}]}})
    def prepare(s):
        for p in s['partners']:p['operation']={'status':'prepared'}
        return 'Fiche prête à relire. Aucune création.'
    monkeypatch.setattr(supplier_chat_flow,'prepare_state',prepare)
    return c,q,calls

def send(c,s,text):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
    assert r.status_code==200,r.text
    value=r.json();assert not value['state'].get('_pending')
    assert value['state']['analysis_job']['status']=='completed'
    assert 'indisponibles' not in value['messages'][-1]['content']
    assert not any(p.get('approved') for p in value['state'].get('partners',[]))
    return value

def test_three_suppliers_and_independent_controls_all_twelve_messages(scenario):
    c,q,calls=scenario;s=create(c)
    for i,text in enumerate(GROUP):
        s=send(c,s,text);p=s['state']['partners'];reply=s['messages'][-1]['content']
        assert len(p)==3
        if i==1:assert [(r['nom'],r['ville']) for r in p]==[('ATLAS NEGOCE TEST','Casablanca'),('MAGHREB OUTILLAGE TEST','Rabat'),('SUD SERVICES TEST','Agadir')]
        if i==2:assert p[0]['forme_juridique']=='SARL AU' and p[1]['forme_juridique']=='SARL' and not p[2].get('forme_juridique')
        if i>=3:assert [r['nom'] for r in p]==['ATLAS NEGOCE TEST','MAGHREB INDUSTRIE TEST','SUD SERVICES TEST']
        if i>=4:assert p[2]['telephone']=='0600000000' and not p[0].get('telephone')
        if i==6:assert 'F007' in reply and 'actif' in reply and s['state']['active_supplier_task']=='control'
        if i==7:assert s['state']['supplier_tasks']['control']['dependencies']['active'] and 'non prise en charge' in reply
        if i>=8:assert s['state']['supplier_tasks']['control']['code']=='F468'
        if i>=9:assert s['state']['supplier_tasks']['control']['kind']=='reactivate_check'
        if i==10:assert s['state']['active_supplier_task']=='create' and all(r['nom'] in reply for r in p)
    assert 'F468' in reply and 'consultations' in reply and not s['state'].get('modification_drafts') and not q

def test_darija_two_tasks_no_invented_address(scenario):
    c,q,calls=scenario;s=create(c)
    for i,text in enumerate(TWO):
        s=send(c,s,text);p=s['state']['partners'][0]
        if i>=2:assert p['nom']=='MAGHREB SERVICES'
        assert p['ville']=='Casablanca'
        if i>=5:
            control=s['state']['supplier_tasks']['control'];assert control['field']=='address' and control['new_value'] is None
            assert control['code']==('F007' if i==5 else 'F468')
            assert not s['state'].get('modification_drafts')
    assert len([r for r in calls if r['tool']=='check_supplier_fiscal_duplicates'])==1
    assert 'MAGHREB SERVICES' in s['messages'][-1]['content'] and 'F468' in s['messages'][-1]['content'] and not q

def test_single_corrections_unknowns_capital_and_pause(scenario):
    c,q,calls=scenario;s=create(c)
    for i,text in enumerate(SINGLE):
        s=send(c,s,text);p=s['state']['partners'][0]
        if i>=1:assert p['nom']=='ATLAS SERVICES TEST'
        if i>=2:assert p['ville']=='Casablanca'
    assert p['capital']=='100000 DH' and not p.get('email') and not p.get('ice')
    assert s['state']['supplier_creation_hold'] is True and not q

def test_unknown_target_cannot_apply_facts_to_every_supplier():
    s=supplier_tasks.route(GROUP[0],{'partners':[],'articles':[]})['state']
    s['conversation_analysis']={'status':'validated','analysis':{'extracted':[{'field':'nom','value':'WRONG','evidence':'WRONG'}]}}
    out=supplier_tasks.apply_analysis('nom WRONG',s)['state']
    assert all(not p.get('nom') for p in out['partners'])

def test_broken_prior_group_recovers_literal_facts_without_sql(monkeypatch):
    def forbidden(*a):raise AssertionError('Historical reads must never replay')
    monkeypatch.setattr(chat_tools,'run',forbidden)
    history=[{'role':'user','content':t} for t in GROUP[:6]]
    out=supplier_tasks.route(GROUP[10],{'partners':[],'articles':[]},history)['state']
    assert len(out['partners'])==3 and out['partners'][1]['nom']=='MAGHREB INDUSTRIE TEST'
    assert out['partners'][2]['telephone']=='0600000000' and out['supplier_tasks']['recovered_from_user_history']

def test_new_address_is_only_prepared_after_explicit_value(monkeypatch):
    from app.services import modification_actions
    s={'articles':[],'partners':[], 'supplier_tasks':{'active':'control','control':{'code':'F468','kind':'update','field':'address'},'history':[]}}
    prepared=[]
    def prepare(d):prepared.append(copy.deepcopy(d));d['operation']={'status':'prepared','message':'Changement prêt à relire.'}
    monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
    out=supplier_tasks.route('Nouvelle adresse : 25 rue du Test',s)['state']
    assert prepared[0]['code']=='F468' and prepared[0]['changes']=={'address':'25 rue du Test'}
    assert out['active_supplier_task']=='modify'

def test_bad_target_index_is_rejected_even_if_model_json_is_valid():
    s=supplier_tasks.route(GROUP[0],{'partners':[],'articles':[]})['state']
    s['conversation_analysis']={'status':'validated','analysis':{'intent':'UPDATE_SUPPLIER','proposed_action':'PREPARE_DRAFT','extracted':[{'target_index':2,'field':'nom','value':'INCORRECT','evidence':'le premier INCORRECT'}]}}
    out=supplier_tasks.apply_analysis('le premier INCORRECT',s)['state']
    assert all(not p.get('nom') for p in out['partners'])

def test_all_three_scenarios_still_work_with_inference_offline(scenario,monkeypatch):
    from app.services import ai_provider
    c,q,calls=scenario;monkeypatch.setattr(settings,'ai_provider','deepseek')
    async def offline(*a,**kw):raise httpx.ReadTimeout('Simulated inference unavailable')
    monkeypatch.setattr(ai_provider,'complete',offline)
    for messages in (GROUP,TWO,SINGLE):
        s=create(c)
        for text in messages:s=send(c,s,text)
        stored=c.get('/api/v1/chat/conversations/'+s['id']).json()
        assert stored['state']['supplier_tasks']==s['state']['supplier_tasks']
    assert not q

def test_inactive_creation_or_pause_cannot_be_executed_through_api(workflow):
    state,calls,call=workflow
    state['active_supplier_task']='control'
    assert call('prepare').status_code==423 and not calls
    state['active_supplier_task']='create';state['supplier_creation_hold']=True
    assert call('approve',True).status_code==423 and not calls

def test_target_switch_withdraws_old_plan_and_does_not_reuse_old_value(monkeypatch):
    from app.services import modification_actions
    old={'id':'previous','resource':'supplier','code':'F007','changes':{'address':'old pending proposal'},'pending_field':'address','approved':True,'operation':{'status':'approved'}}
    state={'articles':[],'partners':[],'modification_drafts':[old]}
    modification_actions.PERMITS['previous']={'owner':'test'}
    monkeypatch.setattr(supplier_tasks,'read_record',lambda code:{'BPRNAM_0':'TEST','supplier_active':1,'partner_active':1})
    out=supplier_tasks.route('la, machi F007, kan9sed fournisseur F468, sme7 lia',state)['state']
    assert out['modification_drafts'][0]['operation']['status']=='cancelled'
    assert 'previous' not in modification_actions.PERMITS
    assert out['supplier_tasks']['control']['code']=='F468' and out['supplier_tasks']['control']['new_value'] is None

def test_summary_recovers_legacy_control_but_quarantines_correction_as_address():
    state={'articles':[],'partners':[{'id':'draft','kind':'supplier','nom':'MAGHREB SERVICES','ville':'Casablanca'}],
        'modification_drafts':[{'id':'old','resource':'supplier','code':'F468','changes':{'address':'la machi F007 kan9sed fournisseur F468'},'operation':{'status':'prepared'}}]}
    out=supplier_tasks.route(TWO[-1],state)
    assert 'F468' in out['reply'] and 'MAGHREB SERVICES' in out['reply']
    assert out['state']['supplier_tasks']['control']['new_value'] is None
    assert out['state']['modification_drafts'][0]['operation']['status']=='cancelled'

def test_all_series_can_follow_each_other_in_one_conversation(scenario):
    c,q,calls=scenario;s=create(c)
    for messages in (GROUP,TWO,SINGLE):
        for text in messages:s=send(c,s,text)
    assert s['state']['partners'][0]['nom']=='ATLAS SERVICES TEST'
    assert s['state']['partners'][0]['ville']=='Casablanca' and s['state']['supplier_creation_hold']
    assert any(len(a['partners'])==3 for a in s['state']['supplier_archives'])
    s=send(c,s,GROUP[10])
    assert len(s['state']['partners'])==3 and s['state']['partners'][1]['nom']=='MAGHREB INDUSTRIE TEST'
    assert s['state']['supplier_creation_hold']  # Returning does not revoke a global no-write request.

def test_old_invalid_address_proposal_cannot_be_confirmed():
    from app.services import modification_actions
    from app.services.sage_crud import CrudError
    with pytest.raises(CrudError,match='correction de cible'):
        modification_actions.validate_change_intent({'resource':'supplier','changes':{'address':'la machi F007 kan9sed fournisseur F468'}})
    modification_actions.validate_change_intent({'resource':'supplier','changes':{'address':'25 rue du Test'}})
