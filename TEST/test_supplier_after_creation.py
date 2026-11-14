"""After a verified creation, propose UPDATEs and keep the creation immutable."""
from test_supplier_independent_tasks import fixture,scenario,send,create
from app.services import supplier_tasks,modification_dialogue as d,business_store as db
from psycopg.types.json import Jsonb
from uuid import uuid4
import copy,pytest

def state():
    return {'articles':[],'partners':[{'id':str(uuid4()),'kind':'supplier','nom':'CASA TECH TEST','ville':'Casablanca','forme_juridique':'SARL AU','operation':{'status':'succeeded','record_keys':{'BPSNUM':'F10037'},'result':{'supplier_verification':{'code':'F10037'}}}}], 'supplier_tasks':{'version':1,'active':'create','group':{'expected_count':1},'history':[],'control':None},'active_supplier_task':'create'}

MESSAGES=['je veux modifier le vile a berrchide','je veux modifier le la vile de cette founiseur F10037','je veux modifier la ville de la fournisseur F10037','pour quoi tu pas comprer mon message','bonjour','tu rester a envyer cette messege']

def test_exact_followup_through_postgres_and_chat(scenario,monkeypatch):
    c,q,_=scenario;s=create(c);initial=state();prepared=[]
    def prepare(draft):
        assert draft['resource']=='supplier' and draft['code']=='F10037'
        prepared.append(copy.deepcopy(draft['changes']));draft['current']={'city':'Casablanca'}
        draft['operation']={'status':'prepared','plan':{'diff':[{'field':'city','before':'Casablanca','after':'berrchide'}]}}
    monkeypatch.setattr(d.actions,'prepare_draft',prepare)
    with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(initial),s['id']))
    s=c.get('/api/v1/chat/conversations/'+s['id']).json()
    for i,text in enumerate(MESSAGES):
        s=send(c,s,text);st=s['state'];reply=s['messages'][-1]['content']
        assert st['partners']==initial['partners']
        assert st['active_supplier_task']=='modify'
        target=st['modification_drafts'][-1]
        assert target['resource']=='supplier' and target['code']=='F10037'
        assert target['changes']=={'city':'berrchide'} and target['operation']['status']=='prepared'
        assert 'Précisez uniquement le champ et la valeur à corriger' not in reply
        if i==4:assert reply.startswith('Bonjour')
        if i in (3,5):assert 'F10037' in reply and 'berrchide' in reply and 'confirmation' in reply
    assert prepared==[{'city':'berrchide'}] and not q

@pytest.mark.parametrize('text',['bonjour','pour quoi tu pas comprer mon message','tu rester a envyer cette messege'])
def test_task_controller_does_not_swallow_unrelated_turns(text):
    assert supplier_tasks.route(text,state()) is None
    assert supplier_tasks.apply_analysis(text,state()) is None

def test_completed_creation_not_rewritten_by_semantic_facts():
    s=state();s['conversation_analysis']={'status':'validated','analysis':{'intent':'UPDATE_SUPPLIER','proposed_action':'PREPARE_DRAFT','extracted':[{'field':'ville','value':'berrchide','evidence':'berrchide','target_index':1}]}}
    assert supplier_tasks.apply_analysis('corrige la ville a berrchide',s) is None
    assert s['partners'][0]['ville']=='Casablanca'
