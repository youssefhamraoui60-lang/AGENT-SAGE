"""Explicit authorized TEST-only test suite, idempotent per historical case.

References are resolved live in TEST. Historical OB prices are never inserted.
"""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import prepare
import creation
from app.services import ai_provider

async def main():
    out=ROOT/'runtime/sob-week-20261102'
    evaluation=json.loads((out/'evaluation-week.json').read_text(encoding='utf-8'))
    messages={r['id']:r for r in json.loads((out/'messages-decoded.json').read_text(encoding='utf-8'))}
    results=[]
    corrected='--correct-price-case' in sys.argv
    for message_id in ((4156,) if corrected else (4053,4102,4156)):
        owner=f'authorized-week-test-20261108-{message_id}'+('-price-fixed' if corrected else '')
        with creation.connection() as conn:
            receipt=conn.execute("SELECT number FROM reviews WHERE owner=? AND status='created'",(owner,)).fetchone()
        if receipt:
            results.append({'message_id':message_id,'number':receipt['number'],'already_created':True})
            continue
        item=next(r for r in evaluation if r['message_ids']==[message_id])
        async def cached(*args,**kwargs):return {'message':{'content':json.dumps(item['extracted'])}}
        ai_provider.complete=cached
        text=messages[message_id]['text']
        details=await prepare.prepare([{'role':'user','content':text}],details=True)
        details['delivery']=datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()
        details['delivery_note']=f'TEST EVAL SEMAINE 02-07/11 - message {message_id}'+(' PRIX CORRIGE - remplace test 14616' if corrected else '')
        try:
            review=creation.review(owner,details)
            receipt=creation.confirm(owner,review['id'])
            results.append({'message_id':message_id,'receipt':receipt,'details':details})
        except creation.CreationError as exc:
            results.append({'message_id':message_id,'error':str(exc),'missing':details['missing_fields']})
        (out/('test-price-corrected-receipt.json' if corrected else 'test-creation-receipts.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(results[-1],ensure_ascii=False),flush=True)

if __name__=='__main__':asyncio.run(main())
