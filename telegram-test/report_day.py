"""Independent TEST readback and timestamped per-message daily report."""
import argparse
import collections
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import creation
import learning_memory as memory
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[1]

def safe(value):
    value=str(value or '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);args=parser.parse_args()
    date=datetime.strptime(args.date,'%Y-%m-%d').date()
    out=ROOT/'runtime'/('sob-day-'+date.strftime('%Y%m%d'))
    source=json.loads((out/'messages-layout.json').read_text(encoding='utf-8'))
    results=json.loads((out/'day-results.json').read_text(encoding='utf-8'))
    rules=memory.approved_rules()
    excluded_owners=set(next((r['payload'].get('value',[]) for r in rules if r['kind']=='policy' and r['rule_key']=='creation_excluded_owners'),[]))
    withdrawn={r['number'] for r in results if r.get('number') and r['owner'] in excluded_owners}
    by_id={i:r for r in results for i in r['message_ids']}
    assert len(by_id)==sum(len(r['message_ids']) for r in results)==len(source)
    expected={}
    with creation.connection() as conn:
        for item in results:
            if item['status']=='created':
                row=conn.execute("SELECT payload FROM reviews WHERE number=? AND status='created' ORDER BY rowid DESC LIMIT 1",(item['number'],)).fetchone()
                if not row:raise ValueError('Reçu local absent')
                expected[item['number']]=json.loads(row['payload'])
    read=creation.run_script('audit-read.ps1',{'kind':'created_test_orders','references':[r['reference'] for r in expected.values()]})
    if not read.get('ok'):raise ValueError('Contrôle SQL indisponible')
    actual=collections.defaultdict(list)
    for row in read['rows']:actual[row['SOHNUM_0']].append(row)
    checks=[]
    for number,payload in expected.items():
        rows=actual.get(number,[])
        want=sorted((l['article'],Decimal(str(l['quantity'])),Decimal(str(l['price']))) for l in payload['lines'])
        got=sorted((r['ITMREF_0'].strip(),Decimal(str(r['QTY_0'])),Decimal(str(r['NETPRIATI_0']))) for r in rows)
        ok=bool(rows) and want==got and rows[0]['BPCORD_0'].strip()==payload['client'] and rows[0]['REP_0'].strip()==payload['representative'] and abs(Decimal(str(rows[0]['ORDATI_0']))-Decimal(payload['total']))<=Decimal('.05')
        checks.append({'number':number,'verified':ok})
    (out/'day-readback.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    if not all(r['verified'] for r in checks):raise ValueError('Écart SQL : consulter day-readback.json')
    # Confirmed addition cannot yet be executed with the SQL agent's rights.
    corrections={'2026ARC14971':'Transport MANTD 1 × 300 TTC confirmé ; correction SQL en attente de droits UPDATE. Script TEST/SOB-CORRECTIONS-TRANSPORT-20261109.sql.',
                 '2026ARC15008':'Transport de 50 TTC compté deux fois dans un récapitulatif cité ; conserver une seule ligne MANTD 50. Correction SQL en attente de droits UPDATE/DELETE. Script TEST/SOB-CORRECTIONS-TRANSPORT-20261109.sql.'}
    rows=[]
    for message in source:
        result=by_id[message['id']]
        stamp=datetime.fromisoformat(message['date'])
        correction=corrections.get(result.get('number'),'')
        label={'created':'CRÉÉE','excluded':'EXCLUE','not_order':'HORS COMMANDE','needs_data':'DONNÉES À PRÉCISER','needs_group_review':'REGROUPEMENT À VÉRIFIER','blocked':'BLOCAGE'}.get(result['status'],result['status'])
        if correction:label='CRÉÉE À COMPLÉTER'
        if result.get('number') in withdrawn:
            label='CRÉÉE AVANT RETRAIT UTILISATEUR'
            correction='Commande déjà créée avant instruction de ne pas créer. Toute relance est bloquée. Aucune annulation Sage effectuée ; décision sur le test existant à confirmer.'
        rows.append({'message_id':message['id'],'jour':stamp.strftime('%d/%m/%Y'),'heure_UTC_plus_1':stamp.strftime('%H:%M:%S'),
                     'contact':result['contact'],'lot_messages':','.join(map(str,result['message_ids'])),'statut':label,
                     'commande_TEST':result.get('number',''),'motif':correction or ('' if result['status']=='created' else result.get('reply','')),
                     'fichier':str((out/message['file']).resolve()) if message.get('file') else '',
                     'texte':message['text'],'lecture_document':message.get('layout_text',''),'correction_utilisateur':''})
    remaining=[r for r in rows if r['statut'] not in ('CRÉÉE','HORS COMMANDE','EXCLUE')]
    prefix='SOB-JOUR-'+date.strftime('%Y%m%d')
    for suffix,data in [('RESULTATS',rows),('A-VERIFIER',remaining)]:
        with (ROOT/'TEST'/(prefix+'-'+suffix+'.csv')).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=rows[0],delimiter=';');writer.writeheader();writer.writerows({k:safe(v) for k,v in r.items()} for r in data)
    summary={'date':args.date,'messages':len(source),'groups':len(results),'statuses':dict(collections.Counter(r['status'] for r in results)),
             'created_orders':len(expected),'sql_verified':sum(c['verified'] for c in checks),
             'orders_requiring_correction':list(corrections.keys() & expected.keys()),'last_source_time':max(r['date'] for r in source),'production_writes':0}
    summary['orders_withdrawn_after_creation']=sorted(withdrawn)
    (out/'day-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    source_by_id={r['id']:r for r in source}
    with memory.db.connection() as conn:
        for item in results:
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                ('sob-day-'+args.date+'-'+str(item['message_ids'][0]),Jsonb([source_by_id[i] for i in item['message_ids']]),
                 Jsonb(expected.get(item.get('number'))) if item.get('number') else None,Jsonb(item),
                 'user_withdrawn_after_creation' if item.get('number') in withdrawn else 'created_test_sql_verified_correction_pending' if item.get('number') in corrections else 'created_test_sql_verified' if item['status']=='created' else 'excluded_by_user' if item['status']=='excluded' else 'needs_review'))
    report=['# Commandes Telegram du '+date.strftime('%d/%m/%Y'),'',
            str(len(source))+' messages lus, '+str(len(results))+' lots suivis individuellement.',
            str(len(expected))+' commandes créées dans TEST et relues par SELECT. Aucune écriture OB.',
            '',str(dict(collections.Counter(r['status'] for r in results))),
            '', 'Les reçus prouvent la conformité SQL aux paramètres exécutés ; ils ne prouvent pas la compréhension parfaite de tout document source.',
            '', 'La commande 2026ARC14971 doit recevoir le transport confirmé de 300 MAD. La commande 2026ARC15008 doit conserver un seul transport de 50 MAD. L’agent ne dispose pas des droits UPDATE/DELETE nécessaires. Le script ciblé SOB-CORRECTIONS-TRANSPORT-20261109.sql est prêt pour SSMS ; aucune de ces corrections n’a été exécutée.',
            '', 'Les autres points à préciser figurent dans '+prefix+'-A-VERIFIER.csv, avec heures, texte, document et raison.',
            '', 'Demandes retirées après création : '+(', '.join(sorted(withdrawn)) or 'aucune')+'. Le retrait bloque les relances, sans annuler une commande déjà enregistrée dans Sage.',
            '', 'Dernier message exporté : '+summary['last_source_time']+'. Les messages reçus ensuite nécessitent un nouvel export.',
            '', 'Les corrections vérifiées et les exemples restent dans la mémoire PostgreSQL SOB. Bouchaib reste exclu.']
    (ROOT/'TEST'/(prefix+'-RAPPORT.md')).write_text('\n'.join(report),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
