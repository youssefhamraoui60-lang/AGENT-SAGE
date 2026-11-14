"""Read-only Sage checks plus negative local API lock checks. Never grants approval."""
import json,socket,sys
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import httpx
from app.services.sage_gateway import Gateway
from app.services.sage_crud import description_hash
import native_stack as stack

result={'checked_at':datetime.now(timezone.utc).isoformat(),'mode':'READ_ONLY_AND_LOCK_REJECTION','transport':{},'resources':{},'sage_writes':0}
for name,port in [('SSH',22),('HTTPS',443),('HTTPS-candidate',8443),('SOAP-current',8124)]:
    try:
        with socket.create_connection(('192.168.9.200',port),timeout=2):tcp=True
    except OSError:tcp=False
    result['transport'][name]={'host':'192.168.9.200','port':port,'tcp':tcp}
try:result['transport']['dns_sage']=sorted({item[4][0] for item in socket.getaddrinfo('sage',None)})
except OSError:result['transport']['dns_sage']=[]
live=json.loads((ROOT/'logs/step4-crud-live-tests.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=60) as client:
    result['security']=client.get('/api/v1/sage/security').json()
    assert result['security']['ready'] is False,'Refusing negative route checks when writes are enabled'
    for resource,r in live['resources'].items():
        gateway=Gateway(resource);desc=gateway.describe()
        keys=r['create_preparation']['request']['keys']
        existing=gateway.read(keys,describe=False)
        methods=sorted({n.get('ID') for n in desc.iter('MET') if n.get('ID')})
        entry={'publication':gateway.spec['publication'],'object':desc.get('OBJ'),'folder':desc.get('FOL'),'solution':desc.get('SOL'),
               'description_sha256':description_hash(desc),'publication_methods':methods,'business_rights_verified':False,
               'pool_x3_user_is_admin':desc.get('USER','').casefold() in ['admin','administrator'],
               'keys':keys,'exists':existing['exists'],'read_status':existing['status'],'read_messages':existing.get('messages',[])}
        # Guard rechecked immediately before local negative tests. No real approval ID/token is supplied.
        assert client.get('/api/v1/sage/security').json()['ready'] is False
        body={'operation_id':str(uuid4()),'approval_token':'INVALID-NOT-AN-APPROVAL'}
        entry['create_without_approval_http']=client.post('/api/v1/sage/'+resource,json=body).status_code
        entry['update_without_approval_http']=client.patch('/api/v1/sage/'+resource+'/'+'/'.join(keys[k] for k in gateway.spec['keys']),json=body).status_code
        assert entry['create_without_approval_http']==423 and entry['update_without_approval_http']==423
        result['resources'][resource]=entry
with stack.connect() as conn:
    result['approvals']=conn.execute('SELECT count(*) FROM sage_ai.soap_operation_approvals').fetchone()[0]
    result['write_attempt_claimed']=conn.execute("SELECT count(*) FROM sage_ai.soap_operation_events WHERE event_type='write_attempt_claimed'").fetchone()[0]
assert result['approvals']==0 and result['write_attempt_claimed']==0
result['itf_dependency']={'article_exists':result['resources']['articles']['exists'],'article_site_exists':result['resources']['article-sites']['exists'],
                         'creation_blocked_until_parent_exists':True,'recheck_after_itm_required':True,'auto_creation_possible_requires_read':True}
result['status']='CHECKS_COMPLETED_WRITES_BLOCKED'
(ROOT/'logs/step4-crud-prerequisites.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=False))
