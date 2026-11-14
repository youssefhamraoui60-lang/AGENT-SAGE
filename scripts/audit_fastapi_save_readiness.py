"""Audit effective gates and serialize save via the existing WSDL; never execute save."""
import json,sys
from datetime import datetime,timezone
from pathlib import Path
from lxml import etree
import httpx
import native_stack as stack
ROOT=stack.ROOT;sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_gateway import Gateway
from app.services.sage_crud import security
result={'checked_at':datetime.now(timezone.utc).isoformat(),'sage_writes':0,'production_configuration_changed':False}
result['effective_settings']={'base_url':settings.sage_soap_base_url,'pool':settings.sage_soap_pool,
    'writes_enabled':settings.sage_writes_enabled,'http_credentials_present':bool(settings.sage_soap_username.get_secret_value() and settings.sage_soap_password.get_secret_value()),
    'policy_path_configured':bool(settings.sage_security_policy_file),'policy_file_exists':bool(settings.sage_security_policy_file and Path(settings.sage_security_policy_file).is_file()),
    'ca_bundle_configured':bool(settings.sage_soap_ca_bundle)}
result['local_security']=security()
gateway=Gateway('articles');desc=gateway.describe()
result['article_publication']={'folder':desc.get('FOL'),'solution':desc.get('SOL'),'object':desc.get('OBJ'),
    'create_published':any(n.get('ID')=='CREATE' for n in desc.iter('MET')),'x3_identity_is_admin':desc.get('USER','').casefold() in ['admin','administrator'],
    'scoped_security':security('articles','create',desc),'dedicated_account_rights_verified':False}
manual=gateway.read({'ITMREF':'TSTAI2610174D94B4'})
result['manual_article_read']={k:manual[k] for k in ['keys','status','exists','messages']}
result['manual_article_read']['fields']={k:v for k,v in manual.get('fields',{}).items() if k in ['ITM0_1.ITMREF','ITM0_1.DES1AXX','ITM0_1.TCLCOD']}
request=json.loads((ROOT/'logs/step4-article-supplier-requested.json').read_text())['resources']['articles']['create_preparation']['request']
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},timeout=60,trust_env=False) as client:
    response=client.get('/api/v1/sage/security');response.raise_for_status();result['live_api_security']=response.json()
    prepared=client.post('/api/v1/sage/articles/prepare',json=request);prepared.raise_for_status();operation=prepared.json()
result['preparation']={k:operation[k] for k in ['id','status','digest','record_keys','before_record','checks']}
session,service=gateway.reader._client()
try:
    result['real_wsdl_signatures']={name:service._binding._operations[name].input.signature() for name in ['read','query','save']}
    envelope=service._client.create_message(service,'save',callContext={'codeLang':'FRA','poolAlias':settings.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName='WS_ARTICLE',objectXml=operation['object_xml'])
    path=ROOT/'examples/crud-api/articles-save-current-NOT-SENT.xml'
    path.write_bytes(etree.tostring(envelope,encoding='utf-8',xml_declaration=True,pretty_print=True))
    result['save_serialization']={'status':'PASS','sent':False,'file':str(path),'source':'Zeep create_message against real WSDL'}
    # Exact HTTP GET only; no production changes or credential data emitted.
    response=session.get(settings.sage_soap_base_url+"/api1/x3/erp/V12_TEST/$prototypes('ITM.$details')",timeout=15,allow_redirects=False)
    result['business_metadata_http']=response.status_code
finally:session.close()
with stack.connect() as conn:
    result['approvals_count']=conn.execute('SELECT count(*) FROM sage_ai.soap_operation_approvals').fetchone()[0]
    result['write_attempts_count']=conn.execute("SELECT count(*) FROM sage_ai.soap_operation_events WHERE event_type='write_attempt_claimed'").fetchone()[0]
assert result['approvals_count']==0 and result['write_attempts_count']==0
(ROOT/'logs/step4-save-readiness.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=False,default=str))
