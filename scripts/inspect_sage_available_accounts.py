"""GET only: non-secret Syracuse account identifiers, no passwords/private keys."""
import sys,json
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlencode,quote
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_soap import SageReader
from app.core.config import settings
out={'checked_at':datetime.now(timezone.utc).isoformat(),'writes':0,'account_query_limit':100,'entities':{}}
session,_=SageReader()._client()
try:
    for entity,representation,fields in [
        ('users','user.$query',['login','active','enabled']),
        ('groups','group.$query',['description','name']),
        ('soapClassicPools','soapClassicPool.$query',['alias','initSize','maxSize'])]:
        params=urlencode({'representation':representation,'count':100},quote_via=quote)
        r=session.get(settings.sage_soap_base_url+'/api1/syracuse/collaboration/syracuse/'+entity+'?'+params,timeout=15,allow_redirects=False)
        data=r.json() if 'json' in r.headers.get('content-type','') else {}
        rows=data.get('$resources',[])
        out['entities'][entity]={'http':r.status_code,'rows':[{k:row[k] for k in fields if k in row} for row in rows],'returned':len(rows),'exhaustive':False}
    out['technical_account_exact_checks']={}
    for login in ['AIAGT','agent_sage_x3','agent_sage_test']:
        params=urlencode({'representation':'user.$query','where':"login eq '"+login+"'"},quote_via=quote)
        r=session.get(settings.sage_soap_base_url+'/api1/syracuse/collaboration/syracuse/users?'+params,timeout=15,allow_redirects=False)
        data=r.json() if 'json' in r.headers.get('content-type','') else {}
        out['technical_account_exact_checks'][login]={'http':r.status_code,'matches':[{k:row[k] for k in ['login','active'] if k in row} for row in data.get('$resources',[])]}
finally:session.close()
(ROOT/'logs/sage-available-accounts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
