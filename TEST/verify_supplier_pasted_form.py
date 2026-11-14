"""Real preparation of the reported supplier form. No write authorization."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import httpx
from http_test_account import authenticate_test_client
from test_supplier_pasted_form import MESSAGE,ADDRESS
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=50,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    r=client.post('/api/v1/chat/conversations');r.raise_for_status();s=r.json()
    r=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':MESSAGE,'revision':s['revision']});r.raise_for_status();s=r.json()
    p=s['state']['partners'][0]
    assert p['nom']=='SOS MECANIQUE HYDRAULIQUE' and p['adresse']==ADDRESS and not p.get('approved')
    assert p['ice']=='001538584000034' and p['identifiant_fiscal']=='1921340'
    reply=s['messages'][-1]['content'];assert 'Souhaitez-vous créer' not in reply
    report={'status':'PASS','real_backend':True,'correct_fields':True,'address_preserved':True,'preparation_status':p['operation']['status'],'reply':reply,'sage_writes':0}
    Path(__file__).with_name('supplier-pasted-form-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
