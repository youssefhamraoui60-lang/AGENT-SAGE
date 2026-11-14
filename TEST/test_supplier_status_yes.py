import asyncio
import pytest
from app.services import conversation_tools as e

@pytest.mark.parametrize('answer',['oui','o ui','ok'])
def test_acknowledgement_prepares_only_unique_verified_supplier(monkeypatch,answer):
    calls=[]
    state={'supplier_target':'TEST','pending_supplier_status_intent':{'folder':'TEST','enabled':False,'text':'désactiver rachide'},'tool_read_results':[{'ok':True,'folder':'TEST','resource':'supplier','rows':[{'BPSNUM_0':'F10043','BPRNAM_0':'Ahmde rachide'}]}]}
    def read(args,state,text):
        assert args.code=='F10043'
        result={'ok':True,'folder':'TEST','resource':'supplier','code':args.code};state['tool_read_results'].append(result);return result
    def dispatch(name,args,state,text,*unused):
        calls.append((name,args));return {'ok':True,'status':'prepared','message':'Proposition à confirmer.'}
    monkeypatch.setattr(e,'read',read);monkeypatch.setattr(e,'dispatch',dispatch)
    r=asyncio.run(e.turn(None,None,answer,state,[]))
    assert r['phase']=='supplier_status_selection'
    assert len(calls)==1 and calls[0][0]=='prepare_modification'
    assert calls[0][1].changes[0].field=='enabled' and calls[0][1].changes[0].value is False
    assert r['state']['tool_orchestration']['sage_writes']==0
