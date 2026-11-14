import asyncio
import delivery_status as module
import telegram_order


TEXT='Contact : Hicham Bensidi\nNumero : 212661835737\nSosmajed Marrakech réclame le retardde la livraison cpj35, veuillez faire le nécessaire !!'


def test_followup_routes_before_creation_or_ai(monkeypatch):
    async def answer(text):
        assert text==TEXT
        return 'TEST : BL 2026BL19725 enregistré.'
    async def forbidden(*args,**kwargs):
        raise AssertionError('No AI or creation on a follow-up')
    monkeypatch.setattr(module,'answer',answer)
    monkeypatch.setattr(telegram_order,'prepare',forbidden)
    assert asyncio.run(telegram_order.handle([{'role':'user','content':TEXT}],'followup-test'))=='TEST : BL 2026BL19725 enregistré.'


def test_followup_looks_up_correct_customer_and_product(monkeypatch):
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[])
    def lookup(kind,code,**kwargs):
        if kind=='representative':return [{'REPNUM_0':'REP023'}]
        assert code=='Sosmajed Marrakech'
        assert kwargs['representative']=='REP023'
        return [{'BPCNUM_0':'C04772'}]
    def read(script,request):
        assert script=='sob-read.ps1'
        assert request=={'kind':'delivery_status','code':'recent','client':'C04772','article':'CPJ35'}
        return {'ok':True,'rows':[{'SOHNUM_0':'2026ARC14583','SDHNUM_0':'2026BL19725'}]}
    monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(module,'run_script',read)
    result=asyncio.run(module.answer(TEXT))
    assert '2026BL19725' in result and 'physique à confirmer' in result
    assert len(result)<=200


def test_no_delivery_and_multiple_orders_are_not_silently_selected():
    result=module.format_status([{'SOHNUM_0':'2026ARC1','SDHNUM_0':None},
                                 {'SOHNUM_0':'2026ARC2','SDHNUM_0':'2026BCH2'}],'CPJ35')
    assert 'aucun BL/BCH' in result and '2026BCH2' in result and 'dernières commandes' in result
    assert len(result)<=200


def test_mixed_followup_and_new_creation_is_never_created():
    assert 'Aucune commande créée' in asyncio.run(module.answer('Relance commande et créer une nouvelle commande'))


def test_order_notes_and_document_terms_are_not_followups():
    assert not module.is_followup('20 sacs CPJ45, livraison sans retard')
    assert not module.is_followup('Commande jointe\nDOCUMENT JOINT :\nPénalité de retard de livraison')


def test_followup_prefix_extracts_customer_after_product(monkeypatch):
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[])
    def lookup(kind,code,**kwargs):
        if kind=='representative':return [{'REPNUM_0':'REP046'}]
        assert code=='Small palace'
        return [{'BPCNUM_0':'C06812'}]
    def read(script,request):
        assert request['article']=='CPJ' and request['client']=='C06812'
        return {'ok':True,'rows':[{'SOHNUM_0':'2026ARC10','SDHNUM_0':None}]}
    monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(module,'run_script',read)
    assert 'aucun BL/BCH' in asyncio.run(module.answer('Contact : Siham Elhafidi\nRelance pour cpj Small palace.. 🚨'))
