"""Read-only independent verification of the user-authorized TEST fixtures."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services import erp_modification as erp, supplier_sql
from app.services.modification_actions import current_values

directory = ROOT / 'TEST/real-write-campaign'
plan = json.loads((directory / 'review-plan.json').read_text(encoding='utf-8'))
result = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
assert result['phase'] == 'complete', 'Campaign not complete; inspect outcomes before retrying'
checks = []
for entry, saved in zip(plan['entries'], result['cases']):
    assert entry['name'] == saved['name'] and entry['name'].startswith('CXTEST ')
    code = saved['code']
    view = erp.snapshot('supplier', code)
    actual = current_values(view)
    assert view['folder'] == 'TEST'
    assert len(view['partners']) == len(view['suppliers']) == 1
    expected = {'name': entry['name'], 'city': entry['parameters']['Ville'],
                'payment': entry['parameters']['Paiement'], 'phone': '',
                'ice': '', 'if': '', 'rc': ''}
    expected.update(entry['modification_after_creation'])
    for key, value in expected.items():
        assert (actual[key] or '').strip() == value, (code, key, actual[key], value)
    address = ' '.join(entry['parameters'].get(k, '').strip() for k in ['Adresse', 'Adresse2', 'Adresse3']).strip()
    assert actual['address'] == address, (code, 'address')
    assert view['suppliers'][0]['BPSNAM_0'].strip() == expected['name']
    checks.append({'code': code, 'folder': 'TEST', 'verified': True, 'values': actual})
out = {'real_creations': len(checks), 'real_modifications': len(checks),
       'independent_sql_readback': checks, 'production_writes': 0}
(directory / 'independent-readback.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'verified_codes': [r['code'] for r in checks], 'folder': 'TEST'}))
