"""Local read-only configuration/service audit. Never emit secrets or raw errors."""
import json,sys,re,os,socket
from pathlib import Path
from urllib.parse import urlsplit,unquote
from datetime import datetime,timezone
import httpx,psycopg
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
values=dotenv_values(ROOT/'.env',interpolate=False)
required=['DATABASE_URL','DB_PORT','POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB','NATIVE_PG_ADMIN_PASSWORD','N8N_DB_PASSWORD','N8N_ENCRYPTION_KEY','N8N_PORT','OLLAMA_URL','OLLAMA_MODEL','APPROVAL_TOKEN','SAGE_SOAP_USERNAME','SAGE_SOAP_BASE_URL','SAGE_SOAP_CA_BUNDLE','SAGE_SOAP_CREDENTIAL_FILE','SAGE_WRITES_ENABLED']
report={'checked_at':datetime.now(timezone.utc).isoformat(),'missing':[k for k in required if k not in values],'empty':[k for k,v in values.items() if not v],'placeholders':[k for k,v in values.items() if v and re.search(r'<[^>]+>|CHANGE.?ME|NOUVEAU_MOT_DE_PASSE|YOUR[_ -]|REPLACE[_ -]',v,re.I)],'secrets_printed':False}
names=[s.split('=',1)[0].strip() for s in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#') and '=' in s]
report['duplicate_keys']=sorted({k for k in names if names.count(k)>1})
def connection(name,**kwargs):
    try:
        with psycopg.connect(connect_timeout=4,options='-c default_transaction_read_only=on',**kwargs) as conn:
            row=conn.execute('SELECT current_database(),current_user,inet_server_port()').fetchone()
            report[name]={'ok':True,'database':row[0],'user':row[1],'server_port':row[2]}
    except Exception as exc:report[name]={'ok':False,'error_type':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None)}
connection('database_url',conninfo=values.get('DATABASE_URL',''))
common={'host':'127.0.0.1','port':55432}
connection('postgres_app_credentials',**common,dbname=values.get('POSTGRES_DB'),user=values.get('POSTGRES_USER'),password=values.get('POSTGRES_PASSWORD'))
connection('postgres_admin_credentials',**common,dbname='postgres',user='sage_admin',password=values.get('NATIVE_PG_ADMIN_PASSWORD'))
connection('n8n_database_credentials',**common,dbname='n8n',user='n8n',password=values.get('N8N_DB_PASSWORD'))
try:
    url=urlsplit(values.get('DATABASE_URL',''))
    report['database_url_consistency']={'host_local':url.hostname in ['127.0.0.1','localhost'],'port_55432':url.port==55432,'user_matches':unquote(url.username or '')==values.get('POSTGRES_USER'),'password_matches':unquote(url.password or '')==values.get('POSTGRES_PASSWORD'),'database_matches':unquote(url.path.lstrip('/'))==values.get('POSTGRES_DB')}
except Exception:report['database_url_consistency']={'valid':False}
report['n8n_encryption_key']={'configured':bool(values.get('N8N_ENCRYPTION_KEY')),'stored_config_found':False,'changed':False}
config=ROOT/'runtime/n8n/.n8n/config'
if config.is_file():
    try:
        saved=json.loads(config.read_text(encoding='utf-8-sig'))
        report['n8n_encryption_key'].update(stored_config_found=True,matches_persisted=saved.get('encryptionKey')==values.get('N8N_ENCRYPTION_KEY'))
    except Exception:report['n8n_encryption_key']['config_parse_error']=True
report['pg_hba_password_auth_present']='scram-sha-256' in (ROOT/'runtime/postgres/pg_hba.conf').read_text()
report['http']={}
with httpx.Client(trust_env=False,timeout=8) as client:
    for label,url in [('fastapi','http://127.0.0.1:8000/health'),('postgres_health','http://127.0.0.1:8000/health/db'),('react','http://127.0.0.1:8000/sage/'),('n8n','http://127.0.0.1:5678/healthz'),('n8n_readiness','http://127.0.0.1:5678/healthz/readiness')]:
        try:report['http'][label]=client.get(url).status_code
        except Exception as exc:report['http'][label]=type(exc).__name__
    try:
        r=client.get('http://127.0.0.1:11434/api/tags');r.raise_for_status()
        report['ollama']={'http_status':r.status_code,'qwen_2_5_7b_available':any(m.get('name')=='qwen2.5:7b' for m in r.json().get('models',[]))}
    except Exception as exc:report['ollama']={'error_type':type(exc).__name__}
    if values.get('N8N_OWNER_EMAIL') and values.get('N8N_OWNER_PASSWORD'):
        try:
            r=client.post('http://127.0.0.1:5678/rest/login',json={'emailOrLdapLoginId':values['N8N_OWNER_EMAIL'],'password':values['N8N_OWNER_PASSWORD']})
            report['n8n_owner_login']={'http_status':r.status_code,'ok':r.status_code==200}
        except Exception as exc:report['n8n_owner_login']={'error_type':type(exc).__name__}
    else:report['n8n_owner_login']={'configured':False}
    client.headers['X-Approval-Token']=values.get('APPROVAL_TOKEN','')
    try:
        r=client.get('http://127.0.0.1:8000/api/v1/sage/security');report['security_http']=r.status_code
        if r.status_code==200:report['security']=r.json()
        if r.status_code==200 and r.json().get('ready') is False:
            report['write_route_probes']={}
            for method,path in [('POST','articles'),('POST','suppliers'),('POST','article-sites'),('PATCH','articles/AUDIT_NOT_EXECUTED'),('PATCH','suppliers/AUDIT_NOT_EXECUTED'),('PATCH','article-sites/AUDIT_NOT_EXECUTED/201'),('POST','operations/00000000-0000-0000-0000-000000000000/approve')]:
                report['write_route_probes'][method+' '+path]=client.request(method,'http://127.0.0.1:8000/api/v1/sage/'+path,json={}).status_code
    except Exception as exc:report['security_error_type']=type(exc).__name__
report['aiagt']={'username_correct':values.get('SAGE_SOAP_USERNAME')=='AIAGT','https_url_correct':values.get('SAGE_SOAP_BASE_URL')=='https://sage:8443','ca_path_correct':values.get('SAGE_SOAP_CA_BUNDLE')=='C:/AGENT-SAGE-X3/certs/ca.cacrt','credential_path_correct':values.get('SAGE_SOAP_CREDENTIAL_FILE')=='C:/AGENT-SAGE-X3/runtime/aiagt-secret/credential.clixml','plaintext_password_present':bool(values.get('SAGE_SOAP_PASSWORD')),'dpapi_present':(ROOT/'runtime/aiagt-secret/credential.clixml').is_file()}
if report['aiagt']['dpapi_present']:
    try:
        from app.core.dpapi_credential import load_aiagt_credential
        secret=load_aiagt_credential(str(ROOT/'runtime/aiagt-secret/credential.clixml'))
        report['aiagt']['decrypt_current_identity_ok']=bool(secret.get_secret_value());del secret
    except Exception:report['aiagt']['decrypt_current_identity_ok']=False
target=ROOT/'logs/env-soap-audit.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
