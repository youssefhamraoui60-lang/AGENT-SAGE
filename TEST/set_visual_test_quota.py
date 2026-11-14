"""Adjust only the isolated browser-test account; never a real user's quota."""
import argparse,sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import business_store as db
parser=argparse.ArgumentParser();parser.add_argument('owner',type=UUID);parser.add_argument('limit',type=int,nargs='?');parser.add_argument('--deactivate',action='store_true');args=parser.parse_args()
assert args.deactivate or args.limit is not None and 1<=args.limit<=200*1024*1024
with db.connection() as conn:
    row=conn.execute('SELECT email,display_name FROM chat_accounts WHERE id=%s',(args.owner,)).fetchone()
    assert row and row['email'].endswith('@example.test') and ((row['email'].startswith('ui-') and row['display_name']=='Youssef Test') or (args.deactivate and row['email'].startswith('ui-article-') and row['display_name']=='Article Test') or (args.deactivate and row['email'].startswith('other-') and row['display_name']=='Autre compte'))
    if args.deactivate:
        conn.execute('UPDATE chat_accounts SET active=false WHERE id=%s',(args.owner,))
        conn.execute('DELETE FROM chat_web_sessions WHERE owner_id=%s',(args.owner,))
    else:conn.execute('UPDATE chat_storage_usage SET limit_bytes=%s WHERE owner_id=%s',(args.limit,args.owner))
print('Isolated visual-test quota adjusted.')
