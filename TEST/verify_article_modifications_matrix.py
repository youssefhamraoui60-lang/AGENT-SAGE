"""Real TEST snapshot and read-only preparation, never approval or execution."""
import sys,json,copy
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import erp_modification as service,sage_crud as crud

code='GEN_BAT_IT780_XLL';schema=service.catalog();view=service.snapshot('article',code)
cases={
 'desactivation':{'deactivate':True},
 'stock_negatif_interdit':{'allow_negative_stock':False},
 'stock_negatif_autorise':{'allow_negative_stock':True},
 'gere_en_stock':{'stock_mode':2},
 'non_gere_en_stock':{'stock_mode':1},
 'vente_avec_trois_fournisseurs_sans_principal':{'sale_enabled':True,'add_suppliers':[{'code':c,'reference':''} for c in ('F007','F552','F889')]},
 'desactivation_vente':{'sale_enabled':False},
 'code_comptable_CPJ35':{'accounting':'CPJ35'},
 'niveau_TVA_T10':{'tax_level':{'index':0,'code':'T10'}},
}
report={'folder':'TEST','code':code,'sage_writes':0,'cases':[]}
for name,changes in cases.items():
 d={'id':str(uuid4()),'resource':'article','folder':'TEST','code':code,'changes':changes}
 try:
  result=service.prepare(d,copy.deepcopy(schema),copy.deepcopy(view))
  preview=result['preview']
  assert not preview.get('executed') and preview.get('transaction_state')=='VALIDATED_NO_WRITE'
  entry={'case':name,'changes':changes,'status':result['status'],'diff':result['plan']['diff'],'executed':False}
 except crud.CrudError as error:
  entry={'case':name,'changes':changes,'status':'blocked_or_unchanged','reason':error.code,'executed':False}
 report['cases'].append(entry)
 print(json.dumps(entry,ensure_ascii=True),flush=True)
Path(__file__).with_name('article-modifications-matrix-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: all actual preparation outcomes recorded; no Sage writes.',flush=True)
