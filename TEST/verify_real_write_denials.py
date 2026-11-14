"""Real TEST validation previews only: never executes a Sage write."""
import copy, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services import supplier_sql, erp_modification
from app.services.modification_actions import prepare_draft, current_values
directory = ROOT / 'TEST/real-write-campaign'
plan = json.loads((directory / 'review-plan.json').read_text(encoding='utf-8'))
results = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
assert results['phase'] == 'complete'
first = results['cases'][0]
before = current_values(erp_modification.snapshot('supplier', first['code']))
preview = supplier_sql.run(plan['entries'][0]['parameters'], execute=False)
assert preview.get('ok') is False or preview.get('duplicate_warnings'), 'Duplicate must be rejected'
draft = copy.deepcopy(first['modification'])
draft['changes'] = {'city': 'X' * 100}
prepare_draft(draft)
assert draft['operation']['status'] == 'blocked', draft['operation']['status']
after = current_values(erp_modification.snapshot('supplier', first['code']))
assert before == after
out = {'folder': 'TEST', 'code': first['code'], 'duplicate_preview_rejected': True,
       'oversize_city_rejected': True, 'record_unchanged': True,
       'sage_writes_in_this_check': 0, 'invalid_update_message': draft['operation'].get('message')}
(directory / 'validation-denials.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False))
