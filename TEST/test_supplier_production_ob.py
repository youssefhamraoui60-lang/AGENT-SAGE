"""Production routing checks with simulated SQL; no real OB INSERT."""
from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from app.services import supplier_sql as sql,conversation_chat as chat,supplier_chat_flow
import pytest,json,subprocess
from test_chat_supplier_sql import workflow,result


@pytest.mark.parametrize('mode',['general','supplier_ob'])
def test_fiscal_fact_in_noisy_sentence_is_retained_and_validated(setup,monkeypatch,mode):
    from app.services import conversation_tools
    c,old,owner=setup
    async def fallback(owner,identifier,text,state,history):return {'state':state,'fallback':True}
    monkeypatch.setattr(conversation_tools,'turn',fallback)
    monkeypatch.setattr(chat.settings,'conversation_tool_calling_enabled',True)
    monkeypatch.setattr(chat.settings,'ai_provider','deepseek')
    monkeypatch.setattr(chat,'supplier_security',lambda **kw:{'ready':True,'folder':kw.get('folder','TEST')})
    monkeypatch.setattr(sql,'prepare_operation',lambda p:{**fake_prepare(p),'folder':p.get('dossier_cible','TEST')})
    monkeypatch.setattr(sql,'run',lambda *a,**kw:pytest.fail('No Sage execution'))
    response=c.post('/api/v1/chat/conversations',json={'discussion_mode':mode})
    s=send(c,response.json(),'bonjour je veux créer un fournisseur rachide H')
    identifier=s['state']['partners'][0]['id']
    s=send(c,s,'CETTE FOURNIISEUR AVCE LE ICE 12343234565456')
    assert len(s['state']['partners'])==1
    p=s['state']['partners'][0]
    assert p['id']==identifier and p['nom']=='rachide H'
    assert p['ice']=='12343234565456' and not p.get('approved')
    assert p['operation']['status']=='blocked'
    assert '14 chiffres' in s['messages'][-1]['content'] and '15' in s['messages'][-1]['content']
    s=send(c,s,'012343234565456')
    p=s['state']['partners'][0]
    assert p['id']==identifier and p['ice']=='012343234565456'
    assert p['operation']['status']=='prepared' and not p.get('approved')


def test_embedded_fiscal_fact_does_not_change_a_different_supplier():
    from app.services.supplier_followups import turn
    state={'partners':[{'id':'one','kind':'supplier','nom':'rachide H'}]}
    assert turn('pour le fournisseur AUTRE avec ICE 12343234565456',state) is None
    assert not state['partners'][0].get('ice')


@pytest.mark.parametrize('mode',['general','supplier_ob'])
def test_rachide_address_typo_keeps_same_draft_and_literal_value(setup,monkeypatch,mode):
    from app.services import conversation_tools
    c,old,owner=setup
    async def fallback(owner,identifier,text,state,history):return {'state':state,'fallback':True}
    monkeypatch.setattr(conversation_tools,'turn',fallback)
    monkeypatch.setattr(chat.settings,'conversation_tool_calling_enabled',True)
    monkeypatch.setattr(chat.settings,'ai_provider','deepseek')
    monkeypatch.setattr(chat,'supplier_security',lambda **kw:{'ready':True,'folder':kw.get('folder','TEST')})
    folders=[]
    def prepare(p):
        folders.append(p.get('dossier_cible','TEST'))
        return {**fake_prepare(p),'folder':p.get('dossier_cible','TEST')}
    monkeypatch.setattr(sql,'prepare_operation',prepare)
    monkeypatch.setattr(sql,'run',lambda *a,**kw:pytest.fail('No Sage execution'))
    response=c.post('/api/v1/chat/conversations',json={'discussion_mode':mode})
    s=send(c,response.json(),'créer le founisseur rachide IT')
    identifier=s['state']['partners'][0]['id']
    s=send(c,s,'le addrise est HAY RAH BERRCHIDE R56')
    assert len(s['state']['partners'])==1 and not s['state'].get('articles')
    p=s['state']['partners'][0]
    assert p['id']==identifier and p['nom']=='rachide IT'
    assert p.get('adresse')=='HAY RAH BERRCHIDE R56' and not p.get('ville'),(s['state'].get('active_supplier_task'),s['state'].get('supplier_tasks'),s['messages'][-1]['content'])
    assert not p.get('approved') and p['operation']['status']=='prepared'
    assert folders==['OB' if mode=='supplier_ob' else 'TEST']*2
    snapshot=s['messages'][-1]['payload']['supplier_snapshots'][0]
    assert any('HAY RAH BERRCHIDE R56'==row.get('value') for row in snapshot['rows'])


