"""Prepare three published services and a blocked client plan. Never approves or writes Sage."""
import json,sys,copy
from datetime import datetime,timezone
from pathlib import Path
from lxml import etree
import httpx
import native_stack as stack
ROOT=stack.ROOT;sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_gateway import Gateway
from app.services.sage_soap import SageReader
from app.core.config import settings
sql=json.loads((ROOT/'logs/four-creation-sql-discovery.json').read_text(encoding='utf-8-sig'))
soap=json.loads((ROOT/'logs/four-creation-soap-discovery.json').read_text())
assert sql['status']=='PASS' and all(not rows for rows in sql['absence'].values())
category=sql['article_category'][0];supplier=sql['supplier_categories'][0];customer=sql['customer_categories'][0];site=sql['site'][0]['FCY_0'].strip()
def field(group,name,value):return {'group':group,'name':name,'value':str(value).strip()}
article=[field('ITM0_1','TCLCOD',category['TCLCOD_0']),field('ITM0_1','DES1AXX','ARTICLE TEST CREATION API SAGE X3'),
         field('ITM2_1','STOMGTCOD',category['STOMGTCOD_0']),field('ITM2_3','LOTMGTCOD',category['LOTMGTCOD_0'])]
article += [field('ITM3_1',name,category[name+'_0']) for name in ['STU','PUU','SAU']]
article += [field('ITM3_1',name,format(category[name+'_0'],'.7f').rstrip('0').rstrip('.')) for name in ['PUUSTUCOE','SAUSTUCOE']]
supfields=[field('BPS0_1','BSGCOD',supplier['BSGCOD_0']),{'group':'BPRS_1','name':'BPRNAM','value':['FOURNISSEUR TEST IA','']},field('BPRS_1','BPRSHO','F_AITEST01')]
supfields += [field('BPRS_1',name,supplier[name+'_0']) for name in ['CRY','LAN','CUR']]
# Only add category defaults where a unique published scalar input is identified.
for name in ['ACCCOD','VACBPR','PTE']:
    matches=[f for f in soap['WS_FOURNIS']['input_fields'] if f['NAM']==name and f.get('DIM','1')=='1']
    if len(matches)==1 and str(supplier[name+'_0']).strip():supfields.append(field(matches[0]['group'],name,supplier[name+'_0']))
requests={
    'articles':{'action':'create','keys':{'ITMREF':'AITEST001'},'fields':article},
    'article-sites':{'action':'create','keys':{'ITMREF':'AITEST001','STOFCY':site},'fields':[field('ITF1_2','ABCCLS',category['ABCCLS_0'])]},
    'suppliers':{'action':'create','keys':{'BPSNUM':'F_AITEST01'},'fields':supfields}}
