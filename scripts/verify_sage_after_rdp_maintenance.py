"""After approved maintenance only: verified HTTPS + AIAGT reads, never writes."""
import argparse,json,sys,ssl,socket,hashlib,re
import httpx,requests
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,quote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_gateway import Gateway
from app.services import sage_crud
from app.services.sage_tls import verified_context

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--article',required=True,help='Known existing article in TEST')
    p.add_argument('--site-article',required=True,help='Known existing article-site in TEST/201')
    p.add_argument('--expected-server-sha256',required=True,help='DER SHA-256 independently confirmed by administrator')
    args=p.parse_args()
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'POST_MAINTENANCE_READ_ONLY','save_sent':False,'tests':[],'status':'BLOCKED'}
    try:
        base=urlsplit(settings.sage_soap_base_url.rstrip('/'))
        if base.scheme!='https' or base.hostname!='sage' or base.port!=8443 or base.path or base.query or base.fragment or base.username or base.password:
            raise ValueError('approved_https_sage_8443_not_configured')
        if settings.sage_soap_username.get_secret_value().casefold()!='aiagt':raise ValueError('aiagt_not_configured')
        if settings.sage_writes_enabled:raise ValueError('writes_must_remain_disabled_during_read_acceptance')
        expected=args.expected_server_sha256.replace(':','').upper()
        if not re.fullmatch('[0-9A-F]{64}',expected):raise ValueError('invalid_public_certificate_fingerprint')
        context=verified_context(settings)
        with socket.create_connection(('sage',8443),timeout=5) as raw:
            with context.wrap_socket(raw,server_hostname='sage') as tls:
                fingerprint=hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest().upper()
                if fingerprint!=expected:raise ValueError('presented_certificate_fingerprint_mismatch')
                report['tls']={'version':tls.version(),'cipher':tls.cipher()[0],'hostname_verified':True,'chain_verified':True,'server_sha256':fingerprint,'revocation':'CRL_CHECK_CHAIN'}
        for resource,keys in [('articles',{'ITMREF':args.article}),('article-sites',{'ITMREF':args.site_article,'STOFCY':'201'})]:
            gateway=Gateway(resource);description=gateway.describe()
            if description.get('FOL')!='TEST' or description.get('SOL')!='V12' or description.get('USER','').casefold()!='aiagt':
                raise ValueError('effective_identity_or_folder_mismatch')
            result=gateway.read(keys,describe=False)
            report['tests'].append({'resource':resource,'context':{'folder':description.get('FOL'),'solution':description.get('SOL'),'object':description.get('OBJ'),'identity_is_aiagt':True},'keys':keys,'exists':result['exists'],'soap_status':result['status'],'messages':result['messages'],'description_hash':sage_crud.description_hash(description),'https_verified_by_connector':True})
            if result['exists'] is not True or result['status']!=1:raise ValueError('known_test_record_not_readable')
        report['status']='READ_ACCEPTANCE_PASS'
        report['creation_rights_exercised']=False
        report['admin_rights_evidence_still_required']=True
        with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=5) as client:
            denied=client.get('/api/v1/sage/security')
            if denied.status_code!=403:raise ValueError('unauthenticated_api_not_rejected')
            client.headers['X-Approval-Token']=settings.approval_token.get_secret_value()
            security_response=client.get('/api/v1/sage/security');security_response.raise_for_status()
            live=security_response.json()
            local=sage_crud.security()
            if live.get('ready') is not False or 'WRITES_DISABLED' not in live.get('blockers',[]):raise ValueError('write_gate_not_closed')
            if set(live.get('blockers',[]))!=set(local['blockers']):raise ValueError('backend_configuration_not_reloaded_or_not_matching')
            for item in report['tests']:
                schema=client.get('/api/v1/sage/'+item['resource']+'/schema');schema.raise_for_status()
                if schema.json().get('description_hash')!=item['description_hash']:raise ValueError('backend_soap_identity_or_mapping_mismatch')
                suffix=quote(item['keys']['ITMREF'],safe='')+('/201' if item['resource']=='article-sites' else '')
                record=client.get('/api/v1/sage/'+item['resource']+'/'+suffix);record.raise_for_status()
                if record.json().get('record',{}).get('exists') is not True:raise ValueError('fastapi_existing_record_not_readable')
                item['fastapi_read_status']=record.status_code
            blocked=client.post('/api/v1/sage/articles',json={})
            if blocked.status_code!=423:raise ValueError('write_probe_not_rejected_with_423')
            report['fastapi_live']={'unauthenticated_status':denied.status_code,'security':live,'invalid_empty_write_probe_status':blocked.status_code,'soap_save_sent':False}
    except Exception as exc:
        # No raw network exceptions, authentication headers or credentials in logs.
        report['error_type']=type(exc).__name__
        safe_codes={'approved_https_sage_8443_not_configured','aiagt_not_configured','writes_must_remain_disabled_during_read_acceptance','effective_identity_or_folder_mismatch','known_test_record_not_readable','invalid_public_certificate_fingerprint','presented_certificate_fingerprint_mismatch','unauthenticated_api_not_rejected','write_gate_not_closed','backend_configuration_not_reloaded_or_not_matching','write_probe_not_rejected_with_423','backend_soap_identity_or_mapping_mismatch','fastapi_existing_record_not_readable'}
        report['error_code']=str(exc) if isinstance(exc,ValueError) and str(exc) in safe_codes else getattr(exc,'code','read_acceptance_failed')
        report['status']='BLOCKED'
    report['fastapi_security']=sage_crud.security()
    target=ROOT/'logs'/('sage-rdp-acceptance-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with target.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2));print('Report: '+str(target))
    return 0 if report['status']=='READ_ACCEPTANCE_PASS' else 1
if __name__=='__main__':raise SystemExit(main())
