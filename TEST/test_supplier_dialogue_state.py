import pytest
from app.services import supplier_dialogue as dialogue,chat_partners,supplier_chat_flow

def draft(text='Créer le fournisseur CIMAT ICE 001234567890123 paiement chèque 30 jours'):
    delta,ground=supplier_chat_flow.extract(text,{'articles':[],'partners':[]})
    return chat_partners.merge({'articles':[],'partners':[]},delta,ground)

def test_missing_name_then_short_name():
    result=dialogue.handle('Je veux créer un fournisseur',{'articles':[],'partners':[]})
    assert result['state']['_supplier_dialogue']['expected_field']=='nom'
    result=dialogue.handle('Berrechid Pièces',result['state'])
    assert result['prepare'] and result['state']['partners'][0]['nom']=='Berrechid Pièces'
    assert not result['state']['partners'][0]['approved']

def test_city_short_reply_and_targeted_correction():
    state=draft();result=dialogue.handle('adresse',state)
    result=dialogue.handle('Berrechid',result['state'])
    assert result['state']['partners'][0]['adresse']=='Berrechid'
    result=dialogue.handle('non, c’est la ville',result['state'])
    p=result['state']['partners'][0]
    assert p['ville']=='Berrechid' and not p.get('adresse') and p['ice']=='001234567890123'

def test_payment_days_retain_method():
    state=draft();result=dialogue.handle('plutôt 60 jours',state)
    assert result['state']['partners'][0]['conditions_paiement']=='cheque 60 jours'

def test_explicit_new_after_duplicate_has_no_inherited_data():
    state=draft();state['partners'][0]['operation']={'status':'blocked'}
    old=state['partners'][0]['id']
    result=dialogue.handle('créer un nouveau fournisseur cimt34',state)
    p=result['state']['partners'][0]
    assert p['id']!=old and p['nom']=='cimt34'
    assert not p.get('ice') and not p.get('conditions_paiement')

def test_correction_of_current_draft_not_durable_rule():
    result=dialogue.handle('Correction : le nom est CIMAT SARL',draft())
    assert result['state']['partners'][0]['nom']=='CIMAT SARL'
    assert not result['state'].get('memory_focus')

def test_unavailable_model_retains_data_without_claiming_verification():
    state=draft();preserved,reply=dialogue.fallback('compléter svp',state)
    assert preserved['partners']==state['partners']
    assert 'conservée' in reply and 'créé' not in reply

def test_article_not_intercepted():
    assert dialogue.handle('ville',{'articles':[{'id':'a'}],'partners':[]}) is None
