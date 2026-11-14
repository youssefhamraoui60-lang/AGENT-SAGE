"""Integration: dedicated project DB only. Run from backend with its venv."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import psycopg
from app.core.config import settings

mode=sys.argv[1]
marker_path=Path(__file__).resolve().parents[1]/'logs'/'persistence-marker.txt'
with psycopg.connect(settings.database_url,connect_timeout=5) as conn:
    for name in ['users','article_requests','supplier_requests','approval_requests','agent_execution_logs']:
        assert conn.execute('SELECT to_regclass(%s)',(name,)).fetchone()[0] is not None, name
    if mode=='prepare':
        marker='environment-test-'+uuid.uuid4().hex
        conn.execute('INSERT INTO agent_execution_logs(event) VALUES (%s)',(marker,))
        conn.commit()
        conn.execute('INSERT INTO users(username) VALUES (%s)',(marker,))
        conn.rollback()
        assert conn.execute('SELECT count(*) FROM users WHERE username=%s',(marker,)).fetchone()[0]==0
        marker_path.write_text(marker,encoding='utf-8')
    elif mode=='verify':
        marker=marker_path.read_text(encoding='utf-8')
        assert conn.execute('SELECT count(*) FROM agent_execution_logs WHERE event=%s',(marker,)).fetchone()[0]==1
    else:
        raise ValueError('prepare or verify required')
print('PASS tables, insertion/lecture et rollback' if mode=='prepare' else 'PASS persistance apres redemarrage')
