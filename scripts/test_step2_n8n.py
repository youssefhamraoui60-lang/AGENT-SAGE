"""Create a NEW step-2 demo; never update or delete step-1 workflows."""
import json
from pathlib import Path
import secrets
import time
import httpx
import native_stack as stack

ROOT=stack.ROOT

def main():
    values=stack.environment()
    path='agent-sage-step2-'+secrets.token_hex(6)
    workflow={'name':'ETAPE 2 - Analyse locale et attente de validation','settings':{'executionOrder':'v1'},
        'nodes':[
            {'id':'entry','name':'Demande de test','type':'n8n-nodes-base.webhook','typeVersion':2,'position':[0,0],
                'webhookId':secrets.token_hex(16),'parameters':{'httpMethod':'POST','path':path,'responseMode':'responseNode','options':{}}},
            {'id':'analyze','name':'Analyse et controles FastAPI','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[240,0],
                'parameters':{'method':'POST','url':'http://127.0.0.1:8000/api/v1/ai/analyze','sendBody':True,
                    'specifyBody':'json','jsonBody':'={{ JSON.stringify({demande: $json.body.demande}) }}','options':{'timeout':420000}}},
            {'id':'read','name':'Relire la demande PostgreSQL','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[480,0],
                'parameters':{'method':'GET','url':"={{ 'http://127.0.0.1:8000/api/v1/ai/requests/' + $json.id }}",'options':{'timeout':15000}}},
            {'id':'return','name':'Resultat en attente de validation','type':'n8n-nodes-base.respondToWebhook','typeVersion':1.4,'position':[720,0],
                'parameters':{'respondWith':'json','responseBody':'={{ $json }}','options':{}}}
        ],'connections':{
            'Demande de test':{'main':[[{'node':'Analyse et controles FastAPI','type':'main','index':0}]]},
            'Analyse et controles FastAPI':{'main':[[{'node':'Relire la demande PostgreSQL','type':'main','index':0}]]},
            'Relire la demande PostgreSQL':{'main':[[{'node':'Resultat en attente de validation','type':'main','index':0}]]}}}
    with httpx.Client(base_url='http://127.0.0.1:5678',timeout=30) as client:
        login=client.post('/rest/login',json={'emailOrLdapLoginId':values['N8N_OWNER_EMAIL'],'password':values['N8N_OWNER_PASSWORD']})
        if login.status_code!=200: raise RuntimeError('Existing n8n owner login failed; no account reset')
        response=client.post('/rest/workflows',json=workflow);response.raise_for_status()
        data=response.json()['data'];workflow_id=data['id']
        (ROOT/'workflows/demo-step2-business.json').write_text(json.dumps({**workflow,'id':workflow_id,'active':False},ensure_ascii=False,indent=2),encoding='utf-8')
        active=client.post(f'/rest/workflows/{workflow_id}/activate',json={'versionId':data['versionId']});active.raise_for_status()
        try:
            for _ in range(60):
                with stack.connect('n8n',admin=True) as conn:
                    registered=conn.execute('SELECT count(*) FROM webhook_entity WHERE "workflowId"=%s',(workflow_id,)).fetchone()[0]
                if registered: break
                time.sleep(0.5)
            else: raise RuntimeError('New step2 webhook registration timeout')
            start=time.perf_counter()
            result=client.post('/webhook/'+path,json={'demande':
                'Créer les articles Câble souple 4x50 mm RVK NOIR, unité, FG, fournisseur SOTAMO et Cosse à sertir SC 70-10, unité, FG, fournisseur SOTAMO.'},timeout=420)
            result.raise_for_status();body=result.json()
            assert body['statut']=='pending_approval' and len(body['proposition']['articles'])==2
            assert not body['execution_sage_autorisee']
            assert body['historique'][-1]['event_type']=='analyzed'
            proof={'status':'PASS','workflow_id':workflow_id,'http':result.status_code,'request_id':body['id'],
                'article_count':len(body['proposition']['articles']),'request_status':body['statut'],
                'seconds':round(time.perf_counter()-start,3),'execution_sage_autorisee':False,'stage1_workflows_untouched':True}
        finally:
            response=client.post(f'/rest/workflows/{workflow_id}/deactivate',json={});response.raise_for_status()
        proof['workflow_final']='inactive'
        (ROOT/'logs/step2-n8n-tests.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(proof,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        (ROOT/'logs/step2-n8n-tests.json').write_text(json.dumps({'status':'FAIL','error':str(exc)},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
