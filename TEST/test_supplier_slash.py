from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners,supplier_sql

MESSAGE='NOUVEAU FRS / ville : Rabat / type montant : HT / nom : MARRAKECH HYDRAULIQUE 0002 / ICE : 900000000000002 / téléphone : 0610015838 / TEST / confirmer avant création'

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_slash_fields_in_any_order_and_no_execution():
    p=parsed()
    assert p['nom']=='MARRAKECH HYDRAULIQUE 0002'
    assert p['ice']=='900000000000002' and p['telephone']=='0610015838'
    assert p['ville']=='Rabat' and p['type_montant']=='HT'
    assert not p.get('approved')

def test_payment_connector_uses_actual_reference_not_invented_code():
    p=parsed();p['conditions_paiement']='virement à 30 jours'
    defaults={'TypeLibelle':'HT','DateRegularite':'1753-01-01','__reference_labels':[{'kind':'Paiement','code':'VIR30','label':'Virement 30 Jours'}]}
    assert supplier_sql.parameters(p,defaults)['Paiement']=='VIR30'
    defaults['__reference_labels']=[]
    import pytest
    from app.services.sage_crud import CrudError
    with pytest.raises(CrudError):supplier_sql.parameters(p,defaults)

if __name__=='__main__':
    import json
    from pathlib import Path
    state={'partners':[parsed()]};reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-slash-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reply':reply,'parameters':state['partners'][0].get('operation',{}).get('parameters')},ensure_ascii=False))
