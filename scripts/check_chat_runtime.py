"""Read-only runtime and frontend secret-exposure checks for the local chat release."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services import sage_crud,chat_tools,business_store

result={'checked_at':datetime.now(timezone.utc).isoformat(),'sage_writes':0,'checks':{}}
with httpx.Client(timeout=15,trust_env=False) as client:
    for name,url in {
        'fastapi':'http://127.0.0.1:8000/health',
        'postgresql':'http://127.0.0.1:8000/health/db',
        'ollama':'http://127.0.0.1:8000/health/ollama',
        'n8n':'http://127.0.0.1:5678/healthz/readiness',
        'chat_page':'http://127.0.0.1:8000/sage/',
    }.items():
        response=client.get(url)
        result['checks'][name]={'http_status':response.status_code,'ok':response.status_code==200}
result['sage_write_security']=sage_crud.security()
assets=[p for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()]
values=[settings.approval_token.get_secret_value(),settings.sage_soap_password.get_secret_value()]
found=any(v.encode() in p.read_bytes() for p in assets for v in values if v)
result['checks']['frontend_server_secrets_absent']={'ok':not found,'files_checked':len(assets)}
result['controlled_select_tools']=sorted(chat_tools.TOOLS)
with business_store.connection() as conn:
    row=conn.execute('SELECT version,sha256 FROM schema_migrations WHERE version=%s',('007-conversation-chat',)).fetchone()
result['checks']['chat_migration_installed']={'ok':bool(row),'version':row['version'] if row else None}
result['status']='PASS' if all(c['ok'] for c in result['checks'].values()) else 'FAILED'
(ROOT/'logs/chat-runtime-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
