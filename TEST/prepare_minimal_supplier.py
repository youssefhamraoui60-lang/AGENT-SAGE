"""Read-only preparation of the reported minimal request; no execution."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.supplier_chat_flow import extract,prepare_state
from app.services import chat_partners
text='Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système :\nNom de frs : Izs.Tex\nIce :003224720000051'
delta,grounding=extract(text,{})
state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
message=prepare_state(state)
report={'sage_inserts':0,'message':message,'partners':state['partners']}
(ROOT/'TEST/verification-minimal-supplier.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
