"""Real chat + PostgreSQL + backend restart. Supplier preparation only, never approval."""
import sys,json,time,subprocess
from pathlib import Path
from uuid import UUID
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from http_test_account import authenticate_test_client
from app.services import learning_auto as auto,learning_training as training
BASE='http://127.0.0.1:8000'
client=httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=50,trust_env=False)
def checked(r):r.raise_for_status();return r.json()
def fresh():return checked(client.post('/api/v1/chat/conversations'))
def send(s,text):
    result=checked(client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']}))
    assert '_pending' not in result['state']
    return result
account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf'];owner=UUID(account['user']['id'])
stamp=str(int(time.time()))[-7:]
for index in range(2):
    s=fresh();s=send(s,'Créer le fournisseur BOUCLE '+stamp+str(index)+'\nAdresse : Berrechid')
    s=send(s,'Berrechid est la ville, pas l’adresse')
    p=s['state']['partners'][0];assert p['ville']=='Berrechid' and not p.get('adresse') and not p.get('approved')
evaluation=auto.evaluate(auto.RECIPE);activated=auto.tick(owner)
assert activated and activated[0]['status']=='active'
cookies=dict(client.cookies);csrf=client.headers['X-Chat-CSRF'];client.close()
restart=r"""
$targets=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object {$_.CommandLine -like '*C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe*' -and $_.CommandLine -like '*uvicorn app.main:app --host 127.0.0.1 --port 8000*'}
foreach($proc in $targets){Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue}
Start-Process -FilePath 'C:\AGENT-SAGE-X3\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\AGENT-SAGE-X3\backend' -WindowStyle Hidden -RedirectStandardOutput 'C:\AGENT-SAGE-X3\TEST\backend-reload-stdout.log' -RedirectStandardError 'C:\AGENT-SAGE-X3\TEST\backend-reload-stderr.log'
"""
process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',restart],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:process.wait(timeout=15)
except subprocess.TimeoutExpired:process.kill();process.wait()
client=httpx.Client(base_url=BASE,cookies=cookies,headers={'Origin':BASE,'X-Chat-CSRF':csrf},timeout=50,trust_env=False)
for _ in range(60):
    try:checked(client.get('/health',timeout=2));break
    except httpx.HTTPError:time.sleep(.25)
else:raise RuntimeError('Backend restart failed')
s=fresh();s=send(s,'Créer le fournisseur NOUVEL ESSAI '+stamp)
assert not s['state']['partners'][0].get('ville') and not s['state']['partners'][0].get('ice')
s=send(s,'Rabat correspond à la ville')
assert s['state']['partners'][0]['ville']=='Rabat' and s['state']['applied_learning_method']==activated[0]['method_id']
assert not s['state']['partners'][0].get('approved')
s=send(s,'Quelles méthodes as-tu apprises ?');s=send(s,'Désactive la méthode 1')
assert 'désactivée' in s['messages'][-1]['content']
dataset=training.export_dataset(owner,force=True)
report={'status':'PASS','real_backend_restart':True,'chat_corrections_in_two_conversations':True,'periodic_worker_logic_triggered_once':True,
 'new_conversation_new_value_after_restart':True,'no_supplier_value_inherited':True,'rollback_by_chat':True,'evaluation':evaluation,
 'measurement_scope':'Bounded dialogue interpreter on independent synthetic cases, not overall Qwen accuracy.',
 'anonymized_dataset_examples':dataset['manifest']['example_count'],'training_performed':False,'sage_writes':0}
(ROOT/'TEST/automatic-improvement-restart-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));client.close()
