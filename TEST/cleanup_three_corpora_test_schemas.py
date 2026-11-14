"""Remove only abandoned fixtures proven to belong to this exact corpus run."""
import sys,json,re
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'backend'))
from app.services import business_store as db
from psycopg import sql
from three_supplier_corpora import cases
cutoff=datetime.fromtimestamp((ROOT/'three_supplier_corpora.py').stat().st_mtime,timezone.utc)
starts={case['steps'][0]['text'] for case in cases()};dropped=[];skipped=[]
with db.connection() as conn:
 names=conn.execute("SELECT nspname FROM pg_namespace WHERE nspname ~ '^chat_test_[0-9a-f]{12}$'").fetchall()
 for row in names:
  name=row['nspname']
  if not re.fullmatch(r'chat_test_[0-9a-f]{12}',name):continue
  if not conn.execute('SELECT to_regclass(%s) AS tab',(name+'.chat_accounts',)).fetchone()['tab']:continue
  accounts=conn.execute(sql.SQL('SELECT email,display_name,created_at FROM {}.chat_accounts').format(sql.Identifier(name))).fetchall()
  owned=len(accounts)==1 and accounts[0]['created_at']>=cutoff and re.fullmatch(r'test-[0-9a-f]+@example.test',accounts[0]['email']) and accounts[0]['display_name']=='Utilisateur Test'
  if not owned:skipped.append(name);continue
  messages=conn.execute(sql.SQL("SELECT content FROM {}.chat_messages WHERE role='user' ORDER BY id LIMIT 1").format(sql.Identifier(name))).fetchall()
  if not messages or messages[0]['content'] not in starts:skipped.append(name);continue
  conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)));dropped.append(name)
result={'dropped_task_fixture_schemas':dropped,'unrelated_schemas_untouched':skipped,'sage_writes':0}
(ROOT/'three-corpora-schema-cleanup.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
