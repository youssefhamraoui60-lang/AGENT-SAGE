"""Real mixed-request preparation; no approve/execute API is ever called."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client
BASE='http://127.0.0.1:8000'
message='Bonjour, Merci de créer le fournisseur : VM HOLZ TIMBER et articles : madriers 3m et madriers 4m. Cdlt'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=180,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json()
    response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':message,'revision':session['revision']});response.raise_for_status();session=response.json()
    state=session['state'];assert not state.get('_pending')
    assert state['partners'][0]['nom']=='VM HOLZ TIMBER'
    assert [a['designation'] for a in state['articles']]==['madriers 3m','madriers 4m']
    assert not any(p.get('approved') for p in state['partners']+state['articles'])
    report={'status':'PASS','real_backend':True,'supplier':state['partners'][0]['nom'],'articles':[a['designation'] for a in state['articles']],
        'job_status':state['analysis_job']['status'],'no_approval_or_execution':True,'sage_writes':0}
    Path(__file__).with_name('mixed-supplier-articles-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))
