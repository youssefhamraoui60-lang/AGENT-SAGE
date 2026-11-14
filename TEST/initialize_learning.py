"""Additive local learning setup; no Sage connection, no automatic validation."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import learning,learning_training,knowledge,business_store as db
with db.connection() as conn:learning.ensure(conn)
identifier=knowledge.index_document(ROOT/'knowledge/assistant-test-guide.md',ROOT/'knowledge',reviewed=False)
report={'capability':learning_training.capability(),'initial_document_id':identifier,'document_status':'pending',
        'memory_database':'existing PostgreSQL application schema','sage_writes':0,'training_performed':False}
(ROOT/'TEST/learning-installation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
