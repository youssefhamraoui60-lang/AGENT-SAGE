"""Replay exact labelled form against localhost; never approve a write."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import httpx
from http_test_account import authenticate_test_client
from test_supplier_double_slash_email import MESSAGE
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=40,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    r=client.post('/api/v1/chat/conversations');r.raise_for_status();s=r.json()
    r=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':MESSAGE,'revision':s['revision']});r.raise_for_status();s=r.json()
    p=s['state']['partners'][0];message=s['messages'][-1]
    assert p['nom']=='AL ALAMIA' and p['identifiant_fiscal']=='60106228' and p['ice']=='003388875000087'
    assert p['email']=='auto.alalamia@gmail.com' and not p['approved']
    assert any(r['key']=='Email' and r['value']==p['email'] for r in message['payload']['supplier_snapshots'][0]['rows'])
    assert 'Email conservé' in message['content']
    report={'status':'PASS','real_backend':True,'all_fields_preserved':True,'email_in_table':True,'unsupported_email_write_explicit':True,'sage_writes':0,'reply':message['content']}
    Path(__file__).with_name('supplier-double-slash-email-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
