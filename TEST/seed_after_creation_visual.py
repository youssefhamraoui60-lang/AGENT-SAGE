"""Seed a creation-history fixture in an isolated visual-test account only."""
import sys
from pathlib import Path
from uuid import UUID,uuid4
from psycopg.types.json import Jsonb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import business_store as db
owner,conversation=map(UUID,sys.argv[1:])
state={'articles':[],'partners':[{'id':str(uuid4()),'kind':'supplier','nom':'CASA TECH TEST','ville':'Casablanca','forme_juridique':'SARL AU','operation':{'status':'succeeded','record_keys':{'BPSNUM':'F10037'},'result':{'supplier_verification':{'code':'F10037'}}}}],'supplier_tasks':{'version':1,'active':'create','group':{'expected_count':1},'history':[],'control':None},'active_supplier_task':'create'}
with db.connection() as conn:
    user=conn.execute('SELECT email,display_name FROM chat_accounts WHERE id=%s',(owner,)).fetchone()
    assert user and user['email'].startswith('ui-deepseek-after-') and user['email'].endswith('@example.test') and user['display_name']=='Youssef Test'
    row=conn.execute('SELECT state FROM chat_conversations WHERE id=%s AND owner_id=%s',(conversation,owner)).fetchone()
    assert row and not row['state'].get('partners') and not row['state'].get('_pending')
    conn.execute("UPDATE chat_conversations SET state=%s,revision=revision+1,title='TEST · Création confirmée F10037',updated_at=now() WHERE id=%s AND owner_id=%s",(Jsonb(state),conversation,owner))
print('Isolated creation-history fixture seeded; no Sage writes.')
