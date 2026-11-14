"""After approved deployment only: TLS + CRLs before any authenticated SOAP."""
import sys,json,socket,hashlib,re,argparse
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_tls import verified_context
from app.services.sage_gateway import Gateway

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-leaf-sha256',required=True)
    args=parser.parse_args();expected=args.expected_leaf_sha256.replace(':','').upper()
    report={'at':datetime.now(timezone.utc).isoformat(),'status':'BLOCKED','authenticated_soap_started':False,'writes_sent':False,'resources':[]}
    try:
        if not re.fullmatch('[0-9A-F]{64}',expected):raise ValueError('invalid_fingerprint')
        if settings.sage_writes_enabled or settings.sage_soap_base_url.rstrip('/')!='https://sage:8443':raise ValueError('invalid_read_only_config')
        if settings.sage_soap_username.get_secret_value()!='AIAGT' or not settings.sage_soap_password.get_secret_value():raise ValueError('aiagt_not_provisioned')
        context=verified_context(settings)
        with socket.create_connection(('sage',8443),timeout=5) as raw:
            with context.wrap_socket(raw,server_hostname='sage') as tls:
                if hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest().upper()!=expected:raise ValueError('fingerprint_mismatch')
                report['tls']={'version':tls.version(),'hostname_verified':True,'revocation':'CRL_CHECK_CHAIN'}
        # No authentication before TLS/CRLs/pin succeeds.
        report['authenticated_soap_started']=True
        for resource in ['articles','suppliers','article-sites']:
            gateway=Gateway(resource);desc=gateway.describe()
            if desc.get('USER','').upper()!='AIAGT':raise ValueError('effective_x3_identity_mismatch')
            result=gateway.query(2)
            item={'resource':resource,'description_valid':True,'folder':'TEST','query_status':result['status'],'query_count':len(result['records'])}
            if resource=='articles':keys={'ITMREF':'CPJ35'}
            elif result['records']:
                record=result['records'][0];keys={k:record[k] for k in gateway.spec['keys'] if record.get(k)}
                if set(keys)!=set(gateway.spec['keys']):raise ValueError('query_read_keys_unavailable')
            else:raise ValueError('no_existing_record_for_read_test')
            read=gateway.read(keys);item.update(keys=keys,read_status=read['status'],exists=read['exists'])
            report['resources'].append(item)
            if read['exists'] is not True:raise ValueError('record_read_not_confirmed')
        report['status']='PASS'
    except Exception as exc:
        codes={'invalid_fingerprint','invalid_read_only_config','aiagt_not_provisioned','fingerprint_mismatch','effective_x3_identity_mismatch','query_read_keys_unavailable','no_existing_record_for_read_test','record_read_not_confirmed'}
        report.update(error_type=type(exc).__name__,error_code=str(exc) if isinstance(exc,ValueError) and str(exc) in codes else getattr(exc,'code','tls_or_soap_validation_failed'))
    target=ROOT/'logs'/('approved-https-soap-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    target.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
