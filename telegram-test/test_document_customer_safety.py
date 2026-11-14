import asyncio
import json
import pytest
import prepare as module
import learning_memory
from creation import build_payload,CreationError
from app.core.config import settings
from app.services import ai_provider
from telegram_batch import document_references


def test_m2h_contact_company_is_an_emitter_in_a_cement_request():
    text='DOCUMENT JOINT :\nPROJET : DOMAINE ANFA\nDEMANDE | DE: | CIMENT\nCONTACT: | M2H | BUILDERS | Tél.: +212661763437\nN° Commande :100065'
    assert 'M2H BUILDERS' in module.document_issuer_names(text)
    assert document_references(text)=={'100065'}


def test_okd_order_number_before_number_is_recognized():
    text='DOCUMENT JOINT :\nCommande | NO: | 088/041126\nICE | : | 003457433000072'
    assert module.is_order_document(text)
    assert module.document_ices(text)=={'003457433000072'}
    assert document_references(text)=={'088/041126'}

def test_receiver_own_company_cannot_be_used_when_buyer_is_unreadable(monkeypatch):
    own={'BPCNUM_0':'C00191','BPCNAM_0':'OULD BOUAZZA','CUR_0':'MAD','REP_0':'REP003','VACBPR_0':'MAR'}
    async def complete(*a,**k):return {'message':{'content':json.dumps({'intent':'order','client':'C00191','lines':[{'article':'CPJ45','quantity':60,'unit':'SAC','price':81}]})}}
    def lookup(kind,code,*a,**k):
        if kind=='client':return [own] if code=='C00191' else []
        if kind=='article':return [{'ITMREF_0':'CPJ45','ITMDES1_0':'Ciment','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(ai_provider,'complete',complete);monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[{'kind':'policy','rule_key':'automatic_document_identity_exclusions','payload':{'value':['C00191']}}])
    d=asyncio.run(module.prepare([{'role':'user','content':'DOCUMENT JOINT :\nBON DE COMMANDE\nDestinataire : OULD BOUAZZA\n60 sacs CPJ45 81 DH'}],details=True))
    assert d['client'] is None
    assert 'client acheteur du document, pas son destinataire' in d['missing_fields']

def test_model_cannot_borrow_an_unrelated_existing_customer_for_a_document(monkeypatch):
    unrelated={'BPCNUM_0':'C08541','BPCNAM_0':'HAJJI FLORIDA','CUR_0':'MAD','REP_0':'REP003','VACBPR_0':'MAR'}
    async def complete(*a,**k):return {'message':{'content':json.dumps({'intent':'order','client':'C08541','lines':[{'article':'CPJ35','quantity':100,'unit':'SAC','price':65.42}]})}}
    def lookup(kind,code,*a,**k):
        if kind=='client':return [unrelated] if code=='C08541' else []
        if kind=='article':return [{'ITMREF_0':'CPJ35','ITMDES1_0':'Ciment','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(ai_provider,'complete',complete);monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    d=asyncio.run(module.prepare([{'role':'user','content':'DOCUMENT JOINT :\nSEYF CONSTRUCTION\nBON DE COMMANDE 38\nCIMENT CPJ35 100 SAC 65.42'}],details=True))
    assert d['client'] is None
    assert 'client acheteur du document à identifier depuis la source' in d['missing_fields']
    assert not d.get('reference_client_ob')


def test_okd_document_ice_resolves_customer_when_model_misses_it(monkeypatch):
    client={'BPCNUM_0':'C10187','BPCNAM_0':'OKD INVEST','CUR_0':'MAD','REP_0':'REP003','VACBPR_0':'MAR'}
    async def complete(*args,**kwargs):
        return {'message':{'content':json.dumps({'intent':'order','client':None,'lines':[{'article':'CPJ45','quantity':60,'unit':'SAC','price':81}]})}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client_by_ice':return [client] if code=='003457433000072' else []
        if kind=='client':return [client] if code=='C10187' else []
        if kind=='article':return [{'ITMREF_0':'CPJ45','ITMDES1_0':'Ciment','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    details=asyncio.run(module.prepare([{'role':'user','content':'DOCUMENT JOINT :\nCommande | NO: | 088/041126\nCiment 45 Tonne 3\nICE : 003457433000072'}],details=True))
    assert details['client']['BPCNUM_0']=='C10187'
    assert 'client Sage' not in details['missing_fields']


def test_conflicting_verified_document_customer_blocks_creation(monkeypatch):
    wrong={'BPCNUM_0':'C01975','BPCNAM_0':'NAJHI ABDERRAHMAN','CUR_0':'MAD','REP_0':'REP008','VACBPR_0':'MAR'}
    right={'BPCNUM_0':'C08090','BPCNAM_0':'M2H BUILDERS','CUR_0':'MAD','REP_0':'REP027','VACBPR_0':'MAR'}
    draft={'intent':'order','client':'C01975','lines':[{'article':'CPJ35','quantity':300,'unit':'SAC','price':79}]}
    async def complete(*args,**kwargs):return {'message':{'content':json.dumps(draft)}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client_by_ice':return [wrong]  # simulate contradictory document evidence
        if kind=='client':return [right] if code=='M2H BUILDERS' else [wrong] if code=='C01975' else []
        if kind=='article':return [{'ITMREF_0':'CPJ35','ITMDES1_0':'Ciment','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    source='DOCUMENT JOINT (données à vérifier avant validation) :\nDEMANDE DE CIMENT\nCONTACT: M2H BUILDERS\nRéférence fournisseur : C01975\nICE 003244463000005\nCIMENT CPJ35 300 SAC'
    details=asyncio.run(module.prepare([{'role':'user','content':source}],details=True))
    assert 'client incompatible avec l’émetteur du document' in details['missing_fields']
    with pytest.raises(CreationError):build_payload(details)
