import pytest
from test_supplier_nova import parsed as unused
from app.services.supplier_language import extract_request
from app.services.supplier_chat_flow import extract
from app.services import chat_partners

@pytest.mark.parametrize('message',[
 'Merci de saisir notre prestataire DELTA MECANIQUE. localité : El Jadida; règlement : VIR30; identifiant fiscal : 00012345 Je confirme après vérification.',
 'Bonsoir, besoin de référencer DELTA MECANIQUE dans Sage TEST. identifiant fiscal 00012345 / mdina El Jadida / khalass VIR30 Ne pas lancer la création avant accord.',
 'Salam zid lina fournisseur smitou DELTA MECANIQUE. ville El Jadida; IF 00012345; paiement VIR30 w 3tini les infos bach nconfirmi.',
 'عافاك وجد ليا fournisseur جديد سميتو DELTA MECANIQUE. IF 00012345; ville El Jadida; règlement VIR30 وريني المعلومات قبل التأكيد.',
])
def test_multilingual_independent_values_are_grounded(message):
    delta,grounding=extract(message,{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='DELTA MECANIQUE' and p['ville']=='El Jadida'
    assert p['identifiant_fiscal']=='00012345' and p['conditions_paiement']=='VIR30'
    assert not p.get('approved') and not p.get('operation')

def test_corrections_override_only_the_corrected_fields():
    message='Nom provisoire : ANCIEN NOM. Finalement le nom correct est NOUVEAU NOM. Paiement prévu au début : CHQ00. Correction finale : EFF60. Frs jdid -> NOUVEAU NOM. ICE 012345678901234 / khalass EFF60 / fax 0522000000 Prépare seulement la fiche.'
    delta,grounding=extract(message,{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='NOUVEAU NOM' and p['conditions_paiement']=='EFF60'
    assert p['fax']=='0522000000' and p['ice']=='012345678901234'

@pytest.mark.parametrize('body',[
 'ICE : inconnu','IF : 123ABC','date régularité fiscale : 31/02/2026',
 'type montant : HT ou TTC', 'ICE : 012345678901234 / ICE : 999999999999999',
 'dossier : OB', 'code comptable : SPECIAL',
])
def test_uncertain_or_unsupported_values_use_complete_semantic_path(body):
    assert extract_request('Frs jdid -> DELTA MECANIQUE. '+body) is None

def test_does_not_intercept_mixed_article_creation():
    assert extract_request('Frs jdid -> DELTA MECANIQUE. Ajouter un article câble.') is None

def test_lookup_is_not_changed_to_a_creation_request():
    assert extract_request('Recherche le fournisseur existant, nom : DELTA MECANIQUE, ICE : 012345678901234.') is None

def test_internal_periods_in_company_name_are_preserved():
    delta,grounding=extract('Merci de saisir notre prestataire IZS.TEX S.A.R.L. ICE : 012345678901234 Je confirme après vérification.',{})
    p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
    assert p['nom']=='IZS.TEX S.A.R.L' and p['ice']=='012345678901234'
