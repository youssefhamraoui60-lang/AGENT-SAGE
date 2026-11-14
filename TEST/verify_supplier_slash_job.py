"""Exercise the same asynchronous analysis endpoint as the chat UI; no write action."""
from http_test_account import authenticate_test_client
import json,time,uuid
from pathlib import Path
import httpx
from test_supplier_slash import MESSAGE
BASE='http://127.0.0.1:8000'
with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=30,trust_env=False) as client:
    def checked(response):response.raise_for_status();return response.json()
    for _ in range(40):
        try:checked(client.get('/health',timeout=2));break
        except httpx.HTTPError:time.sleep(.25)
    identity=authenticate_test_client(client);client.headers['X-Chat-CSRF']=identity['csrf']
    conversation=checked(client.post('/api/v1/chat/conversations'))
    path='/api/v1/chat/conversations/'+conversation['id']+'/analysis-jobs'
    result=checked(client.post(path,json={'content':MESSAGE,'revision':conversation['revision'],'request_id':str(uuid.uuid4())}))
    for _ in range(120):
        if result['job']['status'] in ('completed','failed','interrupted','verification_incomplete'):break
        time.sleep(.25);result=checked(client.get(path+'/'+result['job']['id']))
    assert result['job']['status']=='completed',result['job']
    p=result['conversation']['state']['partners'][0]
    assert p['nom']=='MARRAKECH HYDRAULIQUE 0002'
    assert p['operation']['status']=='prepared' and not p.get('approved')
    assert p['operation']['parameters']['Telephone']=='0610015838'
    report={'status':'PASS','async_chat_job':True,'sage_inserts':0,'confirmation_required':True,'name':p['nom'],'parameters':p['operation']['parameters'],'analysis_status':result['job']['status']}
    Path(__file__).with_name('verification-slash-job.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
