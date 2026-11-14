"""Exact user request, SQL preparation only; no real supplier creation."""
import json
from pathlib import Path
from test_supplier_nova import MESSAGE,parsed
from app.services.supplier_chat_flow import prepare_state
state={'partners':[parsed()]};reply=prepare_state(state)
report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
(Path(__file__).parent/'verification-nova-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
op=state['partners'][0].get('operation',{})
print(json.dumps({'status':op.get('status'),'parameters':op.get('parameters'),'reference_resolutions':op.get('reference_resolutions')},ensure_ascii=False,indent=2))
print(reply)
