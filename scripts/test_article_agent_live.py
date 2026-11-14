"""Real local Ollama, PG, SQL SELECT and SOAP prepare only. Never approve or execute."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import httpx
import native_stack as stack
ROOT=stack.ROOT
out={'checked_at':datetime.now(timezone.utc).isoformat(),'sage_write_attempts':0,'checks':{}}
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=400) as c:
    r=c.post('/api/v1/article-agent/conversations',json={'message':'Crée un nouvel article Ciment CPJ35, catégorie NEG, unité SAC, pour le site 201.'})
    r.raise_for_status();value=r.json();identifier=value['id'];base='/api/v1/article-agent/conversations/'+identifier
    out['conversation_id']=identifier
    out['checks']['real_ollama_extraction']=value['draft']
    assert value['draft']['designation'] and value['draft']['categorie']=='NEG' and value['draft']['unite']=='SAC' and value['draft']['site']=='201', 'Unexpected grounded model extraction'
    # Human correction of the local draft only; no ERP data is changed.
    form={**value['draft'],'code_article':'AICHAT'+uuid4().hex[:10].upper(),'reference_article':'CPJ35'}
    r=c.patch(base,json={'revision':value['revision'],'draft':form});r.raise_for_status();value=r.json()
    r=c.post(base+'/validate',json={'revision':value['revision']});r.raise_for_status();value=r.json()
    out['checks']['sql_validation']=value['validation'];assert value['validated'], 'Real SQL validation failed'
    r=c.post(base+'/prepare',json={'revision':value['revision']});r.raise_for_status();value=r.json()
    assert value['operation'] and not value['security']['ready']
    out['checks']['soap_prepare']={'status':value['operation']['status'],'operation_id':value['operation']['id'],'blockers':value['operation']['checks']['security']['blockers'],'xml_prepared':bool(value['operation']['object_xml'])}
    assert value['operation']['checks']['save_sent'] is False
    assert c.get(base).json()['draft']==value['draft']
    assert any(row['id']==identifier for row in c.get('/api/v1/article-agent/conversations').json()['conversations'])
    out['checks']['postgres_history_persisted']=True
    out['checks']['creation_message']=value['creation_message']
    out['checks']['real_ollama_provenance']=c.get('/api/v1/ai/requests/'+identifier).json()['provenance']
out['status']='PASS'
(ROOT/'logs/article-agent-live-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':out['status'],'conversation_id':identifier,'sage_write_attempts':0,'checks':list(out['checks'])}))
