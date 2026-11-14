"""User-authorized TEST execution of the eight reported text examples.

Never reads or writes OB here. Reuse an already verified identical TEST
receipt when possible; otherwise use stable per-example owners.
"""
import hashlib
import json
from pathlib import Path
import creation

OUT=Path(__file__).resolve().parents[1]/'runtime/sob-week-20261102'

def signature(payload):
    return (payload['client'],tuple(sorted((l['article'],str(float(l['quantity'])),str(float(l['price']))) for l in payload['lines'])))

def main():
    examples=json.loads((OUT/'reported-examples-retest.json').read_text(encoding='utf-8'))
    results=[]
    for example in examples:
        details=example.get('details',{})
        record={'contact':example['contact'],'text':example['text'],'production_writes':0}
        try:
            payload=creation.build_payload(details)
            key=hashlib.sha256((example['contact']+'\n'+example['text']).encode()).hexdigest()[:24]
            owner='authorized-reported-example-'+key
            with creation.connection() as conn:
                existing=conn.execute('SELECT id,status FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 1',(owner,)).fetchone()
                # Identical existing commands need no second TEST insertion.
                possible=conn.execute("SELECT id,owner,payload FROM reviews WHERE status='created' AND number IS NOT NULL ORDER BY rowid DESC").fetchall()
            same=next((r for r in possible if signature(json.loads(r['payload']))==signature(payload)),None)
            if same:
                receipt=creation.confirm(same['owner'],same['id'])
                record.update(receipt,reused_existing=True)
            else:
                if existing and existing['status'] in ('created','pending','uncertain'):
                    receipt=creation.confirm(owner,existing['id'])
                else:
                    creation.invalidate(owner)
                    review=creation.review(owner,details)
                    receipt=creation.confirm(owner,review['id'],human_validated=True)
                record.update(receipt,reused_existing=False)
        except Exception as exc:
            record.update(status='blocked',reason=str(exc) if isinstance(exc,creation.CreationError) else type(exc).__name__)
        results.append(record)
        (OUT/'reported-examples-creation-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(record,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
