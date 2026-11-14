"""Controlled live TEST write, with the production mail channel left stopped."""
import asyncio,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import supplier_mail as mail,conversation_chat as chat
from app.core.config import settings
from uuid import UUID
root=Path(__file__).resolve().parents[1]
report={'folder':'TEST','production_writes':0,'imap':mail.check_connection()}
identifier=None
def checkpoint(value):
    global identifier
    identifier=value
async def run():
    name='TEST MAIL '+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    report['supplier_name']=name
    message='Créer le fournisseur '+name+'. Adresse : 10 RUE TEST. Ville : Casablanca. Téléphone : 0522000001.'
    report['creation']=await mail.process_text(message,'TEST',checkpoint)
    if report['creation']['status']!='succeeded':return
    code=report['creation']['operations'][0]['keys']['BPSNUM']
    report['modification']=await mail.process_text('Modifier le téléphone du fournisseur '+code+' : 0522000002.','TEST',checkpoint)
try:
    asyncio.run(run())
except Exception as exc:
    report['error_type']=type(exc).__name__;report['error']=str(exc)
    if identifier:
        session=chat.read(UUID(settings.supplier_mail_owner_id),identifier)
        report['conversation']=str(identifier);report['state']=session['state']
        report['last_response']=session['messages'][-1]['content']
(root/'TEST/supplier-mail-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,default=str))
