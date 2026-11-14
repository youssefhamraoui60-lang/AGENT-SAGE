"""Twelve successive turns: isolated PostgreSQL, mocked Sage, no approvals."""
from test_supplier_independent_tasks import scenario, send, create, fixture
from app.services import modification_actions
from app.services import supplier_tasks
import pytest

MESSAGES = [
    "Salam, bghit ncréer fournisseur jdid smito CASA TECH TEST, kayn f Casablanca, SARL AU, téléphone 0611223344, ICE mazal ma3ndich.",
    "Zid fournisseur tani smito RABAT INDUSTRIE TEST, f Rabat, SARL, téléphone 0622334455. Kheli l'premier kif ma howa.",
    "Pour le premier, je me suis trompé f téléphone, le bon numéro c'est 0666778899, matbdelch dyal deuxième.",
    "Vérifie wach CASA TECH TEST et RABAT INDUSTRIE TEST kaynin déjà f Sage TEST, mais matcréihomch.",
    "Maintenant cherche F468 et affiche seulement son statut actuel et son nom.",
    "Je veux modifier le téléphone de F468, mais je connais pas encore le nouveau numéro. Prépare rien à enregistrer.",
    "Non, kan9sed F007 machi F468 pour le changement du téléphone. F468 touche pas.",
    "Le nouveau téléphone de F007 est 0655443322, prépare la modification mais matvalidich.",
    "Pour F007, annule la modification du téléphone, finalement bghit ghir consulter sa fiche.",
    "Reviens au fournisseur RABAT INDUSTRIE TEST et corrige sa ville : finalement c'est Salé, pas Rabat.",
    "Pour CASA TECH TEST, ajoute son capital 150000 DH. Le deuxième fournisseur reste sans capital renseigné.",
    "Donne-moi un résumé séparé des deux créations et des consultations F007/F468. Chno baqi na9es, quels doublons ont été trouvés, et quelles actions sont en attente ? Ne modifie rien dans Sage.",
]


def test_exact_twelve_turns(scenario, monkeypatch):
    c, q, calls = scenario
    prepared = []
    def prepare(d):
        prepared.append((d['code'], d['changes'].copy()))
        d['operation'] = {'status': 'prepared', 'message': 'Modification à confirmer.'}
    monkeypatch.setattr(modification_actions, 'prepare_draft', prepare)
    s = create(c)
    for i, text in enumerate(MESSAGES):
        s = send(c, s, text)
        state = s['state']; p = state['partners']; reply = s['messages'][-1]['content']
        assert 'nouvelle fiche fournisseur ou' not in reply
        assert len(p) == (1 if i == 0 else 2)
        assert p[0]['nom'] == 'CASA TECH TEST'
        assert p[0]['ville'] == 'Casablanca'
        assert p[0]['forme_juridique'] == 'SARL AU'
        assert not p[0].get('ice')
        assert p[0]['telephone'] == ('0611223344' if i < 2 else '0666778899')
        if i >= 1:
            assert p[1]['nom'] == 'RABAT INDUSTRIE TEST'
            assert p[1]['ville'] == ('Rabat' if i < 9 else 'Salé')
            assert p[1]['telephone'] == '0622334455'
            assert p[1]['forme_juridique'] == 'SARL'
        if i < 7: assert not prepared
        if i == 5: assert state['supplier_tasks']['control']['field'] == 'phone'
        if i == 6: assert state['supplier_tasks']['control']['code'] == 'F007'
        if i == 7: assert prepared == [('F007', {'phone': '0655443322'})]
        if i >= 8:
            assert state['modification_drafts'][0]['operation']['status'] == 'cancelled'
            assert state['supplier_tasks']['control']['kind'] == 'search'
        if i >= 10:
            assert p[0]['capital'] == '150000 DH'
            assert not p[1].get('capital')
    assert all(name in reply for name in ('CASA TECH TEST', 'RABAT INDUSTRIE TEST', 'F007', 'F468'))
    assert not q
    assert all(call['tool'] in ('get_supplier_record', 'check_supplier_fiscal_duplicates') for call in calls)


@pytest.mark.parametrize('city', ['Casablanca', 'Casa', 'Rabat'])
@pytest.mark.parametrize('separator', [', kayn f ', ' kayn f '])
def test_darija_creation_variants_without_inference(city, separator):
    s = supplier_tasks.route('Salam bghit ncréer fournisseur jdid smito CASA TECH TEST'+separator+city+', SARL AU, téléphone 0611223344, ICE mazal ma3ndich.', {'partners': [], 'articles': []})['state']
    p = s['partners'][0]
    assert p['nom'] == 'CASA TECH TEST'
    assert p['ville'] == ('Casablanca' if city == 'Casa' else city)
    assert p['telephone'] == '0611223344'
    assert p['forme_juridique'] == 'SARL AU'
    assert p['field_states']['ice']['status'] == 'unknown'


def test_executing_creation_is_not_replaced():
    state = {'partners': [{'id': 'one', 'nom': 'ORIGINAL', 'operation': {'status': 'executing'}}]}
    result = supplier_tasks.route(MESSAGES[0], state)
    assert result['state']['partners'] == state['partners']
