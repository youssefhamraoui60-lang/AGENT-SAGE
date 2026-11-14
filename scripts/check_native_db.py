import native_stack as stack
from urllib.parse import urlparse
from pathlib import Path
import sys
sys.path.insert(0,str(stack.ROOT/'backend'))
from app.core.config import settings
with stack.connect() as conn:
    print('Native application connection:',conn.execute('SELECT current_user, current_database()').fetchone())
import psycopg
try:
    with psycopg.connect(settings.database_url,connect_timeout=5) as conn:
        print('FastAPI settings connection:',conn.execute('SELECT 1').fetchone())
except psycopg.Error as exc:
    print('Settings connection exception type:',type(exc).__name__)
parsed=urlparse(settings.database_url)
print('Settings endpoint:',parsed.hostname,parsed.port,parsed.path)
