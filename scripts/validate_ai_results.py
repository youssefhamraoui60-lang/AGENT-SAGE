"""Compare synthetic test outputs against explicit fields, without changing outputs."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
results=json.loads((root/'logs/ollama-tests.json').read_text(encoding='utf-8-sig'))
expected={
    1:dict(designation='Etalonnage Balance 2T avec attestation de labo',unite=None,categorie='FG',fournisseur='PARTENAIRE SCALE Sarl'),
    2:dict(designation='Câble souple 4x50 mm RVK NOIR',unite=None,categorie='FG',fournisseur='SOTAMO'),
    3:dict(designation='POLYSTER 3 CM',unite='M3',categorie='MARCH',fournisseur='ISONIMA'),
}
checks=[]
for result in results:
    mismatches={key:{'expected':value,'actual':result.get('json',{}).get(key)}
                for key,value in expected[result['test']].items()
                if not result.get('schema_valid') or result['json'].get(key)!=value}
    checks.append(dict(test=result['test'],essai=result['essai'],status='FAIL' if mismatches else 'PASS',mismatches=mismatches))
(root/'logs/ai-semantic-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
passed=sum(x['status']=='PASS' for x in checks)
print(f'Exactitude champs explicites: {passed}/9 PASS')
raise SystemExit(0 if passed==9 else 1)
