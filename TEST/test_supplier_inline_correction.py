from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners

MESSAGE='Je veux créer le fournisseur OCEAN LOGISTIQUE. ICE : 007345678901234 IF : 52678941 RC : 36521 Ville : Rabat Attention, correction : la raison sociale exacte est OCEAN LOGISTICS SARL, pas OCEAN LOGISTIQUE. Le paiement est par virement à 30 jours et les montants sont HT. Merci de prendre uniquement les informations corrigées.'

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_explicit_name_correction_wins_and_other_values_survive():
    p=parsed()
    expected={'nom':'OCEAN LOGISTICS SARL','ice':'007345678901234','identifiant_fiscal':'52678941','rc':'36521','ville':'Rabat','conditions_paiement':'virement 30 jours','type_montant':'HT'}
    assert {k:p.get(k) for k in expected}==expected
    assert not p.get('approved')

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]};reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-inline-correction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reply':reply,'parameters':state['partners'][0].get('operation',{}).get('parameters')},ensure_ascii=False))
