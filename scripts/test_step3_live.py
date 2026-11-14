"""Real authenticated read-only HTTP/SOAP proof. Never prints credentials or raw exceptions."""
import json
from pathlib import Path
import sys
from datetime import datetime,timezone
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import native_stack as stack
env=stack.environment()
results={}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90,trust_env=False) as client:
    headers={'X-Approval-Token':env['APPROVAL_TOKEN']}
    for name,path in [('getDescription','/api/v1/sage/description'),('read','/api/v1/sage/articles/CPJ35'),('query','/api/v1/sage/articles?limit=10')]:
        response=client.get(path,headers=headers)
        body=response.json()
        assert response.status_code==200,(name,response.status_code)
        assert body['read_only'] is True
        if name=='read': assert body['article']['ITMREF']=='CPJ35'
        if name=='query': assert 1<=body['count']<=10
        results[name]={'status':'PASS','http':response.status_code,'result':body}
    health={path:client.get(path).status_code for path in ['/health','/health/db','/health/ollama','/sage/']}
    assert all(code==200 for code in health.values()),health
    results['health']=health
    results['n8n_readiness']=client.get('http://127.0.0.1:5678/healthz/readiness').status_code
    assert results['n8n_readiness']==200
results.update(status='PASS',time_utc=datetime.now(timezone.utc).isoformat(),write_operations_sent=0)
(ROOT/'logs/step3-live-http-tests.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','operations':['getDescription','read','query'],'reference':'CPJ35','list_count':results['query']['result']['count'],'health':health,'n8n_readiness':results['n8n_readiness'],'write_operations_sent':0}))
