"""Real SELECT-only probes; no stock/account values are persisted as knowledge."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.learning_live import read
checks=[]
for kind,kwargs in [('code',{'code':'F10017'}),('stock',{'code':'__READ_PROBE__','site':'NONE'}),
                    ('balance',{'code':'__READ_PROBE__','company':'NONE','ledger':'NONE','date_from':'2026-11-01','date_to':'2026-11-02'})]:
    try:
        result=read(kind,**kwargs)
        checks.append({'kind':kind,'ok':result['ok'],'folder':result['folder'],'row_count':len(result['rows']),
            'checked_at':result['checked_at'],'writes':result['writes'],'training_excluded':result['training_excluded']})
    except Exception as exc:checks.append({'kind':kind,'ok':False,'error_type':type(exc).__name__})
(ROOT/'TEST/learning-live-results.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))
