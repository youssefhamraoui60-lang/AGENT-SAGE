"""SELECT-only verification and durable report for a completed dated SOB replay."""
import argparse,collections,csv,json,sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from psycopg.types.json import Jsonb
import creation
import learning_memory as memory

ROOT=Path(__file__).resolve().parents[1]


def verified(payload,rows,number):
    if len(rows)!=len(payload['lines']):return False
    expected={int(line['line']):line for line in payload['lines']}
    if len({int(r['SOPLIN_0']) for r in rows})!=len(rows):return False
    for row in rows:
        line=expected.get(int(row['SOPLIN_0']))
        if not line or str(row['SOHNUM_0']).strip()!=number or str(row['BPCORD_0']).strip()!=payload['client']:return False
        if str(row['ITMREF_0']).strip()!=line['article']:return False
        if Decimal(str(row['QTY_0']))!=Decimal(line['quantity']) or Decimal(str(row['NETPRIATI_0']))!=Decimal(line['price']):return False
        if line.get('supplier') and str(row.get('XBPS_0','')).strip()!=line['supplier']:return False
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);args=parser.parse_args()
    out=ROOT/'runtime'/('sob-day-'+args.date.replace('-',''))
    results=json.loads((out/'replay-results.json').read_text(encoding='utf-8'))
    summary=json.loads((out/'replay-summary.json').read_text(encoding='utf-8'))
    source=json.loads((out/'messages-reviewed.json').read_text(encoding='utf-8'));by_id={r['id']:r for r in source}
    def check(item):
        with creation.connection() as conn:
            receipt=conn.execute("SELECT payload FROM reviews WHERE owner=? AND status='created' AND number=? ORDER BY rowid DESC LIMIT 1",(item['owner'],item['number'])).fetchone()
        if not receipt:return {'number':item['number'],'verified':False,'reason':'Receipt missing'}
        payload=json.loads(receipt['payload'])
        try:
            readback=creation.run_script('sob-read.ps1',{'kind':'order_lines','code':item['number']})
            ok=readback.get('ok') is True and verified(payload,readback.get('rows',[]),item['number'])
            return {'number':item['number'],'verified':ok,'expected':payload,'actual':readback.get('rows',[])}
        except Exception as exc:return {'number':item['number'],'verified':False,'reason':type(exc).__name__}
    created=[r for r in results if r['status']=='created']
    with ThreadPoolExecutor(max_workers=3) as executor:checks=list(executor.map(check,created))
    (out/'replay-sql-verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    summary.update(sql_verified=sum(c['verified'] for c in checks),sql_unverified=[c['number'] for c in checks if not c['verified']],first_source_time=min(r['date'] for r in source),last_source_time=max(r['date'] for r in source))
    (out/'replay-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    good={c['number'] for c in checks if c['verified']}
    with memory.db.connection() as conn:
        for result in results:
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET input_data=EXCLUDED.input_data,observed=EXCLUDED.observed,status=EXCLUDED.status''',
                ('sob-replay-'+args.date+'-'+str(result['message_ids'][0]),Jsonb([by_id[mid] for mid in result['message_ids']]),None,Jsonb(result),
                 'created_test_sql_verified' if result.get('number') in good else 'already_created_no_replay' if result['status']=='already_created' else 'needs_review'))
    report=['# Reprise SOB du '+args.date,'',str(summary['messages'])+' messages source, '+str(summary['groups'])+' lots suivis individuellement.',
            str(len(created))+' nouvelles commandes TEST ; '+str(summary['sql_verified'])+' relues et conformes aux paramètres exécutés.',
            'Résultats publiés dans COMMANDES SOB : '+str(summary['published'])+'. Écritures OB : 0.',
            'Dernier message du snapshot : '+summary['last_source_time']+'. Les nouveaux messages sont traités par le service en direct.',
            '', 'Les vérifications SQL confirment les paramètres enregistrés ; les ambiguïtés d’identité, de produit, de quantité ou de regroupement restent signalées.',
            '', '| Messages source | Contact | Résultat | Commande(s) | Détail |','| --- | --- | --- | --- | --- |']
    def safe(value):
        text=str(value or '')
        return "'"+text if text.startswith(('=','+','-','@')) else text
    csv_rows=[]
    for r in sorted(results,key=lambda x:min(x['message_ids'])):
        numbers=r.get('number') or ', '.join(r.get('numbers',[]))
        report.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in [','.join(map(str,r['message_ids'])),r.get('contact',''),r['status'],numbers,r['reply']])+' |')
        csv_rows.append({'messages':','.join(map(str,r['message_ids'])),'contact':r.get('contact',''),'status':r['status'],'commandes':numbers,'reponse':r['reply'],'publie':r.get('published',False)})
    target=ROOT/'TEST'/('SOB-REPRISE-'+args.date+'.md');target.write_text('\n'.join(report)+'\n',encoding='utf-8')
    with target.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(csv_rows[0]),delimiter=';');writer.writeheader();writer.writerows({k:safe(v) for k,v in row.items()} for row in csv_rows)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
