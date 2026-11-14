import asyncio
import json
import pytest
import prepare as module
from app.core.config import settings
from app.services import ai_provider


@pytest.mark.parametrize('include_receiver',[False,True])
@pytest.mark.parametrize('model_client',[None,'OULD BOUAZZA'])
@pytest.mark.parametrize('ice_label',['ICE','I.C.E.'])
def test_purchase_order_ice_and_tonne_price_resolve_without_guessing_customer(monkeypatch,include_receiver,model_client,ice_label):
    draft={'client':model_client,'intent':'order','lines':[{'article':'CPJ45','quantity':12,'unit':'tonne','price':1640.004,'price_unit':'tonne'}]}
    client={'BPCNUM_0':'C08534','BPCNAM_0':'JR FLOORING','CUR_0':'MAD','REP_0':'REP046','VACBPR_0':'MAR'}
    async def complete(*args,**kwargs):return {'message':{'content':json.dumps(draft)}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client_by_ice':
            assert code=='002910359000007'
            return [client]+([{'BPCNUM_0':'C00191','BPCNAM_0':'OULD BOUAZZA'}] if include_receiver else [])
        if kind=='client' and code=='C08534':return [client]
        if kind=='article':return [{'ITMREF_0':'CPJ45','ITMDES1_0':'Ciment CPJ45','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup)
    monkeypatch.setattr(module.learning_memory,'approved_rules',lambda:[{'kind':'policy','rule_key':'automatic_document_identity_exclusions','payload':{'value':['C00191']}}])
    result=asyncio.run(module.prepare([{'role':'user','content':'BON | DE | COMMANDE 3109\n12 tonnes CPJ45\n'+ice_label+': | 002910359000007'}],details=True))
    assert result['client']['BPCNUM_0']=='C08534'
    assert result['lines'][0]['quantity']==240
    assert result['lines'][0]['price']==82.0002
    assert result['missing_fields']==[]
