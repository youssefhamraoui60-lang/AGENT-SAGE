"""Boolean-only DPAPI verification; no Sage network access."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
result={'dpapi_created':False,'path_validated':False,'decryption_ok':False,'fastapi_can_load':False,'http_423':False}
try:
    from app.core.config import settings
    from app.core.dpapi_credential import load_aiagt_credential
    file=ROOT/'runtime/aiagt-secret/credential.clixml'
    result['dpapi_created']=file.is_file()
    result['path_validated']=Path(settings.sage_soap_credential_file).resolve()==file.resolve()
    result['decryption_ok']=bool(load_aiagt_credential(str(file)).get_secret_value())
    result['fastapi_can_load']=bool(settings.sage_soap_password.get_secret_value()) and settings.sage_soap_username.get_secret_value()=='AIAGT'
    if settings.sage_writes_enabled:raise RuntimeError()
    if '--live' in sys.argv:
        import httpx
        with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=5,headers={'X-Approval-Token':settings.approval_token.get_secret_value()}) as client:
            for i in range(20):
                try:
                    health=client.get('/health')
                    if health.status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(1)
            sec=client.get('/api/v1/sage/security')
            if sec.status_code==200 and sec.json().get('ready') is False:
                result['http_423']=client.post('/api/v1/sage/articles',json={}).status_code==423
except Exception:pass
if '--live' in sys.argv:
    (ROOT/'logs/aiagt-provisioning-result.json').write_text(json.dumps(result),encoding='utf-8')
print(json.dumps(result))
raise SystemExit(0 if all(result[k] for k in (result if '--live' in sys.argv else ['dpapi_created','path_validated','decryption_ok','fastapi_can_load'])) else 1)
