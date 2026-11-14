"""Fixed SELECT snapshots and local receipts for the SOB quality audit."""
import concurrent.futures,json,sqlite3,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runtime/sob-quality-audit-20261112'
OUT.mkdir(parents=True,exist_ok=True)
KINDS=['orders','test_orders_audit','customers','customer_identities','articles','representatives','article_sites','test_customers','test_articles','packaging']
def one(kind):
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'telegram-test/audit-read.ps1')],input=json.dumps({'kind':kind,'start':'2026-11-10','end':'2026-11-13'}),capture_output=True,text=True,encoding='utf-8',timeout=90)
    value=json.loads(p.stdout.lstrip('\ufeff'))
    if not value.get('ok'):raise RuntimeError('Snapshot failed: '+kind)
    (OUT/('ob-'+kind+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'kind':kind,'rows':len(value['rows'])}),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:list(ex.map(one,KINDS))
for name,db,tables in [('agent',ROOT/'runtime/sob-orders.sqlite3',['reviews','sob_preparations']),('routing',ROOT/'runtime/sob-telegram-routing.sqlite3',['batches','source_messages'])]:
    with sqlite3.connect(db) as c:
        c.row_factory=sqlite3.Row
        for table in tables:
            data=[dict(r) for r in c.execute('SELECT * FROM '+table)]
            (OUT/(name+'-'+table+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Read-only snapshot complete')
