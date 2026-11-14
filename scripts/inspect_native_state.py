"""Read-only evidence for the project's PostgreSQL cluster and local services."""
import json
from datetime import datetime, timezone
import httpx
import native_stack as stack

proof={'time_utc':datetime.now(timezone.utc).isoformat()}
with stack.connect('postgres',admin=True) as conn:
    proof['postgres_version']=conn.execute('SHOW server_version').fetchone()[0]
    proof['listen_addresses']=conn.execute('SHOW listen_addresses').fetchone()[0]
    proof['password_encryption']=conn.execute('SHOW password_encryption').fetchone()[0]
    proof['application_roles']=[dict(name=row[0],superuser=row[1],createdb=row[2],createrole=row[3])
        for row in conn.execute("SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname IN ('agent','n8n') ORDER BY rolname")]
with stack.connect('n8n',admin=True) as conn:
    proof['n8n_workflows']=[dict(id=row[0],name=row[1],active=row[2])
        for row in conn.execute('SELECT id,name,active FROM workflow_entity ORDER BY id')]
with httpx.Client(timeout=10) as client:
    proof['http']={url:client.get(url).status_code for url in [
        'http://127.0.0.1:8000/health','http://127.0.0.1:8000/health/db',
        'http://127.0.0.1:8000/health/ollama','http://127.0.0.1:5678/healthz/readiness',
        'http://127.0.0.1:5678/','http://127.0.0.1:11434/api/tags']}
(stack.ROOT/'logs/native-final-state.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False,indent=2))
