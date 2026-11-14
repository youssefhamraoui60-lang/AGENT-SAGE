import pytest
from app.services import supplier_dialogue as dialogue,supplier_chat_flow,chat_partners

def empty():return {'articles':[],'partners':[]}

def test_exact_user_conversation_never_treats_language_as_supplier_name():
    state=empty()
    for text in ['BARI Ne ajouter wahade foourniseur','je dire créer un fourniseur mais on darija','le darija pas le nom de fourniseur sample darija']:
        result=dialogue.handle(text,state)
        assert result and not result.get('prepare')
        state=result['state']
        assert len(state['partners'])==1 and not state['partners'][0].get('nom')
        assert state['_supplier_dialogue']['expected_field']=='nom'
    identifier=state['partners'][0]['id']
    result=dialogue.handle('le nom de fourniseur est ABDHADI TA',state)
    p=result['state']['partners'][0]
    assert result['prepare'] and p['nom']=='ABDHADI TA' and p['id']==identifier and not p['approved']

@pytest.mark.parametrize('text',['le nom de fournisseur est ABDHADI TA','le nom du fournisseur est ABDHADI TA','le nom est ABDHADI TA','Nom : ABDHADI TA'])
def test_explicit_name_before_short_answer_handling(text):
    state=dialogue.handle('Créer un fournisseur',empty())['state']
    result=dialogue.handle(text,state)
    assert result['state']['partners'][0]['nom']=='ABDHADI TA'

def test_language_correction_repairs_false_draft_without_losing_other_fields():
    state={'articles':[],'partners':[{'id':'same','kind':'supplier','nom':'mais on darija','ice':'001234567890123','operation':{'status':'prepared'},'approved':True}]}
    result=dialogue.handle('le darija pas le nom de fourniseur sample darija',state)
    p=result['state']['partners'][0]
    assert p['nom'] is None and p['ice']=='001234567890123' and p['id']=='same' and not p['approved']

def test_created_supplier_is_not_changed():
    state={'articles':[],'partners':[{'id':'created','kind':'supplier','nom':'ABDHADI TA','operation':{'status':'succeeded','code':'F10031'}}]}
    result=dialogue.handle('le darija pas le nom de fourniseur sample darija',state)
    assert result['state']['partners']==state['partners']

def test_explicit_company_name_containing_darija_is_literal():
    state=dialogue.handle('Créer un fournisseur',empty())['state']
    result=dialogue.handle('le nom du fournisseur est DARIJA SERVICES',state)
    assert result['state']['partners'][0]['nom']=='DARIJA SERVICES'

def test_language_statement_does_not_reach_deterministic_name_extractor():
    assert supplier_chat_flow.extract('je dire créer un fourniseur mais on darija',empty()) is None

@pytest.mark.parametrize('text',['le nom de fourniseur est ABDHADI TA','le nom du fournisseur est ABDHADI TA','Nom de frs : ABDHADI TA'])
def test_explicit_supplier_name_starts_fresh_conversation(text):
    result=dialogue.handle(text,empty())
    assert result and result['prepare']
    p=result['state']['partners'][0]
    assert p['nom']=='ABDHADI TA' and not p['approved'] and not p.get('ice')
    assert not p.get('ville') and not p.get('conditions_paiement')

def test_context_free_name_does_not_force_a_supplier():
    assert dialogue.handle('Nom : ABDHADI TA',empty()) is None

@pytest.mark.parametrize('text',["le fournisseur s’appelle Atlas Fournitures","le fournisseur s'appelle Atlas Fournitures",'le fournisseur se nomme Atlas Fournitures','le fournisseur a pour nom Atlas Fournitures'])
def test_supplier_name_sentence_only_keeps_identity(text):
    initial=dialogue.handle('bonjour je veux créer un fournisseur',empty())['state']
    result=dialogue.handle(text,initial)
    assert result['prepare'] and result['state']['partners'][0]['nom']=='Atlas Fournitures'
    assert not result['state']['partners'][0]['approved']
