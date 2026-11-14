from pathlib import Path
import pytest
import document_memory
import learning_memory
from prepare import steel_supplier
import creation


def test_exact_document_transcription_does_not_match_changed_image(tmp_path, monkeypatch):
    path = tmp_path / 'image.jpg'
    path.write_bytes(b'original-photo')
    digest = document_memory.fingerprint(path)
    monkeypatch.setattr(learning_memory, 'approved_rules', lambda: [
        {'kind': 'interpretation', 'rule_key': 'document_sha256_' + digest,
         'payload': {'transcription': 'Fer 6 : 2 tonnes'}}])
    def empty_reader(path):
        return {'pages': [{'text': '', 'uncertain': True}]}
    assert document_memory.decode(path, empty_reader)['text'] == 'Fer 6 : 2 tonnes'
    path.write_bytes(b'changed-quantity-photo')
    assert document_memory.decode(path, empty_reader)['ok'] is False

def test_reviewed_buyer_identity_does_not_replace_or_leak_document_rows(tmp_path,monkeypatch):
    path=tmp_path/'order.pdf';path.write_bytes(b'original-buyer-document')
    digest=document_memory.fingerprint(path)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[{'kind':'interpretation','rule_key':'document_sha256_'+digest,'payload':{'issuer_name':'BORA CONSTRUCTION'}}])
    reader=lambda p:{'pages':[{'text':'BON DE COMMANDE\nCPJ45 540 SAC 71.66 HT','uncertain':True,'method':'pdf_words_rows'}]}
    result=document_memory.decode(path,reader)
    assert result['text'].startswith('Client : BORA CONSTRUCTION\n')
    assert '540 SAC 71.66 HT' in result['text']
    path.write_bytes(b'another-document')
    assert not document_memory.decode(path,reader)['text'].startswith('Client : BORA')


def test_steel_supplier_requires_whole_explicit_phrase():
    token = learning_memory.ACTIVE.set(({'kind': 'policy', 'rule_key': 'steel_supplier_phrases',
        'payload': {'value': {'Hdude 3adi': 'F050'}}},))
    try:
        assert steel_supplier('Fettouh abdellah\nHdude 3adi\nBarre droite') == 'F050'
        assert steel_supplier('Fettouh abdellah\nSounacid') is None
        assert steel_supplier('pas Hdude 3adi') is None
    finally:
        learning_memory.ACTIVE.reset(token)


def test_supplier_is_bound_to_creation_payload():
    details = {'client': {'BPCNUM_0': 'C01401', 'CUR_0': 'MAD'}, 'missing': [],
        'delivery': '2026-11-10', 'lines': [{'article': 'RAB8', 'quantity': 2000,
        'price': 9.1, 'supplier': 'F050'}]}
    assert creation.build_payload(details)['lines'][0]['supplier'] == 'F050'
    details['lines'][0]['supplier'] = "F050'; SQL"
    with pytest.raises(creation.CreationError, match='fournisseur'):
        creation.build_payload(details)
