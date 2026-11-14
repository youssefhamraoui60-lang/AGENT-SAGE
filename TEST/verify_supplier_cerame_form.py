"""Real preparation of the reported message and its followup; no write approval."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import httpx
from http_test_account import authenticate_test_client
from test_supplier_cerame_form import MESSAGE,FOLLOWUP
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=45,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    r=client.post('/api/v1/chat/conversations');r.raise_for_status();s=r.json();identifiers=[];turns=[]
    for text,name in [(MESSAGE,'Super Cerame'),(FOLLOWUP,'Cerame')]:
        r=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});r.raise_for_status();s=r.json()
        p=s['state']['partners'][0];assert p['nom']==name and p['ice']=='000000505000042' and p['identifiant_fiscal']=='01067182'
        assert p['adresse']=='AIN SEBAA 20252-CASABLANCA-MAROC' and not p.get('approved') and not s['state'].get('_pending')
        reply=s['messages'][-1]['content'];assert 'Souhaitez-vous créer' not in reply
        identifiers.append(p['id']);turns.append({'name':p['nom'],'preparation_status':p['operation']['status']})
    assert len(set(identifiers))==1 and len(s['state']['partners'])==1
    report={'status':'PASS','real_backend':True,'reported_turns':turns,'initial_zeroes_preserved':True,'followup_updates_same_draft':True,'no_intent_question':True,'sage_writes':0}
    Path(__file__).with_name('supplier-cerame-form-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))
