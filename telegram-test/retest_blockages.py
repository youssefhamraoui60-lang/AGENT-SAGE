"""Recheck 34 blocked historical orders; prepare all, never create in Sage."""
import asyncio
import collections
import csv
from datetime import datetime
import json
from zoneinfo import ZoneInfo
from import_history import OUT,ROOT,live,details_from_verified_order,dump
import creation
import learning_memory
from psycopg.types.json import Jsonb

async def main():
    original=json.loads((OUT/'historical-creation-results.json').read_text(encoding='utf-8'))
    blocked=[r for r in original if r['status']!='created']
    orders=collections.defaultdict(list)
    names={r['BPCNUM_0']:r['BPCNAM_0'] for r in json.loads((OUT/'ob-customers.json').read_text(encoding='utf-8'))['rows']}
    for row in json.loads((OUT/'ob-orders.json').read_text(encoding='utf-8'))['rows']:orders[row['SOHNUM_0']].append(row)
    results=[]
    semaphore=asyncio.Semaphore(2)
    async def check(item):
        async with semaphore:
            number=item['ob_number'];rows=orders[number];head=rows[0]
            result={'ob_number':number,'message_ids':item['message_ids'],'client':head['BPCORD_0'],
                    'draft':{'client':head['BPCORD_0'],'representative':head['REP_0'],'lines':[
                        {'article':r['ITMREF_0'],'description_ob':r['ITMDES1_0'],'quantity':r['QTY_0'],'unit_ob':r['SAU_0'],'price_ttc':r['NETPRIATI_0']} for r in rows]},
                    'issues':[],'proposals':[],'human_validation_required':True,'sage_writes':0}
            try:
                customers=await asyncio.to_thread(live,'client_profile',head['BPCORD_0'])
                result['client_in_test']=len(customers)==1
                if not customers:
                    result['issues'].append('Client absent de TEST : '+head['BPCORD_0'])
                    alternatives=await asyncio.to_thread(live,'client',names[head['BPCORD_0']])
                    from understanding import normalized
                    alternatives=[r for r in alternatives if normalized(r['BPCNAM_0'])==normalized(names[head['BPCORD_0']]) and r['CUR_0'].strip()==head['CUR_0'].strip()]
                    result['alternative_clients_test']=alternatives
                    if alternatives:result['proposals'].append('Même nom/devise trouvé sous un autre code TEST : '+', '.join(r['BPCNUM_0']+' — '+r['BPCNAM_0'] for r in alternatives)+'. Confirmer explicitement le rattachement ; aucun code remplacé automatiquement.')
                    result['proposals'].append('Faire valider la création ou la synchronisation de cette fiche client dans TEST ; conserver le brouillon.')
                for code in dict.fromkeys(r['ITMREF_0'] for r in rows):
                    articles=await asyncio.to_thread(live,'article',code)
                    articles=[a for a in articles if a['ITMREF_0'].strip()==code]
                    source=next(r for r in rows if r['ITMREF_0']==code)
                    if not articles:
                        result['issues'].append('Article absent TEST : '+code);continue
                    a=articles[0]
                    if code=='COL':result['COL_test']=a;result['COL_ob']=source
                    if not a['SITE_OK']:result['issues'].append('Article sans site 201 TEST : '+code)
                    if a['SAU_0'].strip()!=source['SAU_0'].strip():result['issues'].append('Unité différente '+code+' : TEST '+a['SAU_0']+' / OB '+source['SAU_0'])
                    if code=='COL' and 'TRADICEM' in source['ITMDES1_0'].upper() and 'TRADICEM' not in a['ITMDES1_0'].upper():
                        result['issues'].append('Produits différents sous le code COL : TEST « '+a['ITMDES1_0']+' » / OB « '+source['ITMDES1_0']+' »')
                        candidates=await asyncio.to_thread(live,'article','TRADICEM')
                        result['alternatives_test']=[a for a in candidates if a['SITE_OK'] and a['SAU_0'].strip()==source['SAU_0'].strip() and a['ITMREF_0'].strip()!='COL']
                        result['proposals'].append('Valider un autre code TEST correspondant réellement au TRADICEM, ou faire créer sa fiche article-site 201 sous un code distinct. Ne pas remplacer COL 250 ML ST silencieusement.')
                if not result['issues']:
                    details=await asyncio.to_thread(details_from_verified_order,number,rows)
                    review=await asyncio.to_thread(creation.review,'retest-human-validation-'+number,details)
                    result.update(status='ready_for_human_validation',review=review)
                else:result['status']='draft_prepared_missing_data'
            except Exception as exc:
                result['status']='draft_prepared_service_issue';result['issues'].append(str(exc) if isinstance(exc,creation.CreationError) else type(exc).__name__)
                result['proposals'].append('Réessayer le contrôle ; brouillon intégral conservé, aucune substitution.')
            results.append(result);dump(OUT/'retest-34-drafts.json',results)
            with learning_memory.db.connection() as conn:
                conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status) VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                    ('sob-retest-validation-'+number,Jsonb(result['draft']),Jsonb({'OB':number}),Jsonb(result),result['status']))
            print(json.dumps({'done':len(results),'order':number,'status':result['status'],'issues':result['issues']},ensure_ascii=False),flush=True)
    await asyncio.gather(*(check(item) for item in blocked))
    target=ROOT/'TEST/SOB-RETEST-34-VALIDATION.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['commande_OB','client','statut','problèmes','solutions','validation_humaine'],delimiter=';');writer.writeheader()
        for r in sorted(results,key=lambda r:r['ob_number']):writer.writerow({'commande_OB':r['ob_number'],'client':r['client'],'statut':r['status'],'problèmes':' ; '.join(r['issues']),'solutions':' ; '.join(r['proposals']),'validation_humaine':'OBLIGATOIRE'})
    summary={'tested':len(results),'statuses':dict(collections.Counter(r['status'] for r in results)),'clients_present_test':sum(r.get('client_in_test',False) for r in results),'sage_orders_created':0}
    dump(OUT/'retest-34-summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':asyncio.run(main())
