"""Checkpointed full-week replay. OB reads only; never confirms or inserts orders.

Grouping and inferred OB counterparts remain review candidates, not training truth.
"""
import asyncio
import collections
import contextvars
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import prepare as agent
from reference_snapshot import ReferenceSnapshot
from telegram_batch import contact_name
from app.services import ai_provider
from app.core.config import settings
import learning_memory as memory
from psycopg.types.json import Jsonb

OUT=ROOT/'runtime/sob-week-20261102'

def sql_day(value):
    match=re.fullmatch(r'/Date\((\d+)\)/',str(value))
    return datetime.fromtimestamp(int(match[1])/1000,ZoneInfo('Europe/Paris')).date().isoformat() if match else str(value)[:10]

def quantities(rows,article,quantity):
    result=collections.defaultdict(Decimal)
    for row in rows:
        if row.get(quantity) is not None:
            result[row[article].strip()]+=Decimal(str(row[quantity]))
    return dict(result)

def groups(messages):
    """Preserve every message once; close messages are provisional batches."""
    result=[]
    for row in messages:
        who=contact_name(row['text'])
        previous=result[-1] if result else None
        if previous:
            last=previous[-1]
            seconds=(datetime.fromisoformat(row['date'])-datetime.fromisoformat(last['date'])).total_seconds()
            same=(who and who==contact_name(last['text'])) or (row.get('grouped_id') and row['grouped_id']==last.get('grouped_id'))
            if row['sender_id']==last['sender_id'] and same and seconds<=30:
                previous.append(row)
                continue
        result.append([row])
    assert sorted(r['id'] for batch in result for r in batch)==sorted(r['id'] for r in messages)
    return result

async def main():
    source=json.loads((OUT/'messages-decoded.json').read_text(encoding='utf-8'))
    batches=groups(source)
    remaining='--remaining' in sys.argv
    if remaining:
        source=json.loads((OUT/'messages-visual.json').read_text(encoding='utf-8'))
        by_id={r['id']:r for r in source}
        unresolved={i for r in json.loads((OUT/'import-linkage.json').read_text(encoding='utf-8'))['outcomes'] if r['status']!='linked' for i in r['message_ids']}
        rules=memory.approved_rules()
        excluded=next((r['payload'].get('value',[]) for r in rules if r['kind']=='policy' and r['rule_key']=='telegram_creation_excluded_contacts'),[])
        previous=json.loads((OUT/'evaluation-final.json').read_text(encoding='utf-8'))
        batches=[[by_id[i] for i in r['message_ids']] for r in previous if unresolved.intersection(r['message_ids']) and not any(contact_name(by_id[i]['text']) in excluded for i in r['message_ids'])]
    snapshot=ReferenceSnapshot(OUT)
    agent.lookup=snapshot
    settings.ai_fallback_provider='none'
    checkpoint=OUT/'evaluation-week.json'
    if remaining:checkpoint=OUT/'evaluation-remaining-fresh.json'
    replay='--replay' in sys.argv
    cached=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else []
    if '--from-fresh' in sys.argv:
        if not replay:raise ValueError('--from-fresh requires --replay')
        cached=json.loads((OUT/'evaluation-remaining-fresh.json').read_text(encoding='utf-8'))
    if replay:
        extracted_cache={r['message_ids'][0]:r.get('extracted') for r in cached}
        batches=[b for b in batches if extracted_cache.get(b[0]['id'])]
        checkpoint=OUT/('evaluation-final.json' if '--final' in sys.argv else 'evaluation-corrected.json')
        if '--refresh' in sys.argv:checkpoint=OUT/'evaluation-refreshed.json'
        if '--from-fresh' in sys.argv:checkpoint=OUT/'evaluation-remaining-corrected.json'
    results=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else []
    done={tuple(r['message_ids']) for r in results}
    ob=collections.defaultdict(list)
    for row in snapshot.orders:ob[row['SOHNUM_0']].append(row)
    original=ai_provider.complete
    current=contextvars.ContextVar('case')
    extracted={}
    async def capture(*args,**kwargs):
        response={'message':{'content':json.dumps(extracted_cache[current.get()])}} if replay else await original(*args,**kwargs)
        extracted[current.get()]=json.loads(response['message']['content'])
        return response
    ai_provider.complete=capture
    semaphore=asyncio.Semaphore(4)
    async def run(batch):
        ids=[r['id'] for r in batch]
        if tuple(ids) in done:return
        async with semaphore:
            current.set(ids[0])
            text='\n\n'.join(r['text']+('\nDOCUMENT JOINT:\n'+r.get('layout_text',r.get('attachment_text','')) if r.get('layout_text',r.get('attachment_text','')) else '') for r in batch)
            item={'message_ids':ids,'source_date':batch[0]['date'],'grouping':'provisional_30s','sage_writes':0}
            try:
                details=await asyncio.wait_for(agent.prepare([{'role':'user','content':text}],details=True,reference_folder='OB',reference_date=date.fromisoformat(batch[0]['date'][:10])),180)
                item.update(ok=True,details=details,extracted=extracted.get(ids[0]))
                client=(details.get('client') or {}).get('BPCNUM_0','').strip()
                actual=quantities(details['lines'],'article','quantity')
                candidates=[]
                for number,lines in ob.items():
                    if lines[0]['BPCORD_0'].strip()!=client or sql_day(lines[0]['ORDDAT_0'])!=batch[0]['date'][:10]:continue
                    expected=quantities(lines,'ITMREF_0','QTY_0')
                    overlap=len(set(actual)&set(expected))
                    if overlap:candidates.append({'number':number,'exact_quantities':actual==expected,'overlap':overlap,'representative':lines[0]['REP_0']})
                candidates.sort(key=lambda r:(r['exact_quantities'],r['overlap']),reverse=True)
                item['ob_candidates']=candidates
                exact=[r for r in candidates if r['exact_quantities']]
                item['unique_structural_match']=len(exact)==1
                item['attachment_uncertain']=any(p.get('uncertain') for r in batch for p in r.get('attachment_decode',{}).get('pages',[]))
            except Exception as exc:
                item.update(ok=False,error=type(exc).__name__,extracted=extracted.get(ids[0]))
            results.append(item)
            temporary=checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps(sorted(results,key=lambda r:r['message_ids'][0]),ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(checkpoint)
            # Inferred references are explicitly review candidates, never approved rules.
            try:
                with memory.db.connection() as conn:
                    conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET expected=EXCLUDED.expected,observed=EXCLUDED.observed,status=EXCLUDED.status''',
                        ('sob-week-'+','.join(map(str,ids)),Jsonb(batch),Jsonb({'ob_candidates':item.get('ob_candidates',[]),'label_status':'unverified'}),Jsonb(item),'needs_review'))
            except Exception as exc:item['memory_error']=type(exc).__name__
            print(json.dumps({'done':len(results),'total':len(batches),'ids':ids,'ok':item['ok'],'match':item.get('unique_structural_match'),'missing':item.get('details',{}).get('missing_fields',[])},ensure_ascii=False),flush=True)
    print(json.dumps({'messages':len(source),'batches':len(batches),'cached':len(done)}),flush=True)
    await asyncio.gather(*(run(batch) for batch in batches))

if __name__=='__main__':asyncio.run(main())