@pytest.mark.parametrize('mode',['general','supplier_ob'])
def test_exact_ahmad_supplier_two_turns_during_provider_outage(setup,monkeypatch,mode):
    from app.services import conversation_tools
    c,old,owner=setup
    async def fallback(owner,identifier,text,state,history):return {'state':state,'fallback':True}
    monkeypatch.setattr(conversation_tools,'turn',fallback)
    monkeypatch.setattr(chat.settings,'conversation_tool_calling_enabled',True)
    monkeypatch.setattr(chat.settings,'ai_provider','deepseek')
    monkeypatch.setattr(chat,'supplier_security',lambda **kw:{'ready':True,'folder':kw.get('folder','TEST')})
    folders=[]
    def prepare(p):
        folder=p.get('dossier_cible','TEST');folders.append(folder)
        return {**fake_prepare(p),'folder':folder}
    monkeypatch.setattr(sql,'prepare_operation',prepare)
    monkeypatch.setattr(sql,'run',lambda *a,**kw:pytest.fail('No Sage write'))
    async def forbidden(*a,**kw):pytest.fail('No supplier model extraction required')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    response=c.post('/api/v1/chat/conversations',json={'discussion_mode':mode})
    assert response.status_code in (200,201)
    s=send(c,response.json(),'je veux créer un founnisseur')
    assert 'nom' in s['messages'][-1]['content'].lower()
    s=send(c,s,'le nom de mon fournisseur est AHMAD IT')
    assert len(s['state']['partners'])==1 and not s['state'].get('articles')
    p=s['state']['partners'][0]
    assert p['nom']=='AHMAD IT' and not p.get('approved')
    assert folders==['OB' if mode=='supplier_ob' else 'TEST']
    assert p['operation']['status']=='prepared'


def test_formal_supplier_email_ob_survives_provider_fallback(setup,monkeypatch):
    c,old,owner=setup
    monkeypatch.setattr(chat,'supplier_security',lambda **kw:{'ready':True,'folder':kw.get('folder','TEST')})
    from app.services import conversation_tools
    async def fallback(owner,identifier,text,state,history):
        return {'state':state,'fallback':True}
    monkeypatch.setattr(conversation_tools,'turn',fallback)
    monkeypatch.setattr(chat.settings,'conversation_tool_calling_enabled',True)
    monkeypatch.setattr(chat.settings,'ai_provider','deepseek')
    calls=[]
    def prepare(p):
        calls.append(p.get('dossier_cible'))
        return {**fake_prepare(p),'folder':p.get('dossier_cible')}
    monkeypatch.setattr(sql,'prepare_operation',prepare)
    monkeypatch.setattr(sql,'run',lambda *a,**kw:pytest.fail('No Sage execution'))
    async def forbidden(*a,**kw):pytest.fail('Explicit supplier email needs no model extraction')
    monkeypatch.setattr(chat.model,'extract',forbidden)
    response=c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier_ob'})
    assert response.status_code in (200,201),response.text
    s=send(c,response.json(),'Bonjour, Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système : Nom de frs : TRACTAFRIC EQUIPMENT MAROC Ice : 001524532000071 Je reste à votre disposition pour toute information complémentaire. Cordialement.')
    assert calls==['OB']
    p=s['state']['partners'][0]
    assert p['nom']=='TRACTAFRIC EQUIPMENT MAROC' and p['ice']=='001524532000071'
    assert p['dossier_cible']=='OB' and p['operation']['folder']=='OB'
    assert p['operation']['status']=='prepared' and not p['approved']
    assert 'Le service IA ne permet pas' not in s['messages'][-1]['content']

