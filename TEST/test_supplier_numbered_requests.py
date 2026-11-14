from test_supplier_independent_tasks import scenario,fixture,create,send
from test_supplier_after_creation import state as completed
from app.services import supplier_tasks,business_store as db
from app.services import supplier_chat_flow
REAL_PREPARE=supplier_chat_flow.prepare_state
from psycopg.types.json import Jsonb
import pytest

LIST='Bonjour, Merci de préparer les fiches des trois fournisseurs suivants : 1. ATLAS INDUSTRIE TEST — Casablanca — SARL AU 2. MAGHREB DISTRIBUTION TEST — Rabat — SARL 3. SUD EQUIPEMENT TEST — Agadir — SARL AU Nous ne disposons pas encore des ICE ni des registres de commerce. Merci de vérifier les éventuels doublons et de préparer les fiches pour validation. Cordialement,'

@pytest.mark.parametrize('previous',[False,True])
def test_numbered_list_from_empty_or_completed_conversation(scenario,previous):
    c,q,calls=scenario;s=create(c)
    if previous:
        with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(completed()),s['id']))
        s=c.get('/api/v1/chat/conversations/'+s['id']).json()
    s=send(c,s,LIST);p=s['state']['partners']
    assert [(x['nom'],x['ville'],x['forme_juridique']) for x in p]==[('ATLAS INDUSTRIE TEST','Casablanca','SARL AU'),('MAGHREB DISTRIBUTION TEST','Rabat','SARL'),('SUD EQUIPEMENT TEST','Agadir','SARL AU')]
    assert all(not x.get('ice') and not x.get('rc') for x in p)
    assert p[1]['duplicate_check']['matches'][0]['code']=='F900'
    assert p[1]['operation']['status']=='blocked'
    assert len([r for r in calls if r['tool']=='check_supplier_fiscal_duplicates'])==3
    assert not q
    if previous:assert s['state']['supplier_archives'][-1]['partners'][0]['operation']['status']=='succeeded'

def test_typo_invalid_ice_keeps_fields_without_inference(scenario,monkeypatch):
    monkeypatch.setattr(supplier_chat_flow,'prepare_state',REAL_PREPARE)
    c,q,_=scenario;s=send(c,create(c),'bonjour je veux céer un fourniseur khalide ben nassare leur ville est casa le ice est 87678937465267')
    p=s['state']['partners'][0]
    assert p['nom']=='khalide ben nassare' and p['ville']=='casa' and p['ice']=='87678937465267'
    assert p['operation']['status']=='blocked' and '14' in s['messages'][-1]['content']
    s=send(c,s,'OUI');assert s['state']['partners'][0]==p
    assert '15' in s['messages'][-1]['content'] and not q

def test_small_talk_and_bare_article_work_offline(scenario):
    c,q,_=scenario;s=send(c,create(c),'cv')
    assert 'Ça va' in s['messages'][-1]['content']
    s=send(c,s,'je veux créer un articles')
    assert s['state']['pending_creation']['resource']=='article'
    assert 'code' in s['messages'][-1]['content'] and 'désignation' in s['messages'][-1]['content']
    assert not q
