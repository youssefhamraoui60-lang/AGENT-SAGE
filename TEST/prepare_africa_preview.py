"""Read-only preparation with RC and explicitly supplied fiscal regularity date."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners
text='Créer un fournisseur AFRICA DISTRIBUTION SARL\nICE : 004567890123456\nIF : 45678912\nRC : 15342 Date de régularité fiscale : 15/09/2026'
delta,grounding=extract(text,{})
state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
reply=prepare_state(state)
report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
(ROOT/'TEST/verification-africa-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
p=state['partners'][0]
print(json.dumps({'nom':p['nom'],'rc':p['rc'],'date':p['date_regularite'],'status':p.get('operation',{}).get('status')},ensure_ascii=False))
print(reply)
