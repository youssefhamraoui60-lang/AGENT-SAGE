"""Read-only preparation of the exact screenshot request. Never executes INSERT."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners
text='Bonjour, veuillez procéder à la création du fournisseur CASA INDUSTRIE.\n\nICE : 001234567890123\n\nMerci.'
delta,grounding=extract(text,{})
state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
message=prepare_state(state)
report={'sage_inserts':0,'message':message,'partners':state['partners']}
(ROOT/'TEST/verification-casa-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(message)
print(json.dumps({'name':state['partners'][0]['nom'],'ice':state['partners'][0]['ice'],
    'status':state['partners'][0].get('operation',{}).get('status')},ensure_ascii=False))
