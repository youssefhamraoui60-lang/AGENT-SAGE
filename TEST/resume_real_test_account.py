"""Reactivate only this campaign's generated test account for a guarded resume."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import business_store as db
plan=json.loads((ROOT/'TEST/real-write-campaign/review-plan.json').read_text(encoding='utf-8'))
with db.connection() as c:
 row=c.execute('SELECT a.id,a.email,a.display_name FROM chat_accounts a JOIN chat_conversations x ON x.owner_id=a.id WHERE x.id=%s',(plan['entries'][0]['conversation'],)).fetchone()
 assert row['email'].startswith('ui-real-writes-') and row['email'].endswith('@example.test') and row['display_name']=='Youssef Test'
 c.execute('UPDATE chat_accounts SET active=true WHERE id=%s',(row['id'],))
print('Isolated real-write test account resumed; no Sage changes.')
