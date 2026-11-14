import pytest
from test_chat_supplier_sql import workflow,supplier
from app.services import supplier_sql as sql,chat_partners
from app.services.supplier_chat_flow import extract

@pytest.mark.parametrize('message',[
 'Bonjour, je vous transmets les coordonnées de Exemple Logistique SARL pour son enregistrement. Adresse : 206, quartier industriel, El Jadida ; Règlement par virement au comptant.',
 'Veuillez enregistrer notre nouveau fournisseur Exemple Métallique.\n- Téléphone : 0677803890\n- Règlement par virement à 30 jours\n- IF : 26384060\nCordialement.',
 'Je souhaite préparer une nouvelle fiche pour Exemple Bureau SA, sous réserve de validation. Téléphone : 0681255141 ; RC : 670323.',
 'Le service achats demande l’ajout de Exemple Carburants SARL comme fournisseur. RC : 628725. Ne créez pas de commande à ce stade.',
])
def test_prepare_then_confirm_then_verified_mock_execution(workflow,monkeypatch,message):
    state,calls,call=workflow
    defaults=sql.parameters(supplier())
    monkeypatch.setattr(sql,'load_defaults',lambda:defaults)
    monkeypatch.setattr(sql,'load_reference_labels',lambda:[{'kind':'Paiement','label':'Virement Comptant','code':'VIR00'},{'kind':'Paiement','label':'Virement 30 Jours','code':'VIR30'}])
    delta,grounding=extract(message,{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    state['partners']=[p]
    assert call('prepare').status_code==200
    assert call('execute',True).status_code==403 and calls==[False]
    assert call('approve',True).status_code==200
    result=call('execute',True)
    assert result.status_code==200
    assert result.json()['state']['partners'][0]['operation']['status']=='succeeded'
    assert calls==[False,True]  # Fake SQL only, no real supplier is inserted.
    assert call('execute',True).status_code==409

def test_full_address_is_preserved_not_truncated_to_expected_street():
    message='Merci de créer le fournisseur Exemple. Adresse : 206, quartier industriel, El Jadida. Facturation en TTC.'
    delta,grounding=extract(message,{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['adresse']=='206, quartier industriel, El Jadida'
    assert not p.get('ville') and p['type_montant']=='TTC'

def test_actual_sage_size_failure_is_explained_without_truncation():
    message=sql.preparation_message({'sql_error_number':50105,'field_errors':[{'field':'Nom','length':38,'limit':35}]})
    assert 'Nom du fournisseur : 38 caractères, maximum 35' in message
    assert 'Corrigez-les dans le chat' in message
