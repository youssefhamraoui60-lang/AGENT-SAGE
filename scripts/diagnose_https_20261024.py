"""Read-only TLS diagnostic: no trust-store import, settings change or ERP write."""
import sys,json,ssl,socket,hashlib
from pathlib import Path
from datetime import datetime,timezone
import requests,httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services import sage_crud
ca=ROOT/'certs/ca.cacrt'
report={'at':datetime.now(timezone.utc).isoformat(),'windows_trust_modified':False,'production_modified':False,'soap_writes_sent':False}
report['ca']={'file_sha256':hashlib.sha256(ca.read_bytes()).hexdigest().upper(),'certificate_sha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca.read_text())).hexdigest().upper(),'decoded':ssl._ssl._test_decode_cert(str(ca))}
report['configuration']={'base_url':settings.sage_soap_base_url,'username_is_aiagt':settings.sage_soap_username.get_secret_value().casefold()=='aiagt','credentials_present':bool(settings.sage_soap_username.get_secret_value() and settings.sage_soap_password.get_secret_value()),'pool':settings.sage_soap_pool,'ca_bundle_configured':bool(settings.sage_soap_ca_bundle),'writes_enabled':settings.sage_writes_enabled}
report['dns']=sorted({x[4][0] for x in socket.getaddrinfo('sage',8443,type=socket.SOCK_STREAM)})
# Explicit candidate CA for this diagnostic only; not an organizational trust approval.
try:
    context=ssl.create_default_context(cafile=str(ca));context.minimum_version=ssl.TLSVersion.TLSv1_2
    with socket.create_connection(('sage',8443),timeout=6) as raw:
        with context.wrap_socket(raw,server_hostname='sage') as tls:
            report['tls']={'verified_against_candidate_ca':True,'hostname_verified':True,'version':tls.version(),'server_sha256':hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest().upper(),'certificate':tls.getpeercert(),'client_certificate_supplied':False,'revocation_checked':False}
    with requests.Session() as session:
        session.trust_env=False
        report['http']={}
        for name,path in [('root','/'),('wsdl','/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl')]:
            try:
                r=session.get('https://sage:8443'+path,verify=str(ca),timeout=10,allow_redirects=False)
                report['http'][name]={'status':r.status_code,'content_type':r.headers.get('Content-Type'),'wsdl_definitions_present':b'definitions' in r.content[:20000] if name=='wsdl' else None}
            except Exception as exc:
                report['http'][name]={'error_type':type(exc).__name__,'tls_alert': 'certificate_required' if 'certificate required' in str(exc).lower() else 'handshake_failure' if 'handshake failure' in str(exc).lower() else None}
except Exception as exc:
    report['tls']={'error_type':type(exc).__name__,'verify_code':getattr(exc,'verify_code',None),'verify_message':getattr(exc,'verify_message',None),'certificate_required':'certificate required' in str(exc).lower()}
report['local_security']=sage_crud.security()
report['requests_verified_probe']={}
with requests.Session() as session:
    session.trust_env=False
    for name,path in [('root','/'),('wsdl','/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl')]:
        try:
            response=session.get('https://sage:8443'+path,verify=str(ca),timeout=10,allow_redirects=False)
            report['requests_verified_probe'][name]={'status':response.status_code,'wsdl_definitions_present':b'definitions' in response.content[:20000] if name=='wsdl' else None}
        except Exception as exc:
            message=str(exc).lower()
            report['requests_verified_probe'][name]={'error_type':type(exc).__name__,'certificate_required':'certificate required' in message,'certificate_verify_failed':'certificate_verify_failed' in message,'handshake_failure':'handshake failure' in message}
with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=10) as client:
    report['fastapi']={}
    for path in ['/health','/health/db','/sage/']:
        try:report['fastapi'][path]=client.get(path).status_code
        except Exception as exc:report['fastapi'][path]=type(exc).__name__
    client.headers['X-Approval-Token']=settings.approval_token.get_secret_value()
    try:
        r=client.get('/api/v1/sage/security');report['fastapi']['security_status']=r.status_code
        if r.status_code==200:report['fastapi']['security']=r.json()
        if r.status_code==200 and r.json().get('ready') is False:
            report['fastapi']['invalid_empty_write_probe_status']=client.post('/api/v1/sage/articles',json={}).status_code
    except Exception as exc:report['fastapi']['error_type']=type(exc).__name__
target=ROOT/'logs/https-soap-diagnostic-20261024.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=str))
