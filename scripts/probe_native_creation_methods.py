"""Metadata GET/getDescription only. No import run, REST write or SQL execution."""
import sys,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_soap import SageReader,ALLOWED
from app.services.sage_gateway import Gateway
out={'checked_at':datetime.now(timezone.utc).isoformat(),'writes':0,'soap_read_transport_allowlist':sorted(ALLOWED),'rest_metadata':{}}
session,service=SageReader()._client()
try:
    out['wsdl_operations']=sorted(service._binding._operations)
    with service._client.settings(raw_response=True):
        response=service.getDescription(callContext={'codeLang':'FRA','poolAlias':settings.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML'},publicName='AOWSIMPORT')
    decoded=Gateway('articles').decode(response,'getDescription');out['AOWSIMPORT']={k:v for k,v in decoded.items() if k!='xml'}
    for name,path in [('catalog','/api1/x3/erp/V12_TEST/$catalog'),('ITM',"/api1/x3/erp/V12_TEST/$prototypes('ITM.$details')"),('BPC',"/api1/x3/erp/V12_TEST/$prototypes('BPC.$details')")]:
        try:
            response=session.get(settings.sage_soap_base_url+path,timeout=10,allow_redirects=False)
            out['rest_metadata'][name]={'http':response.status_code,'write_operation_tested':False}
        except Exception as exc:out['rest_metadata'][name]={'error_type':type(exc).__name__,'write_operation_tested':False}
finally:session.close()
(ROOT/'logs/native-creation-methods.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False))
