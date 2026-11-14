"""Local PostgreSQL test schemas only; SQL Server, SOAP and subprocesses denied."""
import sys
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_offline_regression as boundary
import psycopg
from psycopg.conninfo import conninfo_to_dict
from app.core.config import settings

# The native C connector bypasses Python sockets. Check both its target and the
# fixture-owned schema before allowing a connection. No production schema allowed.
_connect=psycopg.Connection.connect
PREFIXES=('chat_test_','sage_ai_test_','agent_chat_test_','article_sites_',
          'ps_web_test_','sage_crud_test_','sage_draft_test_','evaluation_test_')


def isolated_connect(conninfo='',**kwargs):
    target=conninfo_to_dict(conninfo,**{k:v for k,v in kwargs.items() if k in ('host','port','dbname')})
    if target.get('host') not in ('127.0.0.1','localhost','::1') or target.get('port')!='55432' or target.get('dbname')!='agent_sage':
        raise RuntimeError('ISOLATED_PG_TARGET_DENIED')
    if not any(re.fullmatch(re.escape(prefix)+r'[0-9a-f]{12}',settings.business_schema) for prefix in PREFIXES):
        raise RuntimeError('ISOLATED_PG_SCHEMA_DENIED')
    return _connect(conninfo,**kwargs)


psycopg.connect=isolated_connect
os.environ['RUN_STEP2_INTEGRATION']='1'
if __name__=='__main__':
    os.chdir(ROOT/'backend')
    raise SystemExit(boundary.pytest.main(sys.argv[1:]))
