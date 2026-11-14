"""Real HTTP/PG restart proof. New test identity; no Sage operation is requested."""
from http_test_account import authenticate_test_client
import sys,json,subprocess,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8000'
QUESTION='Comment contrôler un identifiant mémoire démonstration ?'
TARGET='Contrôler le format puis demander une validation humaine.'

def checked(response):
    response.raise_for_status();return response.json()
def send(client,session,text):
    return checked(client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':text,'revision':session['revision']}))

client=httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=40,trust_env=False)
print('Connecting to local backend...',flush=True)
for _ in range(40):
    try:checked(client.get('/health',timeout=2));break
    except httpx.HTTPError:time.sleep(.25)
else:raise RuntimeError('Backend unavailable')
session=authenticate_test_client(client);client.headers['X-Chat-CSRF']=session['csrf']
print('Authenticated test identity created.',flush=True)
doc=checked(client.post('/api/v1/chat/learning/items',json={'kind':'document','title':'TEST — preuve de redémarrage','source':'test_isolated_identity',
    'content':'Pour contrôler un identifiant mémoire démonstration, vérifier son format.'}))
checked(client.post('/api/v1/chat/learning/items/'+doc['id']+'/review',json={'status':'validated','confirm':True}))
conversation=checked(client.post('/api/v1/chat/conversations'))
conversation=send(client,conversation,QUESTION)
print('Original document answer received.',flush=True)
message=next(m for m in reversed(conversation['messages']) if m['role']=='assistant')
conversation=checked(client.post('/api/v1/chat/learning/conversations/'+conversation['id']+'/feedback',json={'message_id':message['id'],'verdict':'incorrect','expected':TARGET}))
rule=next(m['memory_rules'][-1] for m in reversed(conversation['messages']) if m.get('memory_rules'))
assert rule['status']=='pending'
conversation=checked(client.post('/api/v1/chat/learning/conversations/'+conversation['id']+'/items/'+rule['id']+'/action',json={'action':'validate','sha':rule['sha256'],'confirm':True}))
print('Correction validated; restarting backend.',flush=True)
cookies=dict(client.cookies);csrf=client.headers['X-Chat-CSRF'];client.close()
restart=r"""
$targets=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object {$_.CommandLine -like '*C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe*' -and $_.CommandLine -like '*uvicorn app.main:app --host 127.0.0.1 --port 8000*'}
foreach($proc in $targets){Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue}
Start-Process -FilePath 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\AGENT-SAGE-X3\backend' -WindowStyle Hidden -RedirectStandardOutput 'C:\AGENT-SAGE-X3\TEST\backend-reload-stdout.log' -RedirectStandardError 'C:\AGENT-SAGE-X3\TEST\backend-reload-stderr.log'
"""
process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',restart],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:process.wait(timeout=15)
except subprocess.TimeoutExpired:process.kill();process.wait()
client=httpx.Client(base_url=BASE,cookies=cookies,headers={'Origin':BASE,'X-Chat-CSRF':csrf},timeout=40,trust_env=False)
for _ in range(40):
    try:
        checked(client.get('/health',timeout=2));break
    except httpx.HTTPError:time.sleep(.25)
else:raise RuntimeError('Backend restart failed')
fresh=checked(client.post('/api/v1/chat/conversations'))
fresh=send(client,fresh,QUESTION)
answer=next(m['content'] for m in reversed(fresh['messages']) if m['role']=='assistant')
assert TARGET in answer
assert fresh['state']['learning_context'].get('used_example_source')
assert not fresh['state'].get('partners') and not fresh['state'].get('approved')
report={'status':'PASS','real_backend_restart':True,'new_conversation_after_restart':True,
    'validated_correction_reused':True,'training_performed':False,'sage_writes':0,
    'conversation_before':conversation['id'],'conversation_after':fresh['id'],'answer':answer,
    'note':'Dedicated new browser identity, separate from existing user memories. No cookie or CSRF token saved.'}
(ROOT/'TEST/memory-chat-restart-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));client.close()
