"""Create a synthetic local n8n owner/demo through its HTTP API; verify real webhook + persistence."""
import json
from pathlib import Path
import secrets
import time
import httpx
import native_stack as stack

ROOT=stack.ROOT
BASE='http://127.0.0.1:5678'

def wait_ready():
    with httpx.Client(timeout=5) as client:
        for _ in range(90):
            try:
                if client.get(BASE+'/healthz/readiness').status_code==200: return
            except httpx.HTTPError: pass
            time.sleep(2)
    raise RuntimeError('n8n readiness timeout')

def main():
    wait_ready()
    env=stack.environment()
    with httpx.Client(base_url=BASE,timeout=30,headers={'Origin':BASE}) as client:
        r=client.get('/rest/settings')
        r.raise_for_status()
        settings=r.json()['data']
        setup=settings.get('userManagement',{}).get('showSetupOnFirstLoad',False)
        if setup:
            if 'N8N_OWNER_PASSWORD' not in env:
                password='REDACTED_CONFIGURE_LOCALLY'+secrets.token_urlsafe(24)
                with (ROOT/'.env').open('a',encoding='utf-8') as handle:
                    handle.write('\nN8N_OWNER_PASSWORD='+password+'\nN8N_OWNER_EMAIL=admin@localhost.invalid\n')
                env=stack.environment()
            r=client.post('/rest/owner/setup',json={'email':env['N8N_OWNER_EMAIL'],'firstName':'Admin',
                'lastName':'Local Etape1','password':env['N8N_OWNER_PASSWORD']})
            if r.status_code!=200: raise RuntimeError(f'Owner setup HTTP {r.status_code}; existing accounts unchanged')
        else:
            if 'N8N_OWNER_PASSWORD' not in env:
                raise RuntimeError('Existing n8n owner detected; no reset attempted. Local credentials required.')
            r=client.post('/rest/login',json={'emailOrLdapLoginId':env['N8N_OWNER_EMAIL'],'password':env['N8N_OWNER_PASSWORD']})
            if r.status_code!=200: raise RuntimeError(f'Owner login HTTP {r.status_code}')
        workflow=json.loads((ROOT/'workflows/demo-extraction.json').read_text(encoding='utf-8-sig'))
        workflow.pop('active',None)
        workflow['name']='TEST LOCAL ETAPE 1 - Extraction synthetique'
        for node in workflow['nodes']:
            if node['id']=='backend': node['parameters']['url']='http://127.0.0.1:8000/api/ai/extract'
            if node['id']=='webhook':
                node['parameters']['path']='agent-sage-etape1-'+secrets.token_hex(6)
                node['webhookId']=secrets.token_hex(16)
                path=node['parameters']['path']
        created=client.post('/rest/workflows',json=workflow)
        created.raise_for_status()
        data=created.json()['data']
        workflow_id=data['id']
        (ROOT/'workflows/demo-extraction-native.json').write_text(json.dumps({**workflow,'id':workflow_id,'active':False},ensure_ascii=False,indent=2),encoding='utf-8')
        activated=client.post(f'/rest/workflows/{workflow_id}/activate',json={'versionId':data['versionId']})
        if activated.status_code>=400:
            raise RuntimeError(f'Activate workflow HTTP {activated.status_code}: {activated.text[:500]}')
        # Publication is asynchronous: wait for actual webhook registration,
        # rather than treating the activation response as readiness.
        for _ in range(60):
            with stack.connect('n8n',admin=True) as conn:
                registered=conn.execute('SELECT count(*) FROM webhook_entity WHERE "workflowId"=%s',(workflow_id,)).fetchone()[0]
            if registered: break
            time.sleep(0.5)
        else: raise RuntimeError('Webhook not registered after publication')
        start=time.perf_counter()
        try:
            response=client.post('/webhook/'+path,json={'demande':'Créer POLYSTER 3 CM, unité M3, catégorie MARCH, fournisseur ISONIMA.'},timeout=240)
            response.raise_for_status()
            result=response.json()
            for key,value in {'designation':'POLYSTER 3 CM','unite':'M3','categorie':'MARCH','fournisseur':'ISONIMA'}.items():
                assert result.get(key)==value,(key,result)
        finally:
            deactivated=client.post(f'/rest/workflows/{workflow_id}/deactivate',json={})
            deactivated.raise_for_status()
        elapsed=round(time.perf_counter()-start,3)
        before=client.get(f'/rest/workflows/{workflow_id}')
        before.raise_for_status()
        stack.stop_n8n()
        stack.start_n8n()
        wait_ready()
        after=client.get(f'/rest/workflows/{workflow_id}')
        after.raise_for_status()
        after_data=after.json()['data']
        assert after_data['id']==workflow_id and after_data['name']==workflow['name']
        assert len(after_data['nodes'])==len(workflow['nodes'])
        assert not after_data.get('active',False),'Demo must remain inactive'
        proof={'status':'PASS','workflow_id':workflow_id,'webhook_http':response.status_code,'json':result,
            'seconds':elapsed,'persistance_n8n_apres_restart':'PASS','workflow_final':'inactive',
            'owner_email':'admin@localhost.invalid','password_location':'.env (not reported)'}
        (ROOT/'logs/native-workflow-tests.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(proof,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        proof={'status':'FAIL','error':str(exc)}
        (ROOT/'logs/native-workflow-tests.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
