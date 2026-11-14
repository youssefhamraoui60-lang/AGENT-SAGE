from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners,supplier_sql

MESSAGE="slt je veux ajouter un frs son nom c'est BERRCHID PIECES AUTO ice 006789012345678 il est a berrechid paiement par cheque 30j merci"

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_informal_request_is_prepared_without_model_clarification():
    p=parsed()
    assert p['nom']=='BERRCHID PIECES AUTO'
    assert p['ice']=='006789012345678'
    assert p['ville']=='berrechid'
    assert p['conditions_paiement']=='cheque 30 jours'
    params=supplier_sql.parameters(p,{'TypeLibelle':'HT','DateRegularite':'1753-01-01','__reference_labels':[{'kind':'Paiement','code':'CHQ30','label':'Chèque 30 Jours'}]})
    assert params['Paiement']=='CHQ30'
    assert not p.get('approved')

def test_oui_recovers_request_but_never_authorizes_creation():
    delta,grounding=extract('OUI',{},[{'role':'user','content':MESSAGE},{'role':'assistant','content':'Nouvelle fiche ?'}])
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='BERRCHID PIECES AUTO' and not p.get('approved')

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]}
    reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-informal-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
