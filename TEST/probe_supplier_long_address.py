"""Real SQL validation with execute=False only; no supplier is created."""
import sys,json
from uuid import uuid4
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import supplier_sql as sql
partner={'nom':'AUTOR AUTO SARL AU','adresse':'BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF','identifiant_fiscal':'66977576','ice':'003735377000086','telephone':'0707001002','dossier_cible':'TEST'}
values=sql.parameters(partner)
assert ''.join(values[k] for k in ('Adresse','Adresse2','Adresse3'))==partner['adresse']
body=sql.run(values,execute=False,folder='TEST')
assert body.get('transaction_after')=='0:0',body
assert body.get('ok') or body.get('sql_error_number')==50109,body
assert body.get('sql_error_number')!=50105
proof={'sage_writes':0,'execute':False,'address':partner['adresse'],'lines':{k:values[k] for k in ('Adresse','Adresse2','Adresse3')},'validation':body}
unique={**partner,'nom':'PREVIEW ADRESSE '+uuid4().hex[:8].upper(),'ice':'','identifiant_fiscal':''}
positive=sql.run(sql.parameters(unique),execute=False,folder='TEST')
assert positive.get('ok') and positive.get('transaction_after')=='0:0' and positive['rows'][0]['RESULTAT']=='VALIDATED_NO_INSERT',positive
proof['independent_preview_validation']=positive
(ROOT/'TEST/supplier-long-address-sql-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'execute':False,'sage_writes':0,'lines':proof['lines'],'ok':body.get('ok'),'sql_error_number':body.get('sql_error_number'),'transaction_after':body.get('transaction_after')},ensure_ascii=False))
