from uuid import uuid4
from datetime import datetime,timezone
from app.services.learning_training import build_examples

def row(user,target,conversation=None):
    return {'id':uuid4(),'user_text':user,'expected':target,'conversation_id':conversation or uuid4(),'message_id':1,'created_at':datetime.now(timezone.utc)}

def test_dataset_anonymizes_same_entities_in_prompt_and_correction():
    examples,excluded=build_examples([row('Créer le fournisseur PRIVE SARL ICE : 001234567890123 Téléphone : 0612345678','Le fournisseur PRIVE SARL, ICE 001234567890123, est prêt.')])
    assert len(examples)==1
    text=str(examples)
    assert 'PRIVE SARL' not in text and '001234567890123' not in text and '0612345678' not in text
    assert '[NOM]' in text and '[ICE]' in text

def test_secrets_excluded_and_duplicate_private_entities_collapse():
    examples,excluded=build_examples([
        row('password=top-secret','ne pas exporter'),
        row('Créer le fournisseur ALPHA SARL ICE : 001234567890123','ALPHA SARL est prêt'),
        row('Créer le fournisseur BETA SARL ICE : 009876543210987','BETA SARL est prêt')])
    assert excluded['secret']==1 and len(examples)==1
    assert excluded['duplicate_or_near_duplicate']==1

def test_same_conversation_never_crosses_train_test_boundary():
    conversation=uuid4()
    examples,_=build_examples([row('Comment vérifier les identifiants ?','Contrôler le format.',conversation),row('Quelle procédure pour demander confirmation ?','Présenter la fiche puis attendre.',conversation)])
    assert len({e['split'] for e in examples})==1
