"""Replay exact malformed fiscal input; no approve/execute requests."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import httpx
from http_test_account import authenticate_test_client
from test_supplier_fiscal_slashes import MESSAGE
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=40,trust_env=False) as client:
    for _ in range(30):
        try:client.get('/health').raise_for_status();break
        except httpx.HTTPError:time.sleep(.2)
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    r=client.post('/api/v1/chat/conversations');r.raise_for_status();session=r.json()
    r=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':MESSAGE,'revision':session['revision']});r.raise_for_status();session=r.json()
    p=session['state']['partners'][0];reply=session['messages'][-1]['content']
    assert p['ice']=='00295940100040' and p['identifiant_fiscal']=='50647721'
    assert p['adresse']=='bouskoura victoria oulad saleh bloc 24'
    assert not p['approved'] and p['operation']['status']=='blocked' and '14 chiffres' in reply
    report={'status':'PASS','real_backend':True,'raw_ice_preserved':True,'fiscal_id_separated_from_address':True,'invalid_ice_blocks_creation':True,'reply':reply,'sage_writes':0}
    Path(__file__).with_name('supplier-fiscal-slashes-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
