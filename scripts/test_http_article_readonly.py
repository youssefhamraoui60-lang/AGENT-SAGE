"""Explicitly requested HTTP SOAP diagnostics. Never alters runtime configuration.
Only getDescription/read dispatched through the existing read-only transport.
"""
import sys,json,socket
from pathlib import Path
from datetime import datetime,timezone
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_gateway import Gateway,build_xml
from app.services.sage_soap import parse_xml,WSDL_PATH
from app.schemas.sage_crud import Preparation

report={'at':datetime.now(timezone.utc).isoformat(),'url':'http://192.168.9.200:8124','mode':'EXPLICIT_HTTP_READ_ONLY','save_sent':False,'runtime_configuration_changed':False,'transport_encrypted':False,'soap':{}}
g=Gateway('articles');g.reader.config.sage_soap_base_url=report['url']
report['pool']=g.reader.config.sage_soap_pool
report['configured_identity_is_aiagt']=settings.sage_soap_username.get_secret_value()=='AIAGT'
candidate=json.loads((ROOT/'runtime/single-save-candidate-20261025.json').read_text())
description=None
try:
    if not report['configured_identity_is_aiagt']:raise ValueError('expected_aiagt')
    with socket.create_connection(('192.168.9.200',8124),timeout=5):report['tcp']='OPEN'
    with requests.Session() as public:
        public.trust_env=False
        r=public.get(report['url']+WSDL_PATH,timeout=10,allow_redirects=False)
        report['public_wsdl']={'http':r.status_code,'definitions_present':b'definitions' in r.content[:200000]}
    session,service=g.reader._client()
    response_status=[]
    session.hooks['response'].append(lambda response,*args,**kwargs:response_status.append(response.status_code))
    try:
        for label,method,extra in [('description','getDescription',{}),('read_CPJ35','read',{'objectKeys':[{'key':'ITMREF','value':'CPJ35'}]}),('read_candidate','read',{'objectKeys':[{'key':'ITMREF','value':candidate['candidate']['code']} ]})]:
            try:
                with service._client.settings(raw_response=True):
                    response=getattr(service,method)(callContext={'codeLang':'FRA','poolAlias':g.reader.config.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName='WS_ARTICLE',**extra)
                result=g.decode(response,method)
                entry={'http':response.status_code,'status':result['status'],'messages':result['messages']}
                if result['status']==1 and result['xml']:
                    xml=parse_xml(result['xml'])
                    if label=='description':
                        entry['context']={k:xml.get(k) for k in ['FOL','SOL','USER','OBJ','PNA']}
                        if all(xml.get(k)==v for k,v in {'FOL':'TEST','SOL':'V12','OBJ':'ITM','PNA':'WS_ARTICLE'}.items()):description=xml
                    else:
                        entry['fields']={n.get('NAME'):n.text for n in xml.iter('FLD') if n.get('NAME') in ['ITMREF','DES1AXX','TCLCOD','STU','STOMGTCOD']}
                        entry['exists']=True
                elif label!='description':
                    entry['exists']=False if result['status']==0 and any('Fiche inexistante' in m for m in result['messages']) else None
                report['soap'][label]=entry
            except Exception as exc:
                report['soap'][label]={'error_type':type(exc).__name__,'code':getattr(exc,'code','read_diagnostic_failed'),'http':response_status[-1] if response_status else None}
                if getattr(exc,'code',None)=='sage_authentication_required':
                    report['further_authenticated_tests_stopped']=True
                    break
    finally:session.close()
    if description is not None:
        request=Preparation.model_validate(candidate['request']);xml=build_xml(description,g.spec,request)
        file=ROOT/'examples/step4/single-save-live-http-validated-NOT-SENT.xml';file.write_text(xml,encoding='utf-8')
        report['prepared_xml']={'live_mapping_validated':True,'path':str(file),'conditional_rules_verified':False,'human_approval':False}
except Exception as exc:report['error']={'type':type(exc).__name__,'code':getattr(exc,'code','http_read_diagnostic_failed')}
report['candidate']=candidate['candidate'];report['writes_disabled']=not settings.sage_writes_enabled
target=ROOT/'logs/http-article-readonly-20261026.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
