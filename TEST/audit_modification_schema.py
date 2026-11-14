"""Read-only TEST metadata; no permission changes or Sage DML."""
import sys,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services.supplier_sql import connection_env
p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/modification_worker.ps1')],input=json.dumps({'folder':'TEST','action':'catalog','execute':False}),env=connection_env('TEST'),capture_output=True,text=True,encoding='utf-8',timeout=65)
r=json.loads(p.stdout.lstrip('\ufeff'));assert r.get('ok'),r
(ROOT/'TEST/modification-schema-audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tables':len(r['tables']),'columns':len(r['columns']),'triggers':r.get('triggers',[]),'permissions':[x for x in r['permissions'] if x['table'] in ('ITMMASTER','ITMFACILIT','ITMBPS','ITMSALES','ATEXTRA','BPARTNER','BPSUPPLIER','BPADDRESS','TABUNIT','TABCOEFF')]}))
