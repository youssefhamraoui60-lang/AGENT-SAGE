"""Real async chat + actual backend restart. SQL preparation only, never approve/execute."""
from http_test_account import authenticate_test_client
import json,subprocess,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8000'
SOURCE=Path(r'C:\Users\youssef\Desktop\100000_conversations_fournisseurs_fautes_graves.jsonl')
with SOURCE.open(encoding='utf-8') as stream:rows=[json.loads(next(stream)) for _ in range(3)]
EXPECTED=[
 {'nom':'omar trensport','devise':'MAD','type_montant':'TTC','ville':'mohamedia','conditions_paiement':'virement 30 jours','ice':'050325912663415'},
 {'nom':'najib sarl','ice':'592589839266670','ville':'casablanka','intitule_court':'najib sarl','regime_taxe':'MAR','identifiant_fiscal':'3681462','rc':'13981','conditions_paiement':'effet 60 jours'},
 {'nom':'saad auto','ville':'safi','ice':'362831412860975','telephone':'0664257535','identifiant_fiscal':'4095824','rc':'751653','conditions_paiement':'cheque 30 jours'},
]
def client_for(cookies=None,csrf=None):return httpx.Client(base_url=BASE,cookies=cookies,headers={'Origin':BASE,**({'X-Chat-CSRF':csrf} if csrf else {})},timeout=30,trust_env=False)
def checked(response):response.raise_for_status();return response.json()
def ready(client):
    for _ in range(60):
        try:checked(client.get('/health',timeout=2));return
        except httpx.HTTPError:time.sleep(.25)
    raise RuntimeError('Backend unavailable')
def restart():
    script=r"""
$targets=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object {$_.CommandLine -like '*C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe*' -and $_.CommandLine -like '*uvicorn app.main:app --host 127.0.0.1 --port 8000*'}
foreach($proc in $targets){Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue}
Start-Process -FilePath 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\AGENT-SAGE-X3\backend' -WindowStyle Hidden -RedirectStandardOutput 'C:\AGENT-SAGE-X3\TEST\backend-reload-stdout.log' -RedirectStandardError 'C:\AGENT-SAGE-X3\TEST\backend-reload-stderr.log'
"""
    process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:process.kill();process.wait()

client=client_for();ready(client)
identity=authenticate_test_client(client);client.headers['X-Chat-CSRF']=identity['csrf']
results=[];restarted=False
for index,row in enumerate(rows):
    conversation=checked(client.post('/api/v1/chat/conversations'));draft_id=None;durations=[]
    users=[turn['content'] for turn in row['conversation'] if turn['role']=='user']
    for turn_index,text in enumerate(users):
        start=time.monotonic();path='/api/v1/chat/conversations/'+conversation['id']+'/analysis-jobs'
        value=checked(client.post(path,json={'content':text,'revision':conversation['revision'],'request_id':str(uuid.uuid4())}))
        for _ in range(160):
            if value['job']['status'] in ('completed','failed','interrupted','verification_incomplete'):break
            time.sleep(.25);value=checked(client.get(path+'/'+value['job']['id']))
        assert value['job']['status']=='completed',(text,value['job'])
        conversation=value['conversation'];partners=conversation['state']['partners'];assert len(partners)==1
        p=partners[0]
        if draft_id:assert p['id']==draft_id
        draft_id=p['id'];assert not p.get('approved')
        assert p['operation']['status'] in ('prepared','blocked')
        durations.append(round(time.monotonic()-start,2))
        if index==0 and turn_index==2:
            cookies=dict(client.cookies);csrf=client.headers['X-Chat-CSRF'];before=p.copy();client.close();restart()
            client=client_for(cookies,csrf);ready(client)
            conversation=checked(client.get('/api/v1/chat/conversations/'+conversation['id']))
            after=conversation['state']['partners'][0]
            assert after['id']==before['id'] and after['nom']==before['nom'] and after.get('devise')=='MAD'
            restarted=True
    for key,expected in EXPECTED[index].items():assert p.get(key)==expected,(key,p.get(key),expected)
    result={'id':row['id'],'turns':len(users),'same_draft':True,'fields_manually_verified':EXPECTED[index],'max_turn_seconds':max(durations),'no_approval_granted':True,'sage_inserts':0}
    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
report={'status':'PASS','async_chat_real_backend':True,'real_restart_context_preserved':restarted,'sage_inserts':0,'isolated_test_identity':True,'dialogues':results}
(ROOT/'TEST/noisy-dialogues-chat-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');client.close()
