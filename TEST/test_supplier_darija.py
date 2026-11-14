from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners

MESSAGE='salam, 3afak zid lina fournisseur jdid smitou RIF ELECTRIC, ICE dyalou 007234567890123, kayn f Fes route Sefrou. bghit paiement b cheque 30 jours, telephone 0678912345. Les autres paramètres khalihom standard bhal les fournisseurs li 3andna. merci.'

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_darija_request_extracts_fields_without_clarification():
    p=parsed()
    expected={'nom':'RIF ELECTRIC','ice':'007234567890123','ville':'Fes','adresse':'route Sefrou','conditions_paiement':'cheque 30 jours','telephone':'0678912345'}
    assert {k:p.get(k) for k in expected}==expected
    assert not p.get('approved')

def test_typo_clarification_recovers_original_without_approval():
    delta,grounding=extract('un nevue xfourbnseur',{},[{'role':'user','content':MESSAGE}])
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='RIF ELECTRIC' and p['ice']=='007234567890123'
    assert not p.get('approved')

def test_multiword_city_is_not_truncated():
    delta,grounding=extract(MESSAGE.replace('Fes route Sefrou','El Jadida route Sefrou'),{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['ville']=='El Jadida' and p['adresse']=='route Sefrou'

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]};reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-darija-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reply':reply,'parameters':state['partners'][0].get('operation',{}).get('parameters')},ensure_ascii=False))
