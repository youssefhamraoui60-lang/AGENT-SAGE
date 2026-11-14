"""Independent SELECT readback of every claimed successful TEST receipt."""
import collections
from decimal import Decimal
import json
from pathlib import Path
import creation

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-week-20261102'

def main():
    results=json.loads((OUT/'historical-creation-results.json').read_text(encoding='utf-8'))
    expected={}
    for item in results:
        if item.get('status')!='created':continue
        with creation.connection() as conn:
            row=conn.execute("SELECT payload FROM reviews WHERE number=? AND status='created' ORDER BY rowid DESC LIMIT 1",(item['number'],)).fetchone()
        if row is None:raise RuntimeError('Reçu ledger absent : '+item['number'])
        expected[item['number']]=json.loads(row['payload'])
    response=creation.run_script('audit-read.ps1',{'kind':'created_test_orders','references':[p['reference'] for p in expected.values()]})
    if not response.get('ok'):raise RuntimeError('SELECT indépendant TEST indisponible')
    actual=collections.defaultdict(list)
    for row in response['rows']:actual[row['SOHNUM_0']].append(row)
    checked=[]
    for number,payload in expected.items():
        rows=actual.get(number,[])
        match=bool(rows) and len(rows)==len(payload['lines'])
        if match:
            match=rows[0]['BPCORD_0'].strip()==payload['client'] and rows[0]['REP_0'].strip()==payload['representative'] and rows[0]['CUSORDREF_0'].strip()==payload['reference']
            want=sorted((l['article'],Decimal(l['quantity']),Decimal(l['price'])) for l in payload['lines'])
            got=sorted((r['ITMREF_0'].strip(),Decimal(str(r['QTY_0'])),Decimal(str(r['NETPRIATI_0']))) for r in rows)
            match=match and want==got and abs(Decimal(str(rows[0]['ORDATI_0']))-Decimal(payload['total']))<=Decimal('.05')
        checked.append({'number':number,'verified':match,'rows':len(rows)})
    report={'orders':len(checked),'verified':sum(r['verified'] for r in checked),'failures':[r for r in checked if not r['verified']],'details':checked,'select_only':True}
    (OUT/'test-readback-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='details'}))
    if report['failures']:raise SystemExit(1)

if __name__=='__main__':main()
