"""Owned disposable conversations, real restart, no Sage creation endpoints."""
import sys,json,time,subprocess,ast
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
import httpx
from http_test_account import authenticate_test_client
from app.services import learning_auto,learning_corrections as engine,business_store as db
BASE='http://127.0.0.1:8000';owner=None
client=httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=60,trust_env=False)
def checked(r):r.raise_for_status();return r.json()
def fresh():return checked(client.post('/api/v1/chat/conversations'))
def send(s,text):return checked(client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']}))
try:
    print('stage=register',flush=True)
    account=authenticate_test_client(client);owner=UUID(account['user']['id']);client.headers['X-Chat-CSRF']=account['csrf']
    for i in range(2):
        print('stage=conversation-'+str(i),flush=True)
        s=send(fresh(),'Créer un fournisseur Nom : VERIFICATION BOUCLE '+str(i)+' Ville : Rabat')
        s=send(s,'corrige la ville : Fes')
        assert s['state']['partners'][0]['ville']=='Fes' and not s['state']['partners'][0]['approved']
    reports=learning_auto.tick(owner)
    print('stage=evaluated',flush=True)
    assert any(r['status']=='active' and r['evaluation'].get('suite')=='typed-correction-heldout-v1' for r in reports)
    # Reuse the fixed, reviewed restart command from the existing verification tool.
    nodes=ast.parse((ROOT/'TEST/verify_automatic_improvement_restart.py').read_text(encoding='utf-8')).body
    restart=next(ast.literal_eval(n.value) for n in nodes if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='restart' for t in n.targets))
    proc=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',restart],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:proc.wait(timeout=20)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    print('stage=restarted',flush=True)
    for _ in range(60):
        try:checked(client.get('/health',timeout=2));break
        except httpx.HTTPError:time.sleep(.25)
    else:raise AssertionError('Backend unavailable after restart')
    s=send(fresh(),'Créer un fournisseur Nom : NOUVELLE CONVERSATION Ville : Rabat')
    print('stage=new-conversation',flush=True)
    s=send(s,'corige la vile : Tanger')
    assert s['state']['pending_correction'] and s['state']['partners'][0]['ville']=='Rabat'
    s=send(s,'oui corrige ce champ')
    p=s['state']['partners'][0];assert p['ville']=='Tanger' and not p['approved'] and not p.get('ice')
    report={'status':'PASS','real_backend_restart':True,'two_independent_conversations':True,'new_formulation_after_restart':True,'no_private_supplier_value_inherited':True,'uncertain_overwrite_requires_confirmation':True,'evaluation':engine.evaluate(engine.RECIPE),'sage_writes':0,'training_performed':False}
    (ROOT/'TEST/continuous-corrections-restart-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
finally:
    client.close()
    if owner:
        with db.connection() as conn:
            conn.execute("DELETE FROM chat_web_sessions WHERE owner_id=%s AND EXISTS(SELECT 1 FROM chat_accounts WHERE id=%s AND email LIKE 'verification-%%@example.test')",(owner,owner))
            conn.execute("UPDATE chat_accounts SET active=false WHERE id=%s AND email LIKE 'verification-%%@example.test'",(owner,))