def test_ob_requires_fresh_confirmation_then_routes_execute_once(workflow,monkeypatch):
    state,calls,call=workflow
    state['supplier_target']='OB';state['partners'][0]['dossier_cible']='OB'
    def run(values,execute=False,folder='TEST'):
        assert folder=='OB';calls.append(execute)
        return {**result(values),'folder':'OB'} if execute else {'ok':True,'folder':'OB','rows':[{'RESULTAT':'VALIDATED_NO_INSERT','CODE_PROPOSE_NON_RESERVE':'F104'}]}
    monkeypatch.setattr(sql,'run',run)
    assert call('prepare').status_code==200
    assert call('execute',True).status_code==403 and calls==[False]
    assert call('approve',True).status_code==200
    response=call('execute',True)
    assert response.status_code==200,response.text
    op=response.json()['state']['partners'][0]['operation']
    assert op['folder']=='OB' and op['status']=='succeeded'
    assert op['result']['supplier_verification']['folder']=='OB'
    assert call('execute',True).status_code==409 and calls==[False,True]

def test_new_ob_conversation_prepares_only_ob_and_test_stays_test(setup,monkeypatch):
    c,old,owner=setup
    monkeypatch.setattr(chat,'supplier_security',lambda **kw:{'ready':True,'folder':kw.get('folder','TEST')})
    calls=[]
    def prepare(p):
        calls.append(p.get('dossier_cible','TEST'))
        return {**fake_prepare(p),'folder':p.get('dossier_cible','TEST')}
    monkeypatch.setattr(sql,'prepare_operation',prepare)
    response=c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier_ob'})
    assert response.status_code in (200,201),response.text
    s=response.json();assert s['folder']=='OB' and s['state']['supplier_target']=='OB'
    s=send(c,s,'le nom du fournisseur est ROUTAGE OB')
    p=s['state']['partners'][0]
    assert p['dossier_cible']=='OB' and p['operation']['folder']=='OB' and not p['approved']
    send(c,old,'Créer un fournisseur Nom : ROUTAGE TEST')
    assert calls==['OB','TEST']

def test_worker_target_and_connection_are_bound_to_ob(monkeypatch):
    captured=[]
    def process(args,**kw):
        body=json.loads(kw['input']);captured.append((body,kw['env']))
        return subprocess.CompletedProcess(args,0,json.dumps({'ok':True,'folder':'OB','rows':[]}), '')
    monkeypatch.setattr(sql.subprocess,'run',process)
    sql.run({'Nom':'SIMULATION'},execute=False,folder='OB')
    assert captured[0][0]['folder']=='OB' and captured[0][0]['execute'] is False
    assert captured[0][1]['SAGE_SUPPLIER_TARGET_FOLDER']=='OB'
    assert sql.query_digest('OB')!=sql.query_digest('TEST')
    with pytest.raises(Exception):sql.run({},folder='OTHER')

def test_production_readback_cannot_accept_test_result():
    assert sql.verify({}, {'ok':True,'folder':'TEST','executed':True,'rows':[{}]},folder='OB') is None

def test_production_tls_exception_requires_explicit_configuration():
    from pathlib import Path
    script=(Path(__file__).parent/'SupplierSqlConnection.ps1').read_text(encoding='utf-8-sig')
    assert "$target -ceq 'OB' -and $env:SAGE_SUPPLIER_OB_TRUST_SERVER_CERTIFICATE -ceq 'true'" in script
    assert "$target -cnotin @('TEST','OB')" in script
