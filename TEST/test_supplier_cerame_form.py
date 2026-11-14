import pytest
from app.services import supplier_chat_flow,chat_partners

MESSAGE='Bonjour \u00a0youssef,merci de créer le fournisseur suivant\u00a0:'+'\u00a0'*160+'Super Cerame/ICE\u00a0:000000505000042/IF\u00a0:01067182/AIN SEBAA 20252-CASABLANCA-MAROC'
FOLLOWUP='Cerame/ICE :000000505000042/IF :01067182/AIN SEBAA 20252-CASABLANCA-MAROC'

@pytest.mark.parametrize('text',[MESSAGE,MESSAGE.replace('\u00a0',' '),MESSAGE.replace('\u00a0','\u202f')])
def test_inscribed_spaces_and_single_slashes_preserve_supplier_data(text):
    delta,ground=supplier_chat_flow.extract(text,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,ground)
    p=state['partners'][0]
    assert p['nom']=='Super Cerame' and p['ice']=='000000505000042'
    assert p['identifiant_fiscal']=='01067182'
    assert p['adresse']=='AIN SEBAA 20252-CASABLANCA-MAROC'
    assert not state.get('turn_clarifications') and not p.get('approved')

def test_headerless_retry_recovers_creation_context_and_preserves_new_name():
    parsed=supplier_chat_flow.extract(FOLLOWUP,{'articles':[],'partners':[]},[{'role':'user','content':MESSAGE}])
    assert parsed and parsed[0].fournisseurs[0].nom=='Cerame'
    assert not supplier_chat_flow.extract(FOLLOWUP,{'articles':[],'partners':[]})

def test_headerless_followup_updates_same_draft():
    delta,ground=supplier_chat_flow.extract(MESSAGE,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,ground);identifier=state['partners'][0]['id']
    delta,ground=supplier_chat_flow.extract(FOLLOWUP,state)
    state=chat_partners.merge(state,delta,ground)
    assert len(state['partners'])==1 and state['partners'][0]['id']==identifier
    assert state['partners'][0]['nom']=='Cerame'
