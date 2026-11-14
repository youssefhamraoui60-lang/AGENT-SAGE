"""CREATE supplier must not be stolen by UPDATE or lose supplied fields."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/tests'))
import pytest
from app.services import supplier_dialogue,modification_dialogue,supplier_multiturn
from test_conversation_chat import fixture,create
TEXT='je veux ajouter un fournisseur nommé MAROC FOURNITURE TEST, ville Casablanca, ICE 002033808000048, forme juridique SARL AU'

@pytest.mark.parametrize('prefix',['je veux ajouter un','ajoute un','ajouter un nouveau','je veux créer un','je veux crrer un nevelle'])
def test_creation_is_not_an_update(prefix,monkeypatch):
    monkeypatch.setattr(modification_dialogue.settings,'sage_modification_enabled',True)
    text=TEXT.replace('je veux ajouter un',prefix)
    assert modification_dialogue.turn(None,None,text,{'articles':[],'partners':[]}) is None
    result=supplier_dialogue.handle(text,{'articles':[],'partners':[]})
    p=result['state']['partners'][0]
    assert p['nom']=='MAROC FOURNITURE TEST' and p['ville']=='Casablanca'
    assert p['ice']=='002033808000048' and p['forme_juridique']=='SARL AU'
    assert result['prepare'] and not p['approved']

@pytest.mark.parametrize('text',['Ajoute le fournisseur F123 à l’article TESTART203','Ajoute un fournisseur pour article TESTART203','Modifie le fournisseur F123','Change le nom du fournisseur F123','Ajoute le téléphone au fournisseur F123'])
def test_existing_supplier_mutations_are_not_creation(text):
    assert not supplier_multiturn.explicit_supplier_creation(text)

@pytest.mark.parametrize('old_pending',[False,True])
def test_exact_chat_request_in_fastapi(fixture,monkeypatch,old_pending):
    from app.services import supplier_chat_flow,business_store as db
    from psycopg.types.json import Jsonb
    c,q=fixture;monkeypatch.setattr(modification_dialogue.settings,'sage_modification_enabled',True)
    monkeypatch.setattr(supplier_chat_flow,'prepare_state',lambda state:'Fiche prête à vérifier. Aucune création effectuée.')
    s=create(c)
    if old_pending:
        state=s['state'];state['modification_pending_target']={'resource':'supplier','message':TEXT}
        with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(state),s['id']))
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':TEXT,'revision':s['revision']})
    assert r.status_code==200,r.text
    out=r.json();p=out['state']['partners'][0]
    assert p['nom']=='MAROC FOURNITURE TEST' and p['ice']=='002033808000048'
    assert p['ville']=='Casablanca' and p['forme_juridique']=='SARL AU'
    assert not out['state'].get('modification_pending_target') and not out['state'].get('modification_drafts')
    assert 'code exact' not in out['messages'][-1]['content'] and not q
