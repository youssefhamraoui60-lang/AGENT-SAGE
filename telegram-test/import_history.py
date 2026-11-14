"""Reconcile historical Telegram demands with SELECT-only OB, create via SOB TEST.

Every source message receives a durable outcome. No arbitrary OB order is copied:
automatic linkage requires unique matching day, commercial, customer and quantities,
or unambiguous name evidence plus complete article quantities. Partial continuations
are attached to an already established order, never imported as another order.
"""
import argparse
import asyncio
import collections
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re
import hashlib
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from evaluate_week import quantities,sql_day
from reference_snapshot import ReferenceSnapshot
from understanding import name_score,normalized
import creation
import learning_memory as memory

OUT=ROOT/'runtime/sob-week-20261102'

def dump(path,value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    temp.replace(path)

def reconcile():
    snapshot=ReferenceSnapshot(OUT)
    customers={r['BPCNUM_0']:r for r in snapshot.customers}
    orders=collections.defaultdict(list)
    for row in snapshot.orders:orders[row['SOHNUM_0']].append(row)
    source={r['id']:r for r in json.loads((OUT/'messages-decoded.json').read_text(encoding='utf-8'))}
    cases=json.loads((OUT/'evaluation-final.json').read_text(encoding='utf-8'))
    valid_parts={};segmented_keys=set()
    if (OUT/'repair-parts.json').exists():
        from repair_history import validate,normalize_proof
        visual_parts={r['id']:r for r in json.loads((OUT/'messages-visual.json').read_text(encoding='utf-8'))}
        parts=json.loads((OUT/'repair-parts.json').read_text(encoding='utf-8'))
        if (OUT/'repair-text-parts.json').exists():parts+=json.loads((OUT/'repair-text-parts.json').read_text(encoding='utf-8'))
        for part in parts:
            answer=part.get('answer',{});number=part.get('ob_number') or answer.get('ob_number')
            if number not in orders:continue
            mid=part['message_id'];row=visual_parts[mid]
            if sql_day(orders[number][0]['ORDDAT_0'])!=row['date'][:10]:continue
            text=row['text']+'\n'+row.get('layout_text','');identity=customers[orders[number][0]['BPCORD_0']]
            answer=normalize_proof({**answer,'_client_name':identity['BPCNAM_0'],'_identity':str(identity.get('XICE_0','')).strip()},orders[number],text)
            candidates={n:rs for n,rs in orders.items() if sql_day(rs[0]['ORDDAT_0'])==row['date'][:10]}
            valid,_=validate(answer,candidates,text,customers)
            if valid:
                valid_parts[mid]={**part,'ob_number':number,'answer':answer}
                if len(part['parent_message_ids'])>1:segmented_keys.add(tuple(part['parent_message_ids']))
    links={}
    outcomes=[]
    for case in cases:
        d=case.get('details',{})
        draft=case.get('extracted') or {}
        day=case['source_date'][:10]
        rep=(d.get('representative') or {}).get('REPNUM_0','').strip()
        text='\n\n'.join(source[i]['text'] for i in case['message_ids'])
        contact=re.search(r'(?im)^\s*Contact\s*:\s*([^\n]+)',text)
        if not rep and contact:
            rows=snapshot('representative',contact[1])
            if len(rows)==1:rep=rows[0]['REPNUM_0']
        client=(d.get('client') or {}).get('BPCNUM_0','').strip()
        actual=quantities(d.get('lines',[]),'article','quantity')
        nonservice={k:v for k,v in actual.items() if k!='MANTD'}
        candidates=[]
        for number,rows in orders.items():
            head=rows[0]
            if sql_day(head['ORDDAT_0'])!=day:continue
            expected=quantities(rows,'ITMREF_0','QTY_0')
            expected_goods={k:v for k,v in expected.items() if k!='MANTD'}
            if not nonservice or nonservice!=expected_goods:continue
            # All demanded goods must have resolved; a missing article cannot be
            # silently replaced by an OB line based on a shared transport price.
            if any(m.startswith('article ') for m in d.get('missing_fields',[])):continue
            same_client=client==head['BPCORD_0'].strip()
            if not rep and not same_client:continue
            if rep and head['REP_0'].strip()!=rep and not same_client:continue
            query=draft.get('client') or ''
            name=customers.get(head['BPCORD_0'],{}).get('BPCNAM_0','')
            evidence=name_score(query,name) if query else 0
            if not same_client and evidence<.72:continue
            candidates.append({'number':number,'method':('exact_client_rep_goods' if head['REP_0'].strip()==rep else 'exact_client_goods_rep_from_ob') if same_client else 'unique_name_rep_goods','name_score':evidence,'full_quantities':actual==expected,'rep_matches':head['REP_0'].strip()==rep})
        preferred=[c for c in candidates if c['rep_matches']]
        if len(preferred)==1:candidates=preferred
        if tuple(case['message_ids']) in segmented_keys:candidates=[]
        item={'message_ids':case['message_ids'],'source_date':case['source_date'],'contact':contact[1] if contact else '',
              'client_hint':draft.get('client'),'missing':d.get('missing_fields',[]),'candidates':candidates}
        if len(candidates)==1:
            candidate=candidates[0]
            number=candidate['number']
            item.update(status='linked',ob_number=number,method=candidate['method'])
            links.setdefault(number,{'ob_number':number,'message_ids':[],'cases':[]})
            links[number]['message_ids'].extend(case['message_ids'])
            links[number]['cases'].append(item)
        else:
            item.update(status='unresolved',reason='Plusieurs commandes OB compatibles' if candidates else 'Rapprochement OB non établi : client/commercial/articles/quantités à vérifier')
        outcomes.append(item)
    repair_paths=[p for p in (OUT/'repair-proposals.json',OUT/'repair-context.json',OUT/'repair-contacts.json',OUT/'repair-visual.json',OUT/'repair-broad.json',OUT/'repair-identity.json') if p.exists()]
    if repair_paths:
        from repair_history import validate,normalize_proof
        source_file=OUT/('messages-visual.json' if (OUT/'messages-visual.json').exists() else 'messages-layout.json')
        layout_source={r['id']:r for r in json.loads(source_file.read_text(encoding='utf-8'))}
        proposals={}
        for repair_path in repair_paths:
            for proposal in json.loads(repair_path.read_text(encoding='utf-8')):
                key=tuple(proposal['message_ids'])
                if key not in proposals or proposal.get('validated') or not proposals[key].get('validated'):proposals[key]=proposal
        for item in outcomes:
            if item['status']=='linked':continue
            if tuple(item['message_ids']) in segmented_keys:continue
            proposal=proposals.get(tuple(item['message_ids']))
            if not proposal or not proposal.get('answer'):continue
            rep=proposal.get('representative','')
            candidates={n:rows for n,rows in orders.items() if sql_day(rows[0]['ORDDAT_0'])==item['source_date'][:10]}
            source_case=next(c for c in cases if c['message_ids']==item['message_ids'])
            known=(source_case.get('details',{}).get('client') or {}).get('BPCNUM_0')
            selected_number=proposal['answer'].get('ob_number')
            if selected_number in orders:
                selected_customer=customers[orders[selected_number][0]['BPCORD_0']]
                ice=str(selected_customer.get('XICE_0','')).strip()
                source_text='\n'.join(layout_source[i]['text']+'\n'+layout_source[i].get('layout_text','') for i in item['message_ids'])
                explicit_codes=set(c.upper() for c in re.findall(r'\bC\d{4,8}\b','\n'.join(layout_source[i]['text'] for i in item['message_ids']),re.I))
                if len(ice)==15 and ice in normalized(source_text) and sum(str(c.get('XICE_0','')).strip()==ice for c in customers.values())==1 and (not explicit_codes or selected_customer['BPCNUM_0'] in explicit_codes):known=None
            if known:candidates={n:rows for n,rows in candidates.items() if rows[0]['BPCORD_0']==known}
            evidence_ids=proposal.get('evidence_message_ids',item['message_ids'])
            if not set(item['message_ids'])<=set(evidence_ids):continue
            if any(i not in layout_source or abs((datetime.fromisoformat(layout_source[i]['date'])-datetime.fromisoformat(item['source_date'])).total_seconds())>180 for i in evidence_ids):continue
            text='\n\n'.join('MESSAGE #'+str(i)+'\n'+layout_source[i]['text']+('\nDOCUMENT (colonnes séparées par |):\n'+layout_source[i]['layout_text'] if layout_source[i].get('layout_text') else '\n'+layout_source[i].get('attachment_text','')) for i in evidence_ids)
            answer=dict(proposal['answer'])
            selected=answer.get('ob_number')
            if selected in candidates:
                identity=customers[candidates[selected][0]['BPCORD_0']]
                answer=normalize_proof({**answer,'_client_name':identity['BPCNAM_0'],'_identity':str(identity.get('XICE_0','')).strip()},candidates[selected],text)
            valid,reason=validate(answer,candidates,text,customers)
            if not valid and answer.get('goods'):
                # Some forwarded messages carry a contact different from OB's
                # assigned salesman. A complete, unique source-backed goods
                # pattern can identify the historical order across salesmen.
                day_orders={n:rows for n,rows in orders.items() if sql_day(rows[0]['ORDDAT_0'])==item['source_date'][:10] and (not known or rows[0]['BPCORD_0']==known)}
                witnessed=collections.defaultdict(Decimal)
                try:
                    for g in answer['goods']:witnessed[g['code']]+=Decimal(str(g['source_quantity']))*Decimal(str(g.get('factor',1)))
                    matching=[n for n,rows in day_orders.items() if {k:v for k,v in quantities(rows,'ITMREF_0','QTY_0').items() if k not in ('MANTD','TRS','TRC')}==dict(witnessed)]
                except Exception:matching=[]
                if len(matching)==1:
                    answer['ob_number']=matching[0]
                    identity=customers[day_orders[matching[0]][0]['BPCORD_0']]
                    answer=normalize_proof({**answer,'_client_name':identity['BPCNAM_0'],'_identity':str(identity.get('XICE_0','')).strip()},day_orders[matching[0]],text)
                    valid,reason=validate(answer,day_orders,text,customers)
            primary='\n\n'.join(layout_source[i]['text']+'\n'+layout_source[i].get('layout_text',layout_source[i].get('attachment_text','')) for i in item['message_ids'])
            from repair_history import quote_in
            witnesses=[answer.get('client_evidence','')]+[g.get('quote','') for g in answer.get('goods',[])]
            if not any(quote_in(q,primary) for q in witnesses):valid=False;reason='Citation sans preuve dans les messages ciblés'
            if not valid:
                item['repair_blocker']=reason
                continue
            number=answer['ob_number']
            item.update(status='linked',ob_number=number,method='agent_source_quoted_reconciliation',proof=answer,source_representative=rep,ob_representative=orders[number][0]['REP_0'])
            links.setdefault(number,{'ob_number':number,'message_ids':[],'cases':[]})
            links[number]['message_ids'].extend(item['message_ids']);links[number]['cases'].append(item)
    multi_path=OUT/'repair-multi.json'
    if multi_path.exists():
        from repair_history import validate,normalize_proof
        visual={r['id']:r for r in json.loads((OUT/'messages-visual.json').read_text(encoding='utf-8'))}
        multi={tuple(r['message_ids']):r for r in json.loads(multi_path.read_text(encoding='utf-8'))}
        for item in outcomes:
            if item['status']=='linked':continue
            if tuple(item['message_ids']) in segmented_keys:continue
            proposal=multi.get(tuple(item['message_ids']),{});numbers=proposal.get('ob_numbers',[])
            numbers=numbers or proposal.get('answer',{}).get('ob_numbers',[])
            if not numbers or any(n not in orders for n in numbers):continue
            combined=[r for n in numbers for r in orders[n]]
            if len({r['BPCORD_0'] for r in combined})!=1 or any(sql_day(r['ORDDAT_0'])!=item['source_date'][:10] for r in combined):continue
            text='\n\n'.join(visual[i]['text']+'\n'+visual[i].get('layout_text','') for i in item['message_ids'])
            identity=customers[combined[0]['BPCORD_0']]
            answer=normalize_proof({**proposal['answer'],'ob_number':'COMBINED','_client_name':identity['BPCNAM_0'],'_identity':str(identity.get('XICE_0','')).strip()},combined,text)
            valid,reason=validate(answer,{'COMBINED':combined},text,customers)
            if not valid:continue
            item.update(status='linked',ob_number=numbers[0],ob_numbers=numbers,method='source_document_multiple_ob_orders',proof=answer)
            for number in numbers:
                links.setdefault(number,{'ob_number':number,'message_ids':[],'cases':[]})
                links[number]['message_ids'].extend(item['message_ids']);links[number]['cases'].append(item)
    segmented_outcomes=[]
    for item in outcomes:
        ids=item['message_ids']
        if item['status']=='linked' or not (tuple(ids) in segmented_keys or any(i in valid_parts for i in ids)):
            segmented_outcomes.append(item);continue
        for mid in ids:
            child={**item,'message_ids':[mid],'parent_message_ids':ids,'source_date':source[mid]['date']}
            part=valid_parts.get(mid)
            if part:
                number=part['ob_number'];child.update(status='linked',ob_number=number,method='independent_document_source_proof',proof=part['answer'])
                child.pop('repair_blocker',None)
                links.setdefault(number,{'ob_number':number,'message_ids':[],'cases':[]})
                links[number]['message_ids'].append(mid);links[number]['cases'].append(child)
            else:
                child.update(status='unresolved',reason='Complément à rattacher après séparation des documents');child.pop('repair_blocker',None)
            segmented_outcomes.append(child)
    outcomes=segmented_outcomes
    # Attach transport-only/notes to an established order only with one nearby
    # contact on the same day. Never turns a failed new goods order into a note.
    cases_by_ids={tuple(case['message_ids']):case for case in cases}
    for item in outcomes:
        case=cases_by_ids[tuple(item.get('parent_message_ids',item['message_ids']))]
        if item['status']=='linked':continue
        d=case.get('details',{})
        draft=case.get('extracted') or {}
        rawlines=draft.get('lines',[])
        if any(source[i].get('file') for i in item['message_ids']):continue
        def note_line(line):
            name=normalized(line.get('article') or '')
            if name in ('trs','trc','mantd','transport','manutention'):return True
            return line.get('quantity') is None and (name in ('sonasid','sounacid','sounassid','novacim','lafarge','cimat','balance','barredroite','barrespliees') or bool(re.fullmatch(r'\d+',name)))
        if not all(note_line(line) for line in rawlines):continue
        if not item['contact']:continue
        primary_text='\n'.join(source[i]['text'] for i in item['message_ids'])
        explicit_continuation=bool(re.search(r'(?im)^\s*(?:plus|trs|trc|transport|livraison|compl[eé]ment)\b',re.sub(r'(?im)^\s*(?:Contact|Numero)\s*:[^\n]*','',primary_text)))
        nearby=set()
        for other in outcomes:
            if other['status']!='linked' or normalized(other['contact'])!=normalized(item['contact']):continue
            delta=(datetime.fromisoformat(item['source_date'])-datetime.fromisoformat(other['source_date'])).total_seconds()
            if 0<=delta<=(1800 if explicit_continuation else 180) and item['source_date'][:10]==other['source_date'][:10]:
                hint=draft.get('client')
                head=orders[other['ob_number']][0]
                if hint and normalized(head['BPCORD_0']) not in normalized(primary_text) and max(name_score(hint,customers[head['BPCORD_0']]['BPCNAM_0']),name_score(customers[head['BPCORD_0']]['BPCNAM_0'],hint))<.72:continue
                nearby.add(other['ob_number'])
        if len(nearby)==1:
            number=next(iter(nearby))
            item.update(status='linked',ob_number=number,method='nearby_continuation_review_candidate')
            links[number]['message_ids'].extend(item['message_ids'])
            links[number]['cases'].append(item)
    # Exact duplicate files refer to the same historical document when a single
    # OB order has been established for that byte-identical document.
    file_targets=collections.defaultdict(set)
    hashes={}
    for message in source.values():
        if message.get('file'):hashes[message['id']]=hashlib.sha256((OUT/message['file']).read_bytes()).hexdigest()
    for item in outcomes:
        if item['status']=='linked':
            for i in item['message_ids']:
                if i in hashes:file_targets[hashes[i]].add(item['ob_number'])
    for item in outcomes:
        if item['status']=='linked':continue
        if not all(i in hashes and len(file_targets[hashes[i]])==1 for i in item['message_ids']):continue
        targets=set().union(*(file_targets[hashes[i]] for i in item['message_ids'] if i in hashes))
        if len(targets)==1 and any(i in hashes for i in item['message_ids']):
            number=next(iter(targets))
            item.update(status='linked',ob_number=number,method='byte_identical_document')
            links[number]['message_ids'].extend(item['message_ids']);links[number]['cases'].append(item)
    from confirmed_groups import apply as apply_confirmed_groups
    apply_confirmed_groups(memory.ACTIVE.get(),orders,source,links,outcomes)
    for link in links.values():link['message_ids']=sorted(set(link['message_ids']))
    assert sorted(i for item in outcomes for i in item['message_ids'])==sorted(source)
    dump(OUT/'import-linkage.json',{'orders':list(links.values()),'outcomes':outcomes,'coverage_messages':len(source),'production_writes':0})
    return snapshot,orders,links,outcomes

@lru_cache(maxsize=1024)
def live(kind,code):
    result=creation.run_script('sob-read.ps1',{'kind':kind,'code':code})
    if not result.get('ok'):raise creation.CreationError('Lecture TEST indisponible : '+kind)
    return result['rows']

def details_from_verified_order(number,rows):
    head=rows[0]
    customers=live('client_profile',head['BPCORD_0'])
    if len(customers)!=1:raise creation.CreationError('Client absent de TEST : '+head['BPCORD_0'])
    client=customers[0]
    if client['CUR_0'].strip()!=head['CUR_0'].strip():raise creation.CreationError('Devise TEST/OB différente')
    lines=[]
    for row in rows:
        code='MANTD' if row['ITMREF_0'].strip() in ('TRS','TRC') else row['ITMREF_0'].strip()
        articles=[a for a in live('article',code) if a['ITMREF_0'].strip()==code]
        if len(articles)!=1:raise creation.CreationError('Article absent TEST : '+code)
        a=articles[0]
        if not a['SITE_OK']:raise creation.CreationError('Article sans site 201 TEST : '+code)
        if a['SAU_0'].strip()!=row['SAU_0'].strip():raise creation.CreationError('Unité différente TEST/OB : '+code)
        if a['VACITM_0'].strip()!='T20':raise creation.CreationError('TVA hors moteur validé T20 : '+code)
        lines.append({'article':code,'quantity':row['QTY_0'],'price':row['NETPRIATI_0'],'unit':a['SAU_0']})
    total=sum((Decimal(str(r['quantity']))*Decimal(str(r['price']))).quantize(Decimal('.01')) for r in lines)
    if abs(total-Decimal(str(head['ORDATI_0'])))>Decimal('.10'):
        raise creation.CreationError('Total lignes différent du total OB : remise/frais à vérifier')
    today=datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()
    return {'client':client,'representative':{'REPNUM_0':head['REP_0'].strip()},'missing':[],
            'lines':lines,'delivery':today,'intent':'order','missing_fields':[],
            'delivery_note':f'REPRISE TELEGRAM 02-07/11 OB {number} - TEST'}

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--create',action='store_true');parser.add_argument('--serial',action='store_true');parser.add_argument('--approved-batch');parser.add_argument('--only-ob',nargs='+');args=parser.parse_args()
    approved_ids=set()
    if args.approved_batch:
        approval=json.loads(Path(args.approved_batch).read_text(encoding='utf-8'))
        if approval.get('scope')!='historical_remainder_477' or approval.get('human_validated') is not True:raise ValueError('Validation de lot invalide')
        approved_ids=set(approval['source_message_ids'])
    memory.ACTIVE.set(tuple(memory.approved_rules()))
    snapshot,orders,links,outcomes=reconcile()
    print(json.dumps({'linked_orders':len(links),'linked_messages':len({i for x in links.values() for i in x['message_ids']}),'unresolved_messages':sum(len(x['message_ids']) for x in outcomes if x['status']=='unresolved')}),flush=True)
    if not args.create:return
    path=OUT/'historical-creation-results.json'
    results=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    for result in results:
        if result['ob_number'] in links:result['message_ids']=links[result['ob_number']]['message_ids']
    # Previously verified cases created through exactly the same agent workflow.
    previous={'2026ARC24559':'2026ARC14614','2026ARC25216':'2026ARC14613'}
    # The earlier live-agent tests 14615/14617 used TEST/default/requested prices.
    # Their historical copies must instead reproduce the verified OB prices.
    done={r['ob_number'] for r in results if r.get('status')=='created' and not (
        r.get('previous_test') and r['ob_number'] in ('2026ARC24592','2026ARC24652'))}
    semaphore=asyncio.Semaphore(1 if args.serial else 3)
    async def create(number,link):
        if number in done:return
        if args.only_ob and number not in args.only_ob:return
        excluded=set(memory.policy('telegram_creation_excluded_contacts',[]))
        if any(__import__('telegram_batch').contact_name(next(r['text'] for r in json.loads((OUT/'messages-week.json').read_text(encoding='utf-8')) if r['id']==mid)) in excluded for mid in link['message_ids']):return
        async with semaphore:
            result={'ob_number':number,'message_ids':link['message_ids'],'production_writes':0}
            owner='authorized-week-import-'+number
            try:
                validated=bool(approved_ids) and set(link['message_ids'])<=approved_ids
                if number in previous:
                    result.update(status='created',number=previous[number],previous_test=True)
                else:
                    with creation.connection() as conn:
                        existing=conn.execute('SELECT id,status FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 1',(owner,)).fetchone()
                    if existing and existing['status'] in ('created','pending','uncertain','ready'):
                        try:
                            receipt=await asyncio.to_thread(creation.confirm,owner,existing['id'],human_validated=validated)
                        except creation.CreationError as exc:
                            if existing['status']!='ready' or not any(message in str(exc) for message in ('Le jour de commande a changé','Récapitulatif expiré')):raise
                            # Pre-SQL rejection: midnight/expiry requires a new
                            # preview, never reuse yesterday's dates or plan.
                            await asyncio.to_thread(creation.invalidate,owner)
                            details=await asyncio.to_thread(details_from_verified_order,number,orders[number])
                            review=await asyncio.to_thread(creation.review,owner,details)
                            receipt=await asyncio.to_thread(creation.confirm,owner,review['id'],human_validated=validated)
                    else:
                        details=await asyncio.to_thread(details_from_verified_order,number,orders[number])
                        review=await asyncio.to_thread(creation.review,owner,details)
                        receipt=await asyncio.to_thread(creation.confirm,owner,review['id'],human_validated=validated)
                    result.update(receipt)
                with memory.db.connection() as conn:
                    from psycopg.types.json import Jsonb
                    conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                        ('sob-created-'+number,Jsonb(link),Jsonb({'OB':number,'client':orders[number][0]['BPCORD_0'],'lines':orders[number]}),Jsonb(result),'created_test_verified_reference'))
            except Exception as exc:
                result.update(status='blocked',reason=str(exc) if isinstance(exc,creation.CreationError) else type(exc).__name__)
            results[:]=[r for r in results if r['ob_number']!=number]+[result]
            dump(path,results)
            print(json.dumps({'done':len(results),'total':len(links),**result},ensure_ascii=False),flush=True)
    await asyncio.gather(*(create(number,link) for number,link in links.items()))
    dump(path,results)

if __name__=='__main__':asyncio.run(main())
