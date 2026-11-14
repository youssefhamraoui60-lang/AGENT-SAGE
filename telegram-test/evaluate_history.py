"""Read-only evaluation of exported messages against OB references and orders.

No confirmation, review execution or Sage INSERT is called. OB order numbers are
scoring labels only and are never sent to the model or used for name resolution.
"""
import asyncio
import collections
import contextvars
import json
import hashlib
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import prepare as agent
import creation
from app.core.config import settings
from app.services import ai_provider

OUT = ROOT / 'runtime/sob-audit'
# Grouping reviewed from the chronological source, including explicit late PLUS.
# None means no sufficiently reliable OB counterpart established; not a failure.
GROUPS = [
    ([4796,4797], ['25214'], 'split_transport'),
    ([4798], ['25216'], 'cement_transport'),
    ([4799], ['25217'], 'pdf_text'),
    ([4800], ['25218'], 'perfecto_delivery_monday'),
    ([4801,4802,4803], ['25220'], 'tonnes_split_client'),
    ([4804], ['25221'], 'tonnes'),
    ([4805], ['25224'], 'voyage'),
    ([4806], None, 'voyage_customer_uncertain'),
    ([4807], ['25225'], 'voyage_cash_monday'),
    ([4808], ['25226'], 'cement_customer_reordered'),
    ([4809], ['25228'], 'collection_payment'),
    ([4810], ['25233'], 'steel_tonnes_cement'),
    ([4811], ['25229'], 'tradicem'),
    ([4812], ['25230'], 'explicit_customer_code'),
    ([4813,4814], ['25231'], 'tonnes_split_transport'),
    ([4815,4816], ['25240'], 'scanned_pdf_sand'),
    ([4817,4818,4821], ['25234'], 'palette_barres_late_plus'),
    ([4819,4820], ['25235'], 'tonnes_delivery_tuesday'),
    ([4822], ['25236'], 'explicit_code_multiline'),
    ([4823], [], 'activate_existing_not_create'),
    ([4824], ['25238'], 'cement_no_unit'),
    ([4825], ['25239'], 'embedded_transport'),
    ([4826], ['25241'], 'waterproofing_rolls'),
    ([4827], ['25242'], 'cement_35_45'),
    ([4828], ['25243'], 'cement_palettes'),
    ([4829], None, 'tonnes_customer_unmatched'),
    ([4830], ['25246'], 'phonetic_customer'),
    ([4831], ['25247'], 'fardeaux_steel_hundred_kg_prices'),
    ([4832], ['25248'], 'explicit_cement_price'),
    ([4833,4834], ['25249'], 'relative_date_continuation'),
    ([4835,4836], None, 'arabic_quintaux_missing_diameter'),
    ([4837,4838,4839,4840], ['25251'], 'four_messages_arabic_address'),
    ([4841], ['25252'], 'cement_55_special'),
    ([4842], ['25253'], 'abbreviated_customer'),
    ([4843,4844,4846], ['25254','25255','25256','25257'], 'duplicate_scanned_bc_multiple_ob_orders'),
    ([4845], ['25258'], 'photo_steel_table'),
    ([4847], ['25259'], 'fasm_pointes'),
    ([4848,4849], ['25260'], 'client_in_followup'),
    ([4850,4853], ['25262'], 'late_customer_addition'),
    ([4851,4852], None, 'pdf_ht_ttc_sand'),
    ([4854], ['25266'], 'phonetic_customer_transport'),
    ([4855], ['25268'], 'forwarded_customer_message'),
    ([4856], ['25269'], 'scanned_pdf_ht_price'),
    ([4857], None, 'tonnes_27_unmatched'),
    ([4858], ['25271'], 'fardeaux_two_steel_prices'),
    ([4859,4860], None, 'pdf_transport_late_plus'),
    ([4861], ['25274'], 'cement_perfecto'),
    ([4862,4863,4864], ['25275'], 'handwriting_duplicate_photo'),
    ([4865], ['25276'], 'tonnes_explicit_price'),
    ([4866], ['25277'], 'voyage_temara'),
    ([4867], [], 'reminder_not_create'),
    ([4868], None, 'sunday_order_unmatched'),
]


def totals(lines, code_key, quantity_key):
    result = collections.defaultdict(Decimal)
    for row in lines:
        if row.get(quantity_key) is not None:
            result[row[code_key].strip()] += Decimal(str(row[quantity_key]))
    return {k: str(v.normalize()) for k,v in sorted(result.items())}


