"""Real backend permission check and preview ONLY. Never calls execute=True."""
import sys,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import supplier_sql as sql
from app.services.sage_crud import CrudError

raw=json.loads((ROOT/'TEST/supplier.example.json').read_text(encoding='utf-8'))
partner={field:raw[key] for key,field in sql.MAPPING.items()}
partner.update(kind='supplier',dossier_cible='TEST',fax=raw['Fax'],type_montant_valeur=raw['TypeMontant'])
report={'at':datetime.now(timezone.utc).isoformat(),'folder':'TEST','mode':'PREPARE_ONLY','sage_inserts':0}
report['security']=sql.security(force=True)
report['parameters']=sql.parameters(partner)
try:report['preparation']=sql.run(report['parameters'],execute=False)
except CrudError as exc:report['preparation']={'ok':False,'error':exc.code}
if report['preparation'].get('code')=='sql_validation_rejected':
    report['preparation']['message']=sql.preparation_message(report['preparation'])
report['chat']={'route':'/api/v1/chat/conversations/{conversation}/partners/{partner}/prepare',
    'parameters_visible_before_confirmation':True,'approval_required':True}
(ROOT/'TEST/verification-telfix-backend.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
