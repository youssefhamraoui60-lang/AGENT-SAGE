"""Grounded UPDATE dialogue, mocked Sage reads, no SQL writes or live inference."""
import sys,copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
import pytest
from test_conversation_chat import fixture,create
from app.services import modification_dialogue as d,erp_modification as sql,chat_tools
from app.services.sage_crud import CrudError

@pytest.fixture
def reads(monkeypatch):
    monkeypatch.setattr(d.settings,'sage_modification_enabled',True)
    def no_inference(*a):raise AssertionError('Inference unnecessary for this dialogue')
    monkeypatch.setattr(d,'semantic_changes',no_inference)
    view=json.loads((ROOT/'TEST/fixtures/modification-schema.json').read_text(encoding='utf8'))['supplier']
    calls=[]
    def snapshot(resource,code):
        assert resource=='supplier' and code=='F10034'
        calls.append((resource,code));r=copy.deepcopy(view);r['resource']=resource;r['partners'][0]['BPRNAM_0']='votre confirmation';return r
    monkeypatch.setattr(sql,'snapshot',snapshot)
    def light(calls_in):
        code=calls_in[0]['args']['Supplier'];snap=snapshot('supplier',code)
        return {'modification_identity':{'ok':True,'folder':'TEST','rows':[{**snap['partners'][0],**snap['suppliers'][0],'folder':'TEST','BPSNUM_0':code,'BPRNUM_0':code}]}}
    monkeypatch.setattr(chat_tools,'run',light)
    return calls

@pytest.mark.parametrize('code',['F10034',' F10034 ','\u00a0F10034\u00a0','F10034&#x20;','**F10034**','le code est F10034'])
def test_exact_conversation_keeps_target_and_read_request_is_not_a_name(reads,code):
    state={'articles':[],'partners':[]}
    for text in ['je veux modifer mon founiseur',code,'le nom','donner le nome actiale']:
        result=d.turn(None,None,text,state);assert result is not None,text;state=result['state']
    target=state['modification_drafts'][-1]
    assert target['code']=='F10034' and target['pending_field']=='name'
    assert target['changes']=={} and not state['partners']
    assert 'votre confirmation' in result['reply'] and 'nom actuel' in result['reply']
    assert len(reads)>=2

def test_old_unanswered_code_slot_recovers_only_its_own_user_history(reads):
    state=d.turn(None,None,'je veux modifer mon founiseur',{'articles':[],'partners':[]})['state']
    rows=[{'role':'user','content':t} for t in ['F999','je veux modifer mon founiseur',' F10034 ','le nom']]
    out=d.turn(None,None,'donner le nome actiale',state,rows)
    assert out['state']['modification_drafts'][-1]['code']=='F10034'
    assert not out['state']['modification_drafts'][-1]['changes']
    assert 'votre confirmation' in out['reply']

def test_user_can_supply_new_name_after_reading_current_name(reads,monkeypatch):
    def prepare(draft):draft['operation']={'status':'prepared'};draft['approved']=False
    monkeypatch.setattr(d.actions,'prepare_draft',prepare)
    state={'articles':[],'partners':[]}
    for text in ['je veux modifer mon founiseur','F10034 ','le nom','donner le nome actiale','ATLAS BUREAU TEST']:
        state=d.turn(None,None,text,state)['state']
    target=state['modification_drafts'][-1]
    assert target['changes']=={'name':'ATLAS BUREAU TEST'}
    assert target['current']['name']=='votre confirmation' and not target['approved']

def test_read_failure_keeps_code_and_never_fabricates_name(reads,monkeypatch):
    state=d.turn(None,None,'je veux modifer mon founiseur',{'articles':[],'partners':[]})['state']
    def fail(*a):raise CrudError('Lecture momentanément indisponible.',423)
    monkeypatch.setattr(chat_tools,'run',fail)
    out=d.turn(None,None,'F10034 ',state);target=out['state']['modification_drafts'][-1]
    assert target['code']=='F10034' and not target['changes']
    assert 'indisponible' in out['reply'] and 'votre confirmation' not in out['reply']

@pytest.mark.parametrize('bad',['wrong_folder','wrong_code','missing'])
def test_light_lookup_never_uses_wrong_record_or_folder(reads,monkeypatch,bad):
    def wrong(calls):
        assert calls[0]['args']=={'Folder':'TEST','Supplier':'F10034'}
        row={'folder':'OB' if bad=='wrong_folder' else 'TEST','BPSNUM_0':'F999' if bad=='wrong_code' else 'F10034','BPRNUM_0':'F10034','BPRNAM_0':'NEVER USE'}
        return {'modification_identity':{'ok':True,'folder':'TEST','rows':[] if bad=='missing' else [row]}}
    monkeypatch.setattr(chat_tools,'run',wrong)
    with pytest.raises(CrudError):d.read_current_record('supplier','F10034')

def test_end_to_end_pg_remembers_target_and_pending_field(fixture,reads):
    c,q=fixture;s=create(c)
    for text in ['je veux modifer mon founiseur','F10034 ','le nom','donner le nome actiale']:
        r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
        assert r.status_code==200,r.text;s=r.json()
    saved=c.get('/api/v1/chat/conversations/'+s['id']).json()
    target=saved['state']['modification_drafts'][-1]
    assert target['code']=='F10034' and target['changes']=={} and target['pending_field']=='name'
    assert 'nom actuel' in saved['messages'][-1]['content'] and not q
