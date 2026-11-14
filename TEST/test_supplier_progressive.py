import pytest
from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract
from app.services import chat_partners

def turn(state,text):
    delta,grounding=extract(text,state)
    return chat_partners.merge(state,delta,grounding)

@pytest.mark.parametrize('text',['je veux créer le forniseur ahmde mohamde','je veux créer le fournisseurs Ahmed Mohamed'])
def test_name_only_request_with_typo_prepares_a_draft(text):
    state=turn({'articles':[],'partners':[]},text)
    assert len(state['partners'])==1
    assert state['partners'][0]['nom']==('ahmde mohamde' if 'ahmde' in text else 'Ahmed Mohamed')
    assert not state['partners'][0].get('ice')

def test_progressive_updates_preserve_identity_fields_and_remove_approval():
    state=turn({'articles':[],'partners':[]},'je veux créer le fournisseurs Ahmed Mohamed')
    p=state['partners'][0];identifier=p['id']
    p['operation']={'status':'prepared'};p['approved']=True
    for text in ['ajouter le ICE 007567890123456','ajoute le téléphone 0612345678','modifie la ville Rabat','corrige le nom Ahmed Mohamed SARL']:
        state=turn(state,text)
    p=state['partners'][0]
    assert p['id']==identifier and len(state['partners'])==1
    assert p['nom']=='Ahmed Mohamed SARL' and p['ice']=='007567890123456'
    assert p['telephone']=='0612345678' and p['ville']=='Rabat'
    assert p['operation']['status']=='invalidated' and not p.get('approved')

def test_apostrophe_and_confirm_do_not_authorize_execution():
    state=turn({'articles':[],'partners':[]},'je veux créer le forniseur Ahmed Mohamed')
    state=turn(state,"ajouter l’ICE 007567890123456")
    state=turn(state,'oui')
    assert state['partners'][0]['ice']=='007567890123456'
    assert not state['partners'][0].get('approved')

def test_reformulated_initial_name_repairs_same_draft():
    state=turn({'articles':[],'partners':[]},'je veux créer le forniseur ahmde mohamde')
    identifier=state['partners'][0]['id']
    state=turn(state,'je veux créer le fournisseurs Ahmed Mohamed')
    state=turn(state,"ajouter l'ICE 007567890123456")
    assert len(state['partners'])==1 and state['partners'][0]['id']==identifier
    assert state['partners'][0]['nom']=='Ahmed Mohamed'
    assert state['partners'][0]['ice']=='007567890123456'

def test_exact_user_followups_with_typos_and_two_fields():
    state=turn({'articles':[],'partners':[]},'je veux créer le forniseur ahmde mohamde')
    identifier=state['partners'][0]['id']
    for text in ['avce le ice 123456789123456','ADRESS DOIS berrchide  et le ville dois KENTRA','POUR LE téle 09876543234']:
        state['partners'][0]['operation']={'status':'prepared'}
        state['partners'][0]['approved']=True
        state=turn(state,text)
        assert state['partners'][0]['operation']['status']=='invalidated'
        assert not state['partners'][0].get('approved')
    p=state['partners'][0]
    assert len(state['partners'])==1 and p['id']==identifier
    assert p['ice']=='123456789123456' and p['adresse']=='berrchide'
    assert p['ville']=='KENTRA' and p['telephone']=='09876543234'

def test_followup_preserves_address_comma_and_does_not_change_on_question():
    from app.services.supplier_language import extract_followup
    state=turn({'articles':[],'partners':[]},'je veux créer le fournisseur Ahmed Mohamed')
    state=turn(state,'adresse : 12, rue des Fleurs et la ville : Rabat')
    assert state['partners'][0]['adresse']=='12, rue des Fleurs'
    assert state['partners'][0]['ville']=='Rabat'
    assert extract_followup('pour le téléphone est-il correct ?') is None
