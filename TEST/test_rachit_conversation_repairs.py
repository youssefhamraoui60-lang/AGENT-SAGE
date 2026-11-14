import pytest
from test_chat_supplier_sql import supplier
from app.services import supplier_sql as sql, supplier_snapshots
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,fact,send
from test_conversation_chat import create

@pytest.mark.parametrize('label',['Virement 60 Jour','Virement 60 Jours','Virement à 60 jours'])
def test_payment_singular_resolves_only_verified_reference(label):
    p=supplier();p['conditions_paiement']=label
    values=sql.parameters(p,{'__reference_labels':[{'kind':'Paiement','label':'Virement 60 Jours','code':'VIR60'}]})
    assert values['Paiement']=='VIR60'

@pytest.mark.parametrize('status',['désactivé','désactivée','inactif','1','actif','2'])
def test_explicit_status_is_preserved_and_displayed(status):
    p=supplier();p['statut']=status
    values=sql.parameters(p,{})
    assert values['Statut']==('2' if status in ('actif','2') else '1')
    assert any(r['key']=='Statut' and r['value']==status for r in supplier_snapshots.capture({'partners':[p]})[0]['rows'])

def test_explicit_address_cannot_be_silently_split_into_city(native_chat):
    c,q,_,_,attempts,_=native_chat
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','Rachit it'),fact('ville','Casablanca')])),say('Fiche conservée.')])
    s=send(c,create(c),'Créer fournisseur Rachit it ville Casablanca')
    p=s['state']['partners'][0]
    text='ADDIRESE EST : hayraha berrchid casabalca 232 60 R6 ST 67 60K'
    q.extend([native(call('prepare_draft',resource='supplier',mode='update',target_id=p['id'],fields=[fact('adresse','232 60 R6 ST 67 60K'),fact('ville','berrchid casabalca')])),say('Adresse conservée.')])
    s=send(c,s,text);p=s['state']['partners'][0]
    assert p['adresse']=='hayraha berrchid casabalca 232 60 R6 ST 67 60K'
    assert p['ville']=='Casablanca'
    assert all(not a['execute'] for a in attempts)
