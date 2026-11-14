"""Read-only Python integration check; never dispatches SAVE or changes credentials."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.services.sage_gateway import Gateway
from app.services.sage_soap import SageError
from app.services.sage_crud import security

report = {'at':datetime.now(timezone.utc).isoformat(), 'save_attempts':0,
          'article':'TESTSOAP003', 'folder':'TEST', 'steps':[]}
try:
    gateway = Gateway('articles')
    description = gateway.describe()
    report['steps'].append({'operation':'getDescription','status':1,
                            'folder':description.get('FOL'),'user':description.get('USER')})
    record = gateway.read({'ITMREF':'TESTSOAP003'})
    report['steps'].append({'operation':'read','status':record['status'],'exists':record['exists']})
    report['status'] = 'READ_CONFIRMED' if record['exists'] else 'ARTICLE_NOT_FOUND'
except Exception as exc:
    report.update(status='READ_BLOCKED', error_code=exc.code if isinstance(exc,SageError) else type(exc).__name__)
report['security'] = security()
(ROOT/'logs/python-TESTSOAP003-read.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
