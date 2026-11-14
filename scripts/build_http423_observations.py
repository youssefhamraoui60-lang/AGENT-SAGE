"""Record factual diagnostic evidence, never an authorization policy."""
import json,hashlib
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'logs/step4-crud-prerequisites.json'
live=json.loads(source.read_text(encoding='utf-8'))
proof={'recorded_at':datetime.now(timezone.utc).isoformat(),'kind':'AGENT_DIAGNOSTIC_ONLY_NOT_RIGHTS_OR_APPROVAL',
       'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
       'security':live['security'],'target':live['resources']['articles'],
       'approval_count':live['approvals'],'write_attempt_count':live['write_attempt_claimed'],
       'production_changes_applied':False,'dedicated_account_rights_verified':False,'conditional_business_rules_verified':False}
dest=ROOT/'config/security-evidence/agent-observations-2026-10-19.json'
dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
assert proof['approval_count']==0 and proof['write_attempt_count']==0
print('Diagnostic evidence recorded; not an authorization. Real approvals=0; real write attempts=0.')
