import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.supplier_chat_flow import extract,repair_embedded_fields,strip_missing_fiscal_note
from app.services import chat_partners,supplier_sql

MESSAGE="Bonjour, merci de créer un nouveau fournisseur : Nom : SUD TRANSPORT Ville : Marrakech Condition de paiement : Virement comptant Je n'ai pas encore son ICE, son IF ni son RC."

def parsed():
    delta,grounding=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]

def test_absence_statement_is_not_payment_and_fiscal_fields_stay_empty():
    p=parsed()
    assert p['nom']=='SUD TRANSPORT' and p['ville']=='Marrakech'
    assert p['conditions_paiement']=='Virement comptant'
    values=supplier_sql.parameters(p,{'DateRegularite':'1753-01-01','TypeLibelle':'HT','__reference_labels':[{'kind':'Paiement','label':'Virement Comptant','code':'VIR00'}]})
    assert values['Paiement']=='VIR00'
    assert all(values[k]=='' for k in ('ICE','IF','RC'))

def test_existing_unexecuted_payment_is_repaired_without_authorization():
    p={'conditions_paiement':"Virement comptant Je n'ai pas encore son ICE, son IF ni son RC.",'operation':{'status':'blocked'},'approved':True}
    repair_embedded_fields(p)
    assert p['conditions_paiement']=='Virement comptant'
    assert p['operation']['status']=='invalidated' and not p['approved']

def test_executed_records_and_actual_following_data_are_preserved():
    p={'conditions_paiement':"Virement comptant Je n'ai pas encore son ICE.",'operation':{'status':'executed'}}
    before=dict(p)
    repair_embedded_fields(p)
    assert p==before
    text="Virement comptant Je n'ai pas son ICE. Téléphone : 0661234567"
    assert strip_missing_fiscal_note(text)==text

if __name__=='__main__':
    import json
    from app.services.supplier_chat_flow import prepare_state
    state={'partners':[parsed()]}
    reply=prepare_state(state)
    report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
    Path(__file__).with_name('verification-sud-transport-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    op=state['partners'][0].get('operation',{})
    print(json.dumps({'status':op.get('status'),'parameters':op.get('parameters'),'reply':reply},ensure_ascii=False))
