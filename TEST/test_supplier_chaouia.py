from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners

MESSAGE='bjr stp crée moi un frs son nom AUTO SERVICE CHAOUIA ice 007456789012345 il habite a berrechid zone industriel lot 12 telephone 0612349876 et pour le paiment je veux effe 60j et ttc pas ht merci'

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_typos_and_explicit_ttc_preference():
    p=parsed()
    expected={'nom':'AUTO SERVICE CHAOUIA','ice':'007456789012345','ville':'berrechid','adresse':'zone industriel lot 12','telephone':'0612349876','conditions_paiement':'effet 60 jours','type_montant':'TTC'}
    assert {k:p.get(k) for k in expected}==expected
    assert not p.get('approved')

def test_oui_only_recovers_draft_not_write_permission():
    delta,grounding=extract('oui',{},[{'role':'user','content':MESSAGE}])
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='AUTO SERVICE CHAOUIA' and not p.get('approved')

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]};reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-chaouia-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reply':reply,'parameters':state['partners'][0].get('operation',{}).get('parameters')},ensure_ascii=False))
