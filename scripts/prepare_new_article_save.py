"""New candidate and real read/prepare only. Never approves or executes a write."""
import sys,json,secrets,copy
from pathlib import Path
from datetime import datetime,timezone
from lxml import etree
import httpx
import native_stack as stack
ROOT=stack.ROOT;sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_gateway import Gateway
from app.core.config import settings
gateway=Gateway('articles');desc=gateway.describe()
plan=ROOT/'runtime/new-article-save-plan.json'
if plan.exists():candidate=json.loads(plan.read_text())
else:
    candidate={'code':'TAI261019'+secrets.token_hex(3).upper(),'designation':'ARTICLE TEST CREATION API SAGE X3'}
    plan.write_text(json.dumps(candidate,indent=2),encoding='utf-8')
keys={'ITMREF':candidate['code']};before=gateway.read(keys)
assert before['exists'] is False,'Candidate already exists: stop; no automatic creation or code replacement'
reference=gateway.read({'ITMREF':'CPJ35'})
old=gateway.read({'ITMREF':'TSTAI2610174D94B4'})
base=json.loads((ROOT/'logs/step4-article-supplier-requested.json').read_text())['resources']['articles']['create_preparation']['request']
request=copy.deepcopy(base);request['keys']=keys
for field in request['fields']:
    if field['name']=='DES1AXX':field['value']=candidate['designation']
out={'checked_at':datetime.now(timezone.utc).isoformat(),'candidate':candidate,'before':before,
     'publication':{'folder':desc.get('FOL'),'solution':desc.get('SOL'),'object':desc.get('OBJ'),'pool':settings.sage_soap_pool,'create_published':any(n.get('ID')=='CREATE' for n in desc.iter('MET'))},
     'identity_is_admin':desc.get('USER','').casefold() in ['admin','administrator'],
     'reference_read':{'code':'CPJ35','status':reference['status'],'exists':reference['exists'],'fields':{k:v for k,v in reference.get('fields',{}).items() if k in ['ITM0_1.TCLCOD','ITM3_1.STU','ITM3_1.PUU','ITM3_1.SAU']}},
     'old_manual_article':{k:old[k] for k in ['keys','exists','status','messages']},
     'rights_verified':False,'conditional_rules_verified':False,'sage_writes':0,'request':request}
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=60) as client:
    security=client.get('/api/v1/sage/security');security.raise_for_status();out['security']=security.json()
    prepared=client.post('/api/v1/sage/articles/prepare',json=request);prepared.raise_for_status();op=prepared.json()
    out['preparation']={'http':prepared.status_code,**{k:op[k] for k in ['id','digest','status','object_xml','checks']}}
session,service=gateway.reader._client()
try:
    envelope=service._client.create_message(service,'save',callContext={'codeLang':'FRA','poolAlias':settings.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName='WS_ARTICLE',objectXml=op['object_xml'])
    envelope_path=ROOT/'examples/crud-api'/('save-'+candidate['code']+'-NOT-SENT.xml')
    envelope_path.write_bytes(etree.tostring(envelope,encoding='utf-8',xml_declaration=True,pretty_print=True))
    out['serialization']={'status':'PASS','sent':False,'path':str(envelope_path)}
    checks=[('host_diagnoses',"/api1/syracuse/collaboration/syracuse/hostDiagnoses?representation=hostDiagnoses.$query&where=hostName%20eq%20'sage'&count=5"),
            ('log_catalog','/api1/syracuse/collaboration/syracuse/logFiles?representation=logFile.$query&count=3'),
            ('itm_metadata',"/api1/x3/erp/V12_TEST/$prototypes('ITM.$details')"),
            ('category_metadata',"/api1/x3/erp/V12_TEST/$prototypes('ITGC.$details')")]
    out['administrative_reads']={}
    for name,path in checks:
        try:
            response=session.get(settings.sage_soap_base_url+path,timeout=12,allow_redirects=False)
            try:data=response.json()
            except ValueError:data={}
            out['administrative_reads'][name]={'http':response.status_code,'resource_count':len(data.get('$resources',[])),
                'does_not_establish_business_rights':True,'local_system_logs_read':False}
        except Exception as exc:out['administrative_reads'][name]={'error_type':type(exc).__name__,'local_system_logs_read':False}
finally:session.close()
with stack.connect() as conn:
    out['approvals']=conn.execute('SELECT count(*) FROM sage_ai.soap_operation_approvals').fetchone()[0]
    out['attempts']=conn.execute("SELECT count(*) FROM sage_ai.soap_operation_events WHERE event_type='write_attempt_claimed'").fetchone()[0]
assert out['approvals']==0 and out['attempts']==0
out['status']='PREPARED_SECURITY_BLOCKED' if not out['security']['ready'] else 'PREPARED_APPROVAL_REQUIRED'
(ROOT/'logs/step4-new-article-save.json').write_text(json.dumps(out,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False,default=str))
