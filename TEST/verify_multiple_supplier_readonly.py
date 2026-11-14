"""Read TEST and validate a supplier addition; never send an execute request."""
import sys,json
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import erp_modification as service, sage_crud as crud
code='MAIN_LAFARGE3K';view=service.snapshot('article',code);schema=service.catalog()
existing=[str(p['BPSNUM_0']).strip() for p in view['article_suppliers']]
assert 'F007' in existing and 'F552' not in existing
draft={'id':str(uuid4()),'folder':'TEST','resource':'article','code':code,'changes':{'add_suppliers':[{'code':'F552','reference':''}]}}
try:
 operation=service.prepare(draft,schema,view)
 report={'status':operation['status'],'preview':operation['preview'],'diff':operation['plan']['diff']}
 assert operation['preview']['executed'] is False
except crud.CrudError as error:
 report={'status':'blocked','reason':error.code}
report.update(article=code,existing_suppliers=existing,requested_supplier='F552',sage_writes=0)
Path(__file__).with_name('multiple-supplier-readonly-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
