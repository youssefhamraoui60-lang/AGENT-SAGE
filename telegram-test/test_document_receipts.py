import asyncio
import document_receipts as module
import telegram_order


TEXT='DOCUMENT JOINT :\nBON DE COMMANDE N°3109 JR 2026\nICE 002910359000007'
RULE={'kind':'interpretation','rule_key':'document_receipt_jr_3109',
      'payload':{'reference':'3109','year':2026,'ice':'002910359000007','client':'C08534','order':'2026ARC15017'}}


def test_known_pdf_returns_verified_existing_order_without_creation(monkeypatch):
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[RULE])
    monkeypatch.setattr(module,'run_script',lambda script,request:{'ok':True,'rows':[{'BPCORD_0':'C08534'}]})
    async def forbidden(*args,**kwargs):raise AssertionError('Must not create a duplicate')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    assert '2026ARC15017' in asyncio.run(telegram_order.handle([{'role':'user','content':TEXT}],'new-message-same-pdf'))


def test_same_number_from_another_issuer_does_not_match_receipt(monkeypatch):
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[RULE])
    assert asyncio.run(module.known_receipt(TEXT.replace('002910359000007','001234567890123'))) is None


def test_wrong_client_in_sage_requires_review_instead_of_recreation(monkeypatch):
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[RULE])
    monkeypatch.setattr(module,'run_script',lambda script,request:{'ok':True,'rows':[{'BPCORD_0':'C99999'}]})
    result=asyncio.run(module.known_receipt(TEXT))
    assert 'vérifier' in result and 'déjà créé' not in result
