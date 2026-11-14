import asyncio
import order_amendments as module
import telegram_order

CONTACT='Contact : Abdelmajid\nNumero : 212761677064\n'
DOC=CONTACT+'DOCUMENT JOINT :\nN° Commande :100065\n2026 ICE 003244463000005\n'
FEE=CONTACT+'+300 dh frais de transport'
RULE={'kind':'interpretation','rule_key':'document_receipt_m2h',
      'payload':{'reference':'100065','year':2026,'ice':'003244463000005','client':'C08090','order':'2026ARC15048'}}


def test_supplement_does_not_consume_goods_or_another_contacts_fee():
    assert module.transport_supplement(FEE)==300
    assert module.transport_supplement(DOC+'\n'+FEE)==300
    assert module.transport_supplement(FEE+'\n20 sacs cpj45') is None
    assert module.transport_supplement(DOC+'\n'+FEE.replace('Abdelmajid','Wiam')) is None
    assert module.transport_supplement(CONTACT+'300 dh frais de transport') is None


def test_late_fee_is_saved_before_duplicate_guard_without_creating(monkeypatch):
    saved=[]
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[RULE])
    monkeypatch.setattr(module.creation,'run_script',lambda *a:{'ok':True,'rows':[{'BPCORD_0':'C08090'}]})
    monkeypatch.setattr(module.drafts,'save',lambda *a:saved.append(a))
    async def forbidden(*a,**kw):raise AssertionError('Must not recreate goods')
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    history=[{'role':'user','content':DOC},{'role':'user','content':FEE}]
    reply=asyncio.run(telegram_order.handle(history,'telegram:group:sender:100'))
    assert '2026ARC15048' in reply and 'non appliquée' in reply
    assert saved[0][1]['article']=='MANTD' and saved[0][1]['price']==300
    assert saved[0][1]['quantity']==1
    assert len(telegram_order.short(reply))<=200


def test_missing_receipt_keeps_transport_and_requests_current_order(monkeypatch):
    saved=[]
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[RULE])
    monkeypatch.setattr(module.creation,'run_script',lambda *a:{'ok':True,'rows':[]})
    monkeypatch.setattr(module.drafts,'save',lambda *a:saved.append(a))
    reply=asyncio.run(module.handle([{'role':'user','content':DOC+'\n'+FEE}],'telegram:group:sender:101'))
    assert 'numéro actuel' in reply and 'Aucun ajout effectué' in reply
    assert saved[0][1]['status']=='amendment_receipt_unverified'
