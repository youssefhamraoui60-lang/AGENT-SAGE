from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners

MESSAGE="Bonjour, Merci de procéder à l'ajout d'un nouveau fournisseur dans notre système. Il s'agit de MAROC INDUSTRIE PLUS SARL, situé à Tanger, Zone Franche Gzenaya, lot 48. Le règlement se fera par effet à 60 jours. Son numéro ICE est 007123456789012, son IF est 48271935 et son RC 28451. Téléphone : 0661457892. Je souhaite que les montants soient en TTC et que la devise soit le dirham marocain. Merci de faire le nécessaire."

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_narrative_proposes_literal_fields_without_creation():
    p=parsed()
    expected={'nom':'MAROC INDUSTRIE PLUS SARL','ville':'Tanger','adresse':'Zone Franche Gzenaya, lot 48','conditions_paiement':'effet 60 jours','ice':'007123456789012','identifiant_fiscal':'48271935','rc':'28451','telephone':'0661457892','type_montant':'TTC','devise':'MAD'}
    assert {k:p.get(k) for k in expected}==expected
    assert not p.get('approved')

def test_user_can_correct_proposal_without_repeating_other_fields():
    state={'articles':[],'partners':[parsed()]}
    delta,grounding=extract('Ville : Casablanca',state)
    updated=chat_partners.merge(state,delta,grounding)['partners'][0]
    assert updated['ville']=='Casablanca'
    assert updated['ice']=='007123456789012' and updated['conditions_paiement']=='effet 60 jours'
    assert not updated.get('approved')

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]}
    reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-maroc-narrative.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reply':reply,'parameters':state['partners'][0].get('operation',{}).get('parameters')},ensure_ascii=False))
