import argparse
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from dotenv import set_key
from app.core.config import settings
from app.services import business_store as db
parser=argparse.ArgumentParser()
parser.add_argument('--folder', choices=('TEST','OB'), default='TEST')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
with db.connection() as conn:
    row=conn.execute('SELECT id FROM chat_accounts WHERE email=%s',(settings.gmail_user.lower(),)).fetchone()
owner=str(row['id']) if row else str(uuid5(NAMESPACE_URL,'supplier-mail:'+settings.gmail_user.lower()))
for key,value in {'SMTP_HOST':'smtp.gmail.com','SMTP_PORT':'587','IMAP_HOST':'imap.gmail.com','IMAP_PORT':'993','SUPPLIER_MAIL_FOLDER':args.folder,'SUPPLIER_MAIL_OWNER_ID':owner,'SUPPLIER_MAIL_POLL_SECONDS':'30'}.items():
    set_key(root/'.env',key,value)
print('Mail configuration saved; folder='+args.folder+'; dedicated_owner='+str(not bool(row)))
