import pytest
from app.services import supplier_chat_flow,chat_partners,supplier_sql,supplier_snapshots
from app.services.sage_crud import CrudError

MESSAGE='Bonjour , Youssef merci de créer le fournisseur suivant AL ALAMIA//IF :N°60106228//ICE :003388875000087//EMAIL:auto.alalamia@gmail.com//'

@pytest.mark.parametrize('text',[MESSAGE,MESSAGE.replace('N°','Nº'),MESSAGE.replace('fournisseur suivant','fournisseur :')])
def test_all_fields_retained_and_number_prefix_removed(text):
    delta,ground=supplier_chat_flow.extract(text,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,ground);p=state['partners'][0]
    assert p['nom']=='AL ALAMIA' and p['identifiant_fiscal']=='60106228'
    assert p['ice']=='003388875000087' and p['email']=='auto.alalamia@gmail.com'
    assert not state.get('turn_clarifications')
    rows={r['key']:r['value'] for r in supplier_snapshots.capture(state)[0]['rows']}
    assert rows['Email']=='auto.alalamia@gmail.com'

def test_email_unsupported_write_is_explicit_and_prevents_preparation(monkeypatch):
    delta,ground=supplier_chat_flow.extract(MESSAGE,{})
    state=chat_partners.merge({'articles':[],'partners':[]},delta,ground)
    def forbidden(*a,**kw):raise AssertionError('No Sage preparation for unsupported field')
    monkeypatch.setattr(supplier_sql,'prepare_operation',forbidden)
    reply=supplier_chat_flow.prepare_state(state)
    assert 'Email conservé' in reply and 'pas encore pris en charge' in reply
    p=state['partners'][0];assert p['operation']['status']=='blocked' and not p['approved']
    with pytest.raises(CrudError,match='email'):supplier_sql.parameters(p)
