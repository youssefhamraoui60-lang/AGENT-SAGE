"""Read only: inspect saved confirmation and the already-created TEST supplier."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import business_store as db
with db.connection() as conn:
    rows=conn.execute("""SELECT p->'operation' AS operation FROM chat_conversations c,
        LATERAL jsonb_array_elements(COALESCE(c.state->'partners','[]'::jsonb)) p
        WHERE p->'operation'->'record_keys'->>'BPSNUM'=%s ORDER BY c.updated_at DESC LIMIT 1""",('F10017',)).fetchall()
report={'code':'F10017','saved_operations':[r['operation'] for r in rows]}
(ROOT/'TEST/verification-F10017.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:
    op=r['operation'];proof=op.get('result',{}).get('supplier_verification') or {}
    print(json.dumps({'status':op.get('status'),'transport':op.get('transport'),'resource':op.get('resource'),
        'action':op.get('action'),'result_status':op.get('result',{}).get('status'),
        'code':proof.get('code'),'confirmed':proof.get('confirmed'),'comparisons':proof.get('comparisons'),
        'after_record':op.get('after_record'),'readback':proof.get('sql_readback'),'errors':proof.get('errors')},ensure_ascii=False))
