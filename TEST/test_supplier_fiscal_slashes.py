import pytest
from app.services import supplier_chat_flow as flow,chat_partners,supplier_sql
from app.services.sage_crud import CrudError

MESSAGE='UGRENT Bonjour, Merci de créer ce nouveau fournisseur : mohamed arrar ICE / 00295940100040 / IF : 50647721 / bouskoura victoria oulad saleh bloc 24'

def parsed(text=MESSAGE):
    delta,ground=flow.extract(text,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,ground)

def test_fiscal_values_and_address_are_independent():
    p=parsed()['partners'][0]
    assert p['nom']=='mohamed arrar' and p['ice']=='00295940100040'
    assert p['identifiant_fiscal']=='50647721'
    assert p['adresse']=='bouskoura victoria oulad saleh bloc 24' and not p.get('ville')

def test_invalid_ice_is_visible_and_blocks_before_sql(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('No SQL or defaults read for invalid ICE')
    monkeypatch.setattr(supplier_sql,'run',forbidden);monkeypatch.setattr(supplier_sql,'load_defaults',forbidden)
    state=parsed();reply=flow.prepare_state(state);p=state['partners'][0]
    assert '14 chiffres' in reply and '15' in reply
    assert p['operation']['status']=='blocked' and not p['approved']
    with pytest.raises(CrudError,match='ICE invalide'):supplier_sql.prepare_operation(p)
    with pytest.raises(CrudError,match='ICE invalide'):supplier_sql.parameters(p)

def test_corrected_ice_keeps_the_other_values():
    state=parsed();flow.prepare_state(state);identifier=state['partners'][0]['id']
    delta,ground=flow.extract('corrige ICE : 002959401000401',state)
    corrected=chat_partners.merge(state,delta,ground)['partners'][0]
    assert corrected['id']==identifier and corrected['ice']=='002959401000401'
    assert corrected['identifiant_fiscal']=='50647721' and corrected['adresse']=='bouskoura victoria oulad saleh bloc 24'
