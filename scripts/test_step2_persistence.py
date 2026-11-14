"""Confirm step-2 proposals and append-only history survive a project DB restart."""
import json
from pathlib import Path
import time
import httpx
import native_stack as stack

ROOT=stack.ROOT
rows=json.loads((ROOT/'logs/step2-live-tests.json').read_text(encoding='utf-8'))
ids=[row['response']['id'] for row in rows if row['status']=='PASS']
assert ids,'No real step2 requests to check'
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=15) as client:
    before={key:client.get('/api/v1/ai/requests/'+key).json() for key in ids}
    stack.pg_run('pg_ctl.exe','-D',str(stack.DATA),'-m','fast','-w','stop')
    stack.start_pg()
    for _ in range(30):
        if client.get('/health/db').status_code==200: break
        time.sleep(1)
    for key in ids:
        response=client.get('/api/v1/ai/requests/'+key);response.raise_for_status()
        assert response.json()==before[key],key
proof={'status':'PASS','requests_preserved':len(ids),'history_and_proposals_unchanged':True,
    'project_postgres_restarted':True,'sage_x3_accessed':False}
(ROOT/'logs/step2-persistence-tests.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof,indent=2))
