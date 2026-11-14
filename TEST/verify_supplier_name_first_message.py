"""First message on fresh authenticated conversations; never approves a Sage write."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=40,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf'];results=[]
    for _ in range(2):
        response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json()
        response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':'le nom de fourniseur est ABDHADI TA','revision':session['revision']});response.raise_for_status();session=response.json()
        p=session['state']['partners'][0]
        assert p['nom']=='ABDHADI TA' and not p.get('approved') and not session['state'].get('_pending')
        assert not p.get('ice') and not p.get('ville')
        assert p['operation']['status']=='blocked'  # Existing F10031 is protected by duplicate checking.
        reply=next(m['content'] for m in reversed(session['messages']) if m['role']=='assistant')
        assert 'F10031' in reply
        results.append({'draft_id':p['id'],'name':p['nom'],'status':p['operation']['status'],'existing_code':'F10031'})
    assert results[0]['draft_id']!=results[1]['draft_id']
    report={'status':'PASS','real_backend':True,'two_fresh_conversations':results,'sage_writes':0,'no_approval_or_execution':True}
    Path(__file__).with_name('supplier-name-first-message-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))
