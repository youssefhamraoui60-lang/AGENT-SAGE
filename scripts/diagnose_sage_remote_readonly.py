"""Only GET and allowlisted SOAP getDescription/read/query; no remote system commands."""
import sys,json,socket,ssl,hashlib
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlencode,quote
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_gateway import Gateway
from app.services.sage_soap import SageReader
out={'checked_at':datetime.now(timezone.utc).isoformat(),'access':'AGENT_VM_NETWORK_AND_HTTP_ONLY','remote_os_access':False,'writes_sent':False,'tcp':{},'https':{},'http':{},'soap':{},'administration':{}}
def failure(exc):return {'error_type':type(exc).__name__,'code':getattr(exc,'code','request_failed')}
for port in [8124,8443,443,22]:
    try:
        with socket.create_connection(('192.168.9.200',port),timeout=2):out['tcp'][str(port)]=True
    except OSError:out['tcp'][str(port)]=False
out['dns_sage']=sorted({v[4][0] for v in socket.getaddrinfo('sage',None)})
public=requests.Session();public.trust_env=False
for port in [443,8443]:
    url=f'https://sage:{port}/'
    try:
        response=public.get(url,timeout=4,allow_redirects=False)
        out['https'][url]={'http':response.status_code,'tls_verified':True}
    except requests.RequestException as exc:out['https'][url]={**failure(exc),'tls_verified':False}
reader=SageReader();session,service=reader._client()
try:
    for name,url in [('entry_8080','http://192.168.9.200:8080/'),('entry_8124',settings.sage_soap_base_url+'/'),('wsdl',settings.sage_soap_base_url+'/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl')]:
        try:
            response=session.get(url,timeout=10,allow_redirects=False)
            location=response.headers.get('location','');parsed=urlsplit(location)
            out['http'][name]={'url':url,'status':response.status_code,'content_type':response.headers.get('content-type'),
                'redirect_target_without_query':(parsed.scheme+'://'+parsed.netloc+parsed.path) if parsed.netloc else parsed.path,
                'wsdl_definitions':b'definitions' in response.content[:200000] if name=='wsdl' else None}
        except requests.RequestException as exc:out['http'][name]=failure(exc)
    def admin_get(entity,representation,where=None):
        params={'representation':representation,'count':5}
        if where:params['where']=where
        # Syracuse's classic pool filter requires %20, not form-style '+' spaces.
        if where:params.pop('count',None)
        url=settings.sage_soap_base_url+'/api1/syracuse/collaboration/syracuse/'+entity+'?'+urlencode(params,quote_via=quote)
        response=session.get(url,timeout=15,allow_redirects=False)
        try:data=response.json()
        except ValueError:data={}
        return response,data
    for entity,representation,where,fields in [
        ('soapClassicPools','soapClassicPool.$query',"alias eq 'POOL_AI_TEST'",['alias','initSize','maxSize','status','poolStatus']),
        ('soapPoolStates','soapPoolState.$query',"alias eq 'POOL_AI_TEST'",['alias','status','poolStatus','pid']),
        ('hosts','host.$query',None,['hostname','tcpHostName','status','version','wsChildren'])]:
        try:
            response,data=admin_get(entity,representation,where);rows=data.get('$resources',[])
            summary=[]
            for row in rows:
                item={k:row[k] for k in fields if k in row}
                if entity=='hosts':
                    item['connections']=[{k:c.get(k) for k in ['port','active','ssl'] if k in c} for c in row.get('connectionData',[])]
                if entity=='soapClassicPools':
                    endpoint=row.get('endpoint',{});item['endpoint_description']=endpoint.get('description')
                    uid=endpoint.get('$uuid')
                    if uid:
                        ep,ed=admin_get("endPoints('"+uid+"')",'endPoint.$details')
                        item['endpoint_http']=ep.status_code
                        item['endpoint']={k:ed[k] for k in ['dataset','folder','x3Folder','x3Solution','name'] if k in ed}
                summary.append(item)
            out['administration'][entity]={'http':response.status_code,'rows':summary,'count':len(rows)}
        except Exception as exc:out['administration'][entity]=failure(exc)
    for entity,representation in [('certificates','certificate.$query'),('caCertificates','caCertificate.$query')]:
        try:
            response,data=admin_get(entity,representation);certs=[]
            for row in data.get('$resources',[])[:5]:
                uid=row.get('$uuid')
                if not uid:continue
                cert_response=session.get(settings.sage_soap_base_url+"/api1/syracuse/collaboration/syracuse/"+entity+"('"+uid+"')/certificate",timeout=10,allow_redirects=False)
                raw=cert_response.content
                if cert_response.status_code!=200 or b'-----BEGIN CERTIFICATE-----' not in raw or b'PRIVATE KEY' in raw:continue
                public_file=ROOT/'runtime'/('diagnostic-public-'+entity+'-'+str(len(certs))+'.pem');public_file.write_bytes(raw)
                cert=ssl._ssl._test_decode_cert(str(public_file))
                certs.append({'sha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert(raw.decode())).hexdigest(),
                    'subject':cert.get('subject'),'issuer':cert.get('issuer'),'san':cert.get('subjectAltName'),
                    'not_before':cert.get('notBefore'),'not_after':cert.get('notAfter'),'retrieved_over':'HTTP_NOT_AUTHENTICATED_OUT_OF_BAND','trust_installed':False})
            out['administration'][entity]={'http':response.status_code,'public_certificates':certs}
        except Exception as exc:out['administration'][entity]=failure(exc)
finally:session.close();public.close()
targets={'articles':{'ITMREF':'TAI261017948E'},'suppliers':{'BPSNUM':'TB261017948E'},'article-sites':{'ITMREF':'TAI261017948E','STOFCY':'201'}}
for resource,keys in targets.items():
    entry={};gateway=Gateway(resource)
    try:
        desc=gateway.describe();entry['getDescription']={'result':'PASS','folder':desc.get('FOL'),'solution':desc.get('SOL'),'object':desc.get('OBJ'),'x3_identity_is_admin':desc.get('USER','').casefold() in ['admin','administrator']}
        listed=gateway.query(3);entry['query']={'status':listed['status'],'messages':listed['messages'],'count':len(listed['records'])}
        if listed['records']:
            sample={k:listed['records'][0][k] for k in gateway.spec['keys']};read=gateway.read(sample)
            entry['read_existing']={k:read[k] for k in ['keys','exists','status','messages']}
        read=gateway.read(keys);entry['read_candidate']={k:read[k] for k in ['keys','exists','status','messages']}
    except Exception as exc:entry['error']=failure(exc)
    out['soap'][resource]=entry
(ROOT/'logs/step4-remote-readonly-diagnostic.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False))
