import pytest
from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners,supplier_sql

MESSAGE='Bonjour, je souhaite créer un nouveau fournisseur. Nom : TELFIX TEST ICE : 001850814901094 IF : 20734924 RC : 10903 Paiement : Effet 60 jours Type montant : TTC Merci de préparer sa création.'

def parsed(message=MESSAGE):
    delta,grounding=extract(message,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

@pytest.mark.parametrize('closing',['Merci de préparer sa création.','Merci de préparer cette fiche.','Merci de préparer la création pour validation.'])
def test_closing_request_is_not_part_of_ttc(closing):
    p=parsed(MESSAGE.replace('Merci de préparer sa création.',closing))
    assert p['nom']=='TELFIX TEST'
    assert p['ice']=='001850814901094' and p['identifiant_fiscal']=='20734924' and p['rc']=='10903'
    assert p['conditions_paiement']=='Effet 60 jours' and p['type_montant']=='TTC'
    assert not p.get('approved')

def test_closing_is_not_stripped_if_it_contains_additional_data():
    p=parsed(MESSAGE+' Téléphone : 0661234567')
    assert p['telephone']=='0661234567' and p['type_montant']=='TTC'

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]}
    reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-telfix-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':state['partners'][0].get('operation',{}).get('status'),'reply':reply},ensure_ascii=False))
