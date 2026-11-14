"""Replay the reported dialogue against localhost; no approve/execute request."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=45,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json();turns=[]
    for text in ['BARI Ne ajouter wahade foourniseur','je dire créer un fourniseur mais on darija','le darija pas le nom de fourniseur sample darija','le nom de fourniseur est ABDHADI TA']:
        response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':text,'revision':session['revision']});response.raise_for_status();session=response.json()
        assert not session['state'].get('_pending')
        p=session['state']['partners'][0];assert not p.get('approved')
        if text.startswith('le nom de'):assert p['nom']=='ABDHADI TA'
        else:assert not p.get('nom')
        turns.append({'input':text,'reply':next(m['content'] for m in reversed(session['messages']) if m['role']=='assistant'),'name':p.get('nom')})
    report={'status':'PASS','real_backend':True,'reported_turns':turns,'final_preparation_status':(p.get('operation') or {}).get('status'),'sage_writes':0,'no_approve_or_execute_called':True}
    Path(__file__).with_name('darija-discourse-http-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
