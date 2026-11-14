import pytest
from app.services.supplier_chat_flow import extract
from app.services import chat_partners

MESSAGE='Bonjour,    Frs :SOS MECANIQUE HYDRAULIQUE    ICE :001538584000034.    IF :1921340.    ADRESSE :bd khalid bnou al oulid halioua, rue anouar 6 mag n°10 casablanca   Cordialement .'
ADDRESS='bd khalid bnou al oulid halioua, rue anouar 6 mag n°10 casablanca'

@pytest.mark.parametrize('message',[MESSAGE,MESSAGE.replace('    ','\n'),MESSAGE.replace('Frs :','Fournisseur :')])
def test_pasted_supplier_form_prepares_without_intent_question(message):
    delta,ground=extract(message,{'articles':[],'partners':[]})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,ground)
    assert len(state['partners'])==1 and not state.get('turn_clarifications')
    p=state['partners'][0]
    assert p['nom']=='SOS MECANIQUE HYDRAULIQUE'
    assert p['ice']=='001538584000034' and p['identifiant_fiscal']=='1921340'
    assert p['adresse']==ADDRESS and not p.get('approved')
    assert not p.get('ville')  # Never invent a separate city from an unlabelled address.

def test_lookup_is_not_rewritten_as_creation():
    parsed=extract('Rechercher Frs : SOS MECANIQUE HYDRAULIQUE',{'articles':[],'partners':[]})
    assert not parsed or parsed[0].intent!='new'
