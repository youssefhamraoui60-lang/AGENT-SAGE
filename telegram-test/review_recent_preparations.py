"""Replay recent documents for review only. Never calls creation.confirm."""
import asyncio
import csv
import json
import argparse
from datetime import date,datetime
from pathlib import Path
from telegram_batch import contact_name
from document_memory import decode
from read_documents_layout import read
from prepare import prepare
from creation import build_payload,run_script
import learning_memory

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-review-20261110'


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ids',nargs='*',type=int)
    parser.add_argument('--context',nargs='*',default=[])
    args=parser.parse_args()
    contexts={int(p.split(':')[0]):int(p.split(':')[1]) for p in args.context}
    messages=json.loads((OUT/'all-recent-test-messages.json').read_text(encoding='utf-8'))
    previous=OUT/'all-preparations-review.json'
    results=json.loads(previous.read_text(encoding='utf-8')) if args.ids and previous.exists() else []
    if args.ids:results=[r for r in results if r['message_id'] not in args.ids]
    rules=learning_memory.approved_rules()
    excluded=next((r['payload']['value'] for r in rules if r['rule_key']=='telegram_creation_excluded_contacts'),[])
    semaphore=asyncio.Semaphore(2)
    async def one(message):
        async with semaphore:
            mid=message['id']
            result={'message_id':mid,'date':message['date'],'document':message.get('file_name') or 'image',
                    'status':'to_review','client':'','missing':'','total_ttc':'','zero_price_articles':''}
            if contact_name(message['text']) in excluded:
                result.update(status='paused_by_user',missing='Contact Bouchaib : suspension conservée')
                results.append(result)
                return
            folder=ROOT/f'runtime/telegram-test/documents/-5586539927/{mid}'
            paths=[p for p in folder.glob('*') if p.suffix.lower() in ('.jpg','.pdf','.png')]
            try:
                if not paths:raise ValueError('local_file_missing')
                doc=await asyncio.to_thread(decode,paths[0],read)
                if not doc.get('ok'):raise ValueError('unreadable_document')
                text=message['text']+'\nDOCUMENT JOINT :\n'+doc['text']
                if mid in contexts:
                    note=next(m for m in messages if m['id']==contexts[mid])
                    gap=(datetime.fromisoformat(note['date'])-datetime.fromisoformat(message['date'])).total_seconds()
                    if contact_name(note['text'])!=contact_name(message['text']) or not 0<=gap<=120 or note['media']:
                        raise ValueError('unverified_context_link')
                    text+='\n\n'+note['text']
                d=await prepare([{'role':'user','content':text}],details=True,reference_date=date.fromisoformat(message['date'][:10]))
                result['client']=(d.get('client') or {}).get('BPCNUM_0','')
                result['missing']=' ; '.join(d.get('missing_fields',[]))
                result['zero_price_articles']=' ; '.join(l['article'] for l in d['lines'] if l['price']==0)
                (OUT/f'all-check-{mid}-details.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
                if d['intent']=='order' and not d['missing'] and d['client'] and d['lines']:
                    payload=build_payload(d,reference_date=date.fromisoformat(message['date'][:10]))
                    sql=await asyncio.to_thread(run_script,'sob-execute.ps1',payload)
                    (OUT/f'all-check-{mid}-preview.json').write_text(json.dumps(sql,ensure_ascii=False,indent=2),encoding='utf-8')
                    result['total_ttc']=payload['total']
                    result['status']=('sql_preview_passed_with_context' if mid in contexts else 'sql_preview_passed') if sql.get('ok') else 'sql_preview_refused'
                    if not sql.get('ok'):result['missing']='SQL '+str(sql.get('code'))
                else:
                    result['status']='needs_review'
            except Exception as exc:
                result.update(status='review_error',missing=type(exc).__name__+': '+str(exc)[:180])
            results.append(result)
            print(mid,result['status'],result['missing'],flush=True)
    await asyncio.gather(*(one(m) for m in messages if m['media'] and (not args.ids or m['id'] in args.ids)))
    results.sort(key=lambda r:r['message_id'])
    with (ROOT/'TEST/SOB-REJEU-TOUS-DOCUMENTS-RECENTS.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(results[0]),delimiter=';');writer.writeheader();writer.writerows(results)
    (OUT/'all-preparations-review.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DONE',len(results),'documents, no creation')


if __name__=='__main__':asyncio.run(main())
