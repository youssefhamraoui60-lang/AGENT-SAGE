"""Prepare one new SOAP article draft while SQL consultation remains under validation."""
import json,secrets,copy
from pathlib import Path
from datetime import datetime,timezone
import httpx
import native_stack as stack
from lxml import etree
import sys
ROOT=stack.ROOT;sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_gateway import Gateway
from app.core.config import settings
plan_path=ROOT/'runtime/sql-transition-article-plan.json'
if plan_path.exists():plan=json.loads(plan_path.read_text())
else:
    plan={'code':'TAI261019'+secrets.token_hex(3).upper(),'designation':'ARTICLE TEST CREATION API SAGE X3'}
    plan_path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
gateway=Gateway('articles');before=gateway.read({'ITMREF':plan['code']});assert before['exists'] is False
request=copy.deepcopy(json.loads((ROOT/'logs/step4-new-article-save.json').read_text())['request']);request['keys']={'ITMREF':plan['code']}
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=60) as client:
    security=client.get('/api/v1/sage/security').json()
    response=client.post('/api/v1/sage/articles/prepare',json=request);response.raise_for_status();operation=response.json()
session,service=gateway.reader._client()
try:
    envelope=service._client.create_message(service,'save',callContext={'codeLang':'FRA','poolAlias':settings.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName='WS_ARTICLE',objectXml=operation['object_xml'])
    xml_path=ROOT/'examples/crud-api'/('save-'+plan['code']+'-SQL-TRANSITION-NOT-SENT.xml');xml_path.write_bytes(etree.tostring(envelope,encoding='utf-8',pretty_print=True))
finally:session.close()
proof={'checked_at':datetime.now(timezone.utc).isoformat(),'plan':plan,'before':before,'security':security,
       'operation_id':operation['id'],'digest':operation['digest'],'object_xml':operation['object_xml'],'xml_path':str(xml_path),
       'sql_read_executed':False,'save_executed':False,'conditional_rules_verified':False}
(ROOT/'logs/sql-transition-article-preparation.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'code':plan['code'],'read_exists':before['exists'],'prepare_http':response.status_code,'save_sent':False},indent=2))
