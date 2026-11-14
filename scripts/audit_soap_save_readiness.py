"""Fresh public TLS and local write-gate evidence. Never sends credentials or SAVE."""
import hashlib,json,os,re,socket,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services import sage_crud
from app.services.sage_tls import verified_context,TLSConfigurationError
from app.core.dpapi_credential import load_aiagt_credential

OUT=ROOT/'tests/ai-evaluation/reports/soap-save-readiness-20261030'
OPENSSL=ROOT/'runtime/pki-test/tools/openssl-3.5.9/bin/openssl.exe'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    evidence={'at':datetime.now(timezone.utc).isoformat(),'host_ips':socket.gethostbyname_ex(socket.gethostname())[2],
              'mode':'TLS_PUBLIC_INSPECTION_AND_LOCAL_GATE_NO_SAGE_WRITE','sage_writes':0,'production_changes':False}
    evidence['sage_ipv4']=socket.gethostbyname('sage')
    evidence['settings']={k:getattr(settings,k) for k in ('sage_soap_base_url','sage_soap_pool','sage_soap_ca_bundle','sage_soap_crl_bundle','sage_soap_credential_file','sage_security_policy_file','sage_writes_enabled')}
    evidence['identity']={'effective_is_AIAGT':settings.sage_soap_username.get_secret_value()=='AIAGT','effective_is_admin':settings.sage_soap_username.get_secret_value().lower() in ('admin','administrator'),'credential_loaded':bool(settings.sage_soap_password.get_secret_value())}
    f=ROOT/'runtime/aiagt-secret/credential.clixml'
    evidence['aiagt_local_credential']={'exists':f.is_file(),'decrypts':False,'configured':Path(settings.sage_soap_credential_file).resolve()==f.resolve()}
    if f.is_file():
        try:evidence['aiagt_local_credential']['decrypts']=bool(load_aiagt_credential(str(f),'AIAGT').get_secret_value())
        except Exception as e:evidence['aiagt_local_credential']['error_type']=type(e).__name__
    evidence['write_security']={r:sage_crud.security(r,'create') for r in ('articles','suppliers')}
    try:
        context=verified_context(settings)
        evidence['tls_local_material']={'ready':True,'strict':bool(context.verify_flags & __import__('ssl').VERIFY_X509_STRICT),'revocation_chain':bool(context.verify_flags & __import__('ssl').VERIFY_CRL_CHECK_CHAIN)}
    except TLSConfigurationError as e:evidence['tls_local_material']={'ready':False,'code':str(e)}
    if OPENSSL.is_file():
        env=os.environ.copy();env.update(OPENSSL_CONF=str(OPENSSL.parents[1]/'ssl/openssl.cnf'),OPENSSL_MODULES=str(OPENSSL.parents[1]/'lib/ossl-modules'),OPENSSL_ENGINES=str(OPENSSL.parents[1]/'lib/engines-3'))
        def run(args):
            r=subprocess.run([str(OPENSSL),*args],input=b'',capture_output=True,timeout=20,env=env)
            return r
        try:
            # Fatal verification: never accept an invalid chain, no -k or verify bypass.
            r=run(['s_client','-4','-connect','sage:8443','-servername','sage','-verify_hostname','sage','-verify_return_error','-x509_strict','-crl_check_all','-CAfile',settings.sage_soap_ca_bundle,'-showcerts'])
            pem=re.findall(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',r.stdout,re.S)
            evidence['strict_live_handshake']={'returncode':r.returncode,'accepted':r.returncode==0,'diagnostic':r.stderr.decode('utf8','replace')[:6000],'public_certificates_received':len(pem)}
            certfiles=[]
            for i,data in enumerate(pem):
                target=OUT/f'presented-{i}.pem';target.write_bytes(data+b'\n');certfiles.append(target)
            for name,file in [('configured_ca',Path(settings.sage_soap_ca_bundle)),*[(f'presented_{i}',f) for i,f in enumerate(certfiles)]]:
                if not file.is_file():continue
                r=run(['x509','-in',str(file),'-noout','-subject','-issuer','-serial','-dates','-fingerprint','-sha256','-ext','subjectAltName,authorityKeyIdentifier,subjectKeyIdentifier,crlDistributionPoints,authorityInfoAccess,keyUsage,basicConstraints'])
                evidence[name]={'metadata':r.stdout.decode('utf8','replace'),'file_sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
            if certfiles:
                r=run(['verify','-x509_strict','-purpose','sslserver','-verify_hostname','sage','-crl_check_all','-CAfile',settings.sage_soap_ca_bundle,str(certfiles[0])])
                evidence['strict_offline_verification']={'returncode':r.returncode,'diagnostic':(r.stdout+r.stderr).decode('utf8','replace')[:6000]}
        except subprocess.TimeoutExpired:evidence['strict_live_handshake']={'accepted':False,'error':'diagnostic_timeout'}
    (OUT/'readiness.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'evidence':str(OUT/'readiness.json'),'tls':evidence.get('tls_local_material'),'identity':evidence['identity'],'aiagt_credential':evidence['aiagt_local_credential'],'handshake':evidence.get('strict_live_handshake',{}).get('accepted'),'sage_writes':0}))

if __name__=='__main__':main()
