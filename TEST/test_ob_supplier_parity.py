import copy,json,subprocess
import pytest
from test_modifications import simulated,fixture,draft,build,proof
from app.services import erp_modification as mod,conversation_tools as engine,chat_tools
from app.services.sage_crud import CrudError

def test_ob_plan_uses_only_ob_read_context_and_checks_update_rights(simulated):
    schema,_,view,_=simulated;schema['folder']=view['folder']='OB'
    d=draft('supplier',phone='0600000099');d['folder']='OB'
    plan=mod.build(d,schema,view)
    assert plan['folder']=='OB'
    for r in schema['permissions']:
        if r['table']=='BPADDRESS':r['can_update']=0
    with pytest.raises(CrudError):mod.build(d,schema,view)
    schema['folder']='TEST'
    with pytest.raises(CrudError):mod.build(d,schema,view)

def test_ob_transport_cannot_accept_a_test_plan_and_binds_connection(monkeypatch):
    captured=[]
    def process(args,**kw):
        captured.append((json.loads(kw['input']),kw['env']['SAGE_SUPPLIER_TARGET_FOLDER']))
        return subprocess.CompletedProcess(args,0,json.dumps({'ok':True,'folder':'OB'}),'')
    monkeypatch.setattr(mod.subprocess,'run',process)
    mod.transport('plan','supplier','F994',{'folder':'OB'},False,folder='OB')
    assert captured[0][0]['folder']==captured[0][1]=='OB' and captured[0][0]['execute'] is False
    with pytest.raises(CrudError):mod.transport('plan','supplier','F994',{'folder':'TEST'},True,folder='OB')
    assert len(captured)==1

def test_native_supplier_search_uses_ob_and_rejects_test_results(monkeypatch):
    calls=[]
    def run(batch):
        calls.extend(batch)
        return {batch[0]['id']:{'ok':True,'folder':'OB','rows':[{'BPSNUM_0':'F994','BPRNAM_0':'EXEMPLE'}]}}
    monkeypatch.setattr(chat_tools,'run',run)
    result=engine.read(engine.Read(resource='supplier',name='EXEMPLE'),{'supplier_target':'OB'},'cherche EXEMPLE')
    assert result['folder']=='OB' and all(c['args']['Folder']=='OB' for c in calls)
    monkeypatch.setattr(chat_tools,'run',lambda batch:{batch[0]['id']:{'ok':True,'folder':'TEST','rows':[]}})
    with pytest.raises(CrudError):engine.read(engine.Read(resource='supplier',name='EXEMPLE'),{'supplier_target':'OB'},'cherche EXEMPLE')

def test_ob_conversation_cannot_prepare_a_test_target():
    with pytest.raises(ValueError):engine.dispatch('prepare_draft',engine.Draft(resource='supplier',mode='new',fields=[engine.DraftValue(field='dossier_cible',value='TEST',evidence='TEST')]),{'supplier_target':'OB'},'TEST')

def test_ob_api_requires_confirmation_and_executes_only_the_ob_plan(fixture,simulated,monkeypatch):
    c,_=fixture;schema,_,view,_=simulated;calls=[]
    schema=copy.deepcopy(schema);schema['folder']='OB'
    view=copy.deepcopy(view);view['folder']='OB'
    monkeypatch.setattr(mod,'catalog',lambda folder='TEST':schema if folder=='OB' else pytest.fail('Wrong catalog folder'))
    monkeypatch.setattr(mod,'snapshot',lambda resource,code,folder='TEST':view if folder=='OB' else pytest.fail('Wrong snapshot folder'))
    def transport(action,resource='',code='',plan=None,execute=False,folder='TEST'):
        assert folder==plan['folder']=='OB';calls.append(execute)
        return {**proof(plan,execute),'folder':'OB'}
    monkeypatch.setattr(mod,'transport',transport)
    s=c.post('/api/v1/chat/conversations',json={'discussion_mode':'supplier_ob'}).json()
    path='/api/v1/chat/conversations/'+s['id']+'/modifications/'
    r=c.post(path+'drafts',json={'revision':s['revision'],'resource':'supplier','code':'F994','changes':{'phone':'0600000099'}})
    assert r.status_code==200,r.text
    s=r.json();d=s['state']['modification_drafts'][-1];assert d['folder']=='OB'
    url=path+d['id']+'/'
    assert c.post(url+'execute',json={'revision':s['revision'],'confirm':True}).status_code==403
    r=c.post(url+'approve',json={'revision':s['revision'],'confirm':True});assert r.status_code==200,r.text
    s=r.json();r=c.post(url+'execute',json={'revision':s['revision'],'confirm':True});assert r.status_code==200,r.text
    assert r.json()['state']['modification_drafts'][-1]['operation']['status']=='succeeded'
    assert calls==[False,True]
