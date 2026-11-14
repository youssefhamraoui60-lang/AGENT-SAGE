import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from app.services.supplier_chat_flow import extract,repair_embedded_fields
from app.services import chat_partners
from app.services.supplier_dates import normalize_date

@pytest.mark.parametrize('label',['Date de régularité fiscale','Date de régularité','Date régularité fiscale'])
def test_rc_and_fiscal_date_remain_separate_and_grounded(label):
    text='Créer un fournisseur AFRICA DISTRIBUTION SARL\nICE : 004567890123456\nIF : 45678912\nRC : 15342 '+label+' : 15/09/2026'
    delta,grounding=extract(text,{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['rc']=='15342' and p['date_regularite']=='2026-09-15'
    assert p['ice']=='004567890123456' and p['identifiant_fiscal']=='45678912'

def test_existing_polluted_rc_is_repaired_without_losing_other_fields():
    p={'nom':'AFRICA DISTRIBUTION SARL','ice':'004567890123456','rc':'15342 Date de régularité fiscale : 15/09/2026'}
    repair_embedded_fields(p)
    assert p['rc']=='15342' and p['date_regularite']=='2026-09-15'
    assert p['ice']=='004567890123456' and not p['approved']

def test_executed_supplier_is_never_repaired():
    p={'rc':'15342 Date de régularité fiscale : 15/09/2026','operation':{'status':'succeeded'}}
    repair_embedded_fields(p)
    assert p['rc'].startswith('15342 Date')

def test_date_response_updates_same_supplier():
    p={'id':'p','kind':'supplier','nom':'AFRICA DISTRIBUTION SARL','sources':{},'history':[]}
    text='Date de régularité fiscale : 15/09/2026'
    delta,grounding=extract(text,{'partners':[p]})
    after=chat_partners.merge({'partners':[p]},delta,grounding)['partners'][0]
    assert after['date_regularite']=='2026-09-15' and after['id']=='p'

def test_impossible_calendar_date_is_rejected():
    with pytest.raises(ValueError):normalize_date('31/02/2026')
