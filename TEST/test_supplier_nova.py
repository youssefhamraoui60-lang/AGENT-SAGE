import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.supplier_chat_flow import extract
from app.services import chat_partners,supplier_sql

MESSAGE='Bonjour, Merci de créer le fournisseur suivant dans Sage X3 : Raison sociale : NOVA ÉQUIPEMENT SARL Nom court : NOVA EQUIP ICE : 005678901234567 IF : 56789123 RC : 25467 Date de régularité fiscale : 20/10/2026 Adresse : 25, Zone industrielle Aïn Sebaâ Ville : Casablanca Pays : Maroc Téléphone : 0669876543 Fax : 0522345678 Catégorie : FR Code comptable : STD Régime taxe : MAR Condition paiement : Virement 30 jours Type montant : TTC Devise : MAD Merci de préparer la fiche pour validation.'

def parsed():
    delta,text=extract(MESSAGE,{})
    return chat_partners.merge({'articles':[],'partners':[]},delta,text)['partners'][0]

def test_full_message_preserves_each_field_without_model():
    p=parsed()
    expected={'nom':'NOVA ÉQUIPEMENT SARL','intitule_court':'NOVA EQUIP','ice':'005678901234567',
        'identifiant_fiscal':'56789123','rc':'25467','date_regularite':'2026-10-20',
        'adresse':'25, Zone industrielle Aïn Sebaâ','ville':'Casablanca','pays':'Maroc',
        'telephone':'0669876543','fax':'0522345678','categorie_fournisseur':'FR',
        'code_comptable':'STD','regime_taxe':'MAR','conditions_paiement':'Virement 30 jours',
        'type_montant':'TTC','devise':'MAD'}
    assert {k:p.get(k) for k in expected}==expected

def test_reference_labels_resolve_to_exact_verified_codes():
    p=parsed()
    defaults={'__reference_labels':[{'kind':'Pays','code':'MA','label':'Maroc'},
        {'kind':'Paiement','code':'VIR30','label':'Virement 30 Jours'}]}
    values=supplier_sql.parameters(p,defaults)
    assert values['Pays']=='MA' and values['Paiement']=='VIR30'
    assert values['NomCourt']=='NOVA EQUIP' and values['TypeLibelle']=='TTC'
    assert p['conditions_paiement']=='Virement 30 jours'

def test_missing_reference_never_uses_a_different_default():
    import pytest
    from app.services.sage_crud import CrudError
    with pytest.raises(CrudError):supplier_sql.parameters(parsed(),{'__reference_labels':[],'Paiement':'CHQ00'})
