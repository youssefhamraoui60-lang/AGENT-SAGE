"""Exact reported message, preparation only. No supplier INSERT."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners
message="Merci de créer le fournisseur MAGHREB SERVICES avec l'ICE 002345678901234 et le téléphone 0661234567."
delta,grounding=extract(message,{})
state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
reply=prepare_state(state)
report={'sage_inserts':0,'reply':reply,'partners':state['partners']}
(ROOT/'TEST/verification-maghreb-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
p=state['partners'][0]
print(json.dumps({k:p.get(k) for k in ('nom','ice','telephone')},ensure_ascii=False))
print(reply)