async def main():
    def no_writes(*args, **kwargs):
        raise AssertionError('Historical evaluation must never create or confirm a Sage order')
    creation.review = no_writes
    creation.confirm = no_writes
    source = json.loads((OUT / 'messages-selected.json').read_text(encoding='utf-8'))
    messages = {r['id']: r for r in source}
    covered = [i for ids,_,_ in GROUPS for i in ids]
    assert sorted(covered) == sorted(messages), 'Every selected message must be accounted for once'
    ob = json.loads((OUT / 'ob-orders.json').read_text(encoding='utf-8'))['rows']
    expected_orders = collections.defaultdict(list)
    for row in ob:
        expected_orders[row['SOHNUM_0']].append(row)
    stage = sys.argv[1] if len(sys.argv)>1 else 'baseline'
    replay = {}
    if len(sys.argv)>2:
        replay = {r['message_ids'][0]:r.get('extracted') for r in json.loads((OUT / ('evaluation-'+sys.argv[2]+'.json')).read_text(encoding='utf-8'))}
    hashes = {name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
              for name in ('prepare.py','understanding.py','sob-read.ps1','creation.py','telegram_batch.py')}
    (OUT / ('source-'+stage+'.json')).write_text(json.dumps({'hashes':hashes,'cached_model_source':sys.argv[2] if len(sys.argv)>2 else None,'reference_folder':'OB','writes':0},indent=2),encoding='utf-8')
    checkpoint = OUT / f'evaluation-{stage}.json'
    results = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else []
    done = {tuple(r['message_ids']) for r in results}
    original = ai_provider.complete
    current = contextvars.ContextVar('audit_case')
    extracted = {}

    async def capture(*args, **kwargs):
        if replay:
            draft=replay.get(current.get())
            if not draft:
                raise ValueError('No cached extraction for this case')
            response={'message':{'content':json.dumps(draft,ensure_ascii=False)}}
        else:
            response = await original(*args, **kwargs)
        extracted[current.get()] = json.loads(response['message']['content'])
        return response

    ai_provider.complete = capture
    # The audit must never silently fall back to a CPU job or bypass cloud budget.
    settings.ai_fallback_provider = 'none'
    semaphore = asyncio.Semaphore(4 if replay else 2)

    async def evaluate(ids, labels, kind):
        if tuple(ids) in done:
            return
        async with semaphore:
            current.set(ids[0])
            rows = [messages[i] for i in ids]
            text = '\n\n'.join(r['text'] + ('\n\nDOCUMENT JOINT:\n' + r['attachment_text'] if r.get('attachment_text') else '') for r in rows)
            item = {'message_ids': ids, 'kind': kind, 'ob_orders': ['2026ARC'+x for x in labels] if labels is not None else None,
                    'attachment_uncertain': any(p.get('uncertain') for r in rows for p in r.get('attachment_decode',{}).get('pages',[])),
                    'source_date': rows[0]['date'], 'sage_writes': 0}
            try:
                details = await asyncio.wait_for(agent.prepare([{'role':'user','content':text}], details=True,
                    reference_folder='OB', reference_date=date.fromisoformat(rows[0]['date'][:10])), 180)
                item['details'] = details
                item['extracted'] = extracted.get(ids[0])
                try:
                    creation.build_payload(details,reference_date=date.fromisoformat(rows[0]['date'][:10]))
                    item['current_test_creation_scope'] = True
                except creation.CreationError as exc:
                    item['current_test_creation_scope'] = False
                    item['creation_blocker'] = str(exc)
                if labels:
                    truth = [r for x in labels for r in expected_orders['2026ARC'+x]]
                    assert truth, 'OB scoring label absent'
                    item['client_match'] = bool(details['client']) and details['client']['BPCNUM_0'].strip()==truth[0]['BPCORD_0'].strip()
                    item['rep_match'] = bool(details['representative']) and details['representative']['REPNUM_0'].strip()==truth[0]['REP_0'].strip()
                    item['expected_quantities'] = totals(truth,'ITMREF_0','QTY_0')
                    item['actual_quantities'] = totals(details['lines'],'article','quantity')
                    item['lines_match'] = item['expected_quantities']==item['actual_quantities']
                    item['complete_match'] = item['client_match'] and item['rep_match'] and item['lines_match']
                    expected_amounts=collections.defaultdict(Decimal)
                    actual_amounts=collections.defaultdict(Decimal)
                    for row in truth:
                        expected_amounts[row['ITMREF_0'].strip()]+=Decimal(str(row['QTY_0']))*Decimal(str(row['NETPRIATI_0']))
                    for row in details['lines']:
                        if row['quantity'] is not None and row['price'] is not None:
                            actual_amounts[row['article']]+=Decimal(str(row['quantity']))*Decimal(str(row['price']))
                    item['prices_totals_match']=set(expected_amounts)==set(actual_amounts) and all(abs(value-actual_amounts[key])<=Decimal('.05') for key,value in expected_amounts.items())
                    item['structural_and_price_match']=item['complete_match'] and item['prices_totals_match']
                elif labels == []:
                    item['not_create_correct'] = details['intent']=='other'
                item['ok'] = True
            except Exception as exc:
                item.update(ok=False,error=type(exc).__name__)
                item['extracted'] = extracted.get(ids[0])
                if hasattr(exc,'validator'):
                    item['validation'] = {'path': list(exc.absolute_path), 'rule': exc.validator,
                                          'message': exc.message[:500]}
            results.append(item)
            checkpoint.write_text(json.dumps(sorted(results,key=lambda r:r['message_ids'][0]),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'case':ids,'ok':item['ok'],'client':item.get('client_match'),'lines':item.get('lines_match'),'complete':item.get('complete_match')},ensure_ascii=False),flush=True)
    await asyncio.gather(*(evaluate(*group) for group in GROUPS))
    print(json.dumps({'cases':len(results),'scored':sum(bool(r['ob_orders']) for r in results),
                      'complete_match':sum(bool(r.get('complete_match')) for r in results),
                      'sage_writes':0}),flush=True)


if __name__ == '__main__':
    asyncio.run(main())
