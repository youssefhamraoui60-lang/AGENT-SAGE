import pytest
from test_supplier_nova import parsed as unused
from app.services.supplier_chat_flow import extract
from app.services import chat_partners

def replay(turns):
    state={'articles':[],'partners':[]};history=[];identifier=None
    for text in turns:
        parsed=extract(text,state,history);assert parsed is not None,text
        delta,grounding=parsed;state=chat_partners.merge(state,delta,grounding)
        assert len(state['partners'])==1
        p=state['partners'][0]
        if identifier:assert p['id']==identifier
        identifier=p['id'];history.append({'role':'user','content':text})
        assert not p.get('approved') and not state['articles']
    return state['partners'][0]

def test_manually_annotated_progressive_dialogue_and_final_corrections():
    p=replay(['3afak zid lina frs jdid najib sarl','oui ouii cree le fourniseur najib sarl',
      'faut pas copier ice de ancien frs','son ice et 592589839266670, il est a casablanka',
      'nom court najib sarl et regim mar','if 3681462 rc 13981 et paymant effet 60jr',
      'il paye par cheque 30j et le telephone 0664257535',
      'non le paymant c effet 60 jour pas cheque','desole le bon ice c 050325912663415',
      'non att le nome exacte c Najib Services SARL','la devise mad et le type ttc',
      'petite corection c rabat pas casablanka','oui daba zidou f sage','reprendre l analyse svp'])
    expected={'nom':'Najib Services SARL','ice':'050325912663415','identifiant_fiscal':'3681462','rc':'13981',
      'intitule_court':'najib sarl','regime_taxe':'MAR','conditions_paiement':'effet 60 jours',
      'telephone':'0664257535','devise':'MAD','type_montant':'TTC','ville':'rabat'}
    assert {k:p.get(k) for k in expected}==expected

@pytest.mark.parametrize('initial,name',[
 ('merci de faire un nvx tier fournisseur omar trensport','omar trensport'),
 ('je veux ouvrire un nouveu compte frnseur rachad logistike','rachad logistike'),
 ('bonjou jai beosin dajouter un frs brahim constriction','brahim constriction'),
 ('slt je veu crrer le fornnseur hassan service','hassan service'),
 ('bsr je vou dré ajt le frnisseur najib service','najib service'),
 ('bonjour merci de creeer le founiseur youssef matiriaux','youssef matiriaux'),
 ('slm 3ndna frs jdid smito nour atlier bghit dir lih fiche','nour atlier'),
 ('wa9ila khassna nzido frs hamza atlier f system','hamza atlier'),
 ('je souhait creér safia atlier comme frnss','safia atlier'),
])
def test_severe_initial_typos_preserve_literal_name(initial,name):
    p=replay([initial,'ice dyalo 012345678901234 w tel 0661234567'])
    assert p['nom']==name and p['ice']=='012345678901234' and p['telephone']=='0661234567'

def test_repeated_no_ice_statement_never_clears_known_ice():
    p=replay(['3afak zid lina frs jdid Atlas Services','son ice 012345678901234 et rc 1234',
      'je sai pas son ice pour le moment','faut pas copier ice de ancien frs','oui continue stp'])
    assert p['ice']=='012345678901234' and p['rc']=='1234'

def test_long_explicit_short_name_is_kept_for_sage_size_validation():
    p=replay(['3afak zid lina frs jdid salam commerce','nom court salam commer et regim mar'])
    assert p['intitule_court']=='salam commer' # 12 chars: do not crash or silently truncate.

def test_ambiguous_city_correction_does_not_invent_a_name():
    from app.services.supplier_noisy_language import facts
    assert 'ville' not in facts('petite corection c bizarre pas autre chose')

def test_bounded_geo_clause_never_uses_payment_as_city():
    p=replay(['Fournisseur à ajouter : MÉDINA CONSEIL SA, Meknès. paiement par virement à 30 jours.'])
    assert p['nom']=='MÉDINA CONSEIL SA' and p['ville']=='Meknès'
    assert p['conditions_paiement']=='virement 30 jours'

def test_approval_phrase_is_never_a_geographical_clause():
    p=replay(['Pourriez-vous procéder au référencement du fournisseur Orient Nettoyage Industriel ? La création doit être soumise à mon approbation.'])
    assert p['nom']=='Orient Nettoyage Industriel' and not p.get('ville')

def test_long_short_name_survives_checkpoint_without_relaxing_client_schema():
    from app.services.chat_model import Delta
    from app.schemas.conversation_entities import PartnerPatch
    parsed=extract('nom court salam commer et regim mar',{'partners':[{'kind':'supplier','nom':'Salam'}]})
    restored=Delta.model_validate(parsed[0].model_dump())
    assert restored.fournisseurs[0].intitule_court=='salam commer'
    with pytest.raises(ValueError):PartnerPatch(intitule_court='salam commer')