out={'checked_at':datetime.now(timezone.utc).isoformat(),'sql_mode':'TMS_OPTIONAL_ENCRYPTION_AUTHORIZED','sage_writes':0,'resources':{},'negative_tests':{},'supplier_customer_names_status':'FICTITIOUS_NAMES_CHOSEN_BY_AGENT_AT_USER_REQUEST_NOT_WRITE_AUTHORIZATION'}
folder=ROOT/'examples/four-creation-tests';folder.mkdir(exist_ok=True)
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=60) as client:
    security=client.get('/api/v1/sage/security');security.raise_for_status();out['security']=security.json()
    for resource,body in requests.items():
        response=client.post('/api/v1/sage/'+resource+'/prepare',json=body);response.raise_for_status();op=response.json()
        gateway=Gateway(resource);session,service=gateway.reader._client()
        try:
            envelope=service._client.create_message(service,'save',callContext={'codeLang':'FRA','poolAlias':settings.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName=gateway.spec['publication'],objectXml=op['object_xml'])
            file=folder/(resource+'-NOT-SENT.xml');file.write_bytes(etree.tostring(envelope,encoding='utf-8',pretty_print=True))
        finally:session.close()
        out['resources'][resource]={'request':body,'publication':gateway.spec['publication'],'prepare_http':response.status_code,'operation':op,'xml_file':str(file),'executed':False}
    # Read-only business rejection: duplicate preparation does not execute save.
    duplicate=copy.deepcopy(requests['articles']);duplicate['keys']['ITMREF']='CPJ35'
    dup=client.post('/api/v1/sage/articles/prepare',json=duplicate);dup.raise_for_status()
    out['negative_tests']['existing_article_prepare']={'http':dup.status_code,'status':dup.json()['status'],'blockers':dup.json()['checks']['blockers']}
    assert 'DUPLICATE_EXISTS' in dup.json()['checks']['blockers']
    invalid=copy.deepcopy(requests['articles']);invalid['fields'][0]={'group':'ITM0_1','name':'NOT_PUBLISHED','value':'TEST'}
    bad=client.post('/api/v1/sage/articles/prepare',json=invalid);out['negative_tests']['unpublished_field_http']=bad.status_code;assert bad.status_code==422
    invalid=copy.deepcopy(requests['articles']);invalid['keys']['ITMREF']="x' OR 1=1"
    bad=client.post('/api/v1/sage/articles/prepare',json=invalid);out['negative_tests']['invalid_key_http']=bad.status_code;assert bad.status_code==422
    if not out['security']['ready']:
        for resource,r in out['resources'].items():
            response=client.post('/api/v1/sage/operations/'+r['operation']['id']+'/approve',json={'digest':r['operation']['digest'],'confirm':False,'actor':'DIAGNOSTIC','reason':'NON APPROBATION : contrôle de refus uniquement'})
            out['negative_tests'][resource+'_approval_blocked_http']=response.status_code;assert response.status_code==423
out['resources']['customers']={'keys':{'BPCNUM':'C_AITEST01'},'data_proposed':{'BCGCOD':customer['BCGCOD_0'].strip(),'BPRNAM':['CLIENT TEST IA',''],'BPRSHO':'C_AITEST01',**{n:customer[n+'_0'].strip() for n in ['CRY','LAN','CUR','ACCCOD','VACBPR','PTE']}},
    'publication':None,'executed':False,'blockers':['NO_BPC_PUBLICATION_FOUND_IN_TEST_AWEBSERVIC','PUBLISHED_XML_MAPPING_NOT_AVAILABLE','NO_CUSTOMER_EXECUTION_ROUTE_VALIDATED'],
    'xml_file':None}
out['resources']['customers']['native_import_candidate']={'template':'BPC','object':'BPC','function':'GESBPC','exists_in_test':any(r['EXT_0']=='BPC' and r['OBJ_0']=='BPC' for r in sql.get('import_templates',[])),
    'automation_service':'AOWSIMPORT','description_probe':soap.get('AOWSIMPORT',{}),'executable':False,'data_file_generated':False,
    'blockers':['IMPORT_EXECUTION_CHANNEL_UNAVAILABLE','TEMPLATE_CREATE_ONLY_AND_BUSINESS_VALIDATION_REQUIRED','HUMAN_APPROVAL_REQUIRED']}
with stack.connect() as conn:
    out['real_approvals']=conn.execute('SELECT count(*) FROM sage_ai.soap_operation_approvals').fetchone()[0]
    out['real_write_attempts']=conn.execute("SELECT count(*) FROM sage_ai.soap_operation_events WHERE event_type='write_attempt_claimed'").fetchone()[0]
assert out['real_approvals']==0 and out['real_write_attempts']==0
(ROOT/'logs/four-creation-preparations.json').write_text(json.dumps(out,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps({'sage_writes':0,'security':out['security'],'preparations':{k:{'publication':v['publication'],'status':v.get('operation',{}).get('status','BLOCKED_NO_PUBLICATION'),'keys':v.get('request',{}).get('keys',v.get('keys'))} for k,v in out['resources'].items()},'negative_tests':out['negative_tests']},indent=2))
