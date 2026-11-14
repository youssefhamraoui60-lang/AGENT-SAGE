import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from app.services.supplier_chat_flow import extract
from app.services import chat_partners

@pytest.mark.parametrize('message',[
 'Bonjour, veuillez procéder à la création du fournisseur CASA INDUSTRIE.\n\nICE : 001234567890123\n\nMerci.',
 'Bonjour, merci de créer un nouveau fournisseur nommé ATLAS FOURNITURES.',
])
def test_name_in_sentence_and_closing_politeness_do_not_need_model(message):
    delta,grounding=extract(message,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
    p=state['partners'][0]
    assert p['nom']==('CASA INDUSTRIE' if 'CASA' in message else 'ATLAS FOURNITURES')
    if 'CASA' in message:assert p['ice']=='001234567890123'

def test_labelled_name_with_thanks_preserves_fiscal_value():
    delta,_=extract('Créer un fournisseur\nNom : CASA INDUSTRIE\nICE : 001234567890123\nMerci.',{})
    assert delta.fournisseurs[0].ice=='001234567890123'

@pytest.mark.parametrize('message',[
 "Merci de créer le fournisseur MAGHREB SERVICES avec l'ICE 002345678901234 et le téléphone 0661234567.",
 'Merci de créer le fournisseur MAGHREB SERVICES avec l’ICE 002345678901234 et le téléphone 0661234567.',
 'Créer le fournisseur MAGHREB SERVICES, ICE : 002345678901234, téléphone : 0661234567.',
])
def test_prose_separates_name_ice_and_phone(message):
    delta,grounding=extract(message,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
    p=state['partners'][0]
    assert p['nom']=='MAGHREB SERVICES'
    assert p['ice']=='002345678901234' and p['telephone']=='0661234567'

def test_old_unexecuted_polluted_draft_can_be_repaired_without_reentry():
    from app.services.supplier_chat_flow import repair_embedded_fields
    p={'nom':"MAGHREB SERVICES avec l'ICE 002345678901234 et le téléphone 0661234567",'operation':{'status':'blocked'}}
    repair_embedded_fields(p)
    assert p['nom']=='MAGHREB SERVICES' and p['ice']=='002345678901234' and p['telephone']=='0661234567'
    assert p['operation']['status']=='invalidated' and not p['approved']
